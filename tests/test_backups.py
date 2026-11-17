import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from backups import backup_world
from worlds import World
import test_server_init as init_tests


class BackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.server = self.root / "server"
        self.dest = self.root / "backups"
        self.world = World("TheIsland_WP", "main")
        save = self.world.save_path(self.server)
        save.parent.mkdir(parents=True)
        save.write_bytes(b"world")
        (save.parent / "123.arkprofile").write_bytes(b"player")
        config = self.server / "ShooterGame/Saved/Config/WindowsServer/Game.ini"
        config.parent.mkdir(parents=True)
        config.write_text("shared config")
        transfer = self.server / "ShooterGame/Saved/LocalProfiles/transfer.bin"
        transfer.parent.mkdir(parents=True)
        transfer.write_bytes(b"transfer")

    def run_backup(self, now, world=None, **kwargs):
        return backup_world(self.server, self.dest, world or self.world, now=now, **kwargs)

    def archives(self):
        return sorted(self.dest.rglob("*.zip"))

    def test_first_backup_and_interval_survive_restart(self):
        self.assertIn("created", self.run_backup(10000))
        original = self.archives()[0].read_bytes()
        self.assertIn("skipped", self.run_backup(10001))
        self.assertEqual(self.archives()[0].read_bytes(), original)
        self.run_backup(17200)
        self.assertEqual(len(self.archives()), 2)
        with zipfile.ZipFile(self.archives()[0]) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("ShooterGame/Saved/SavedArks/main/TheIsland_WP/123.arkprofile", archive.namelist())
            self.assertNotIn("ShooterGame/Saved/Config/WindowsServer/Game.ini", archive.namelist())
            self.assertNotIn("ShooterGame/Saved/LocalProfiles/transfer.bin", archive.namelist())

    def test_entire_world_folder_included_but_neighbor_world_excluded(self):
        folder = self.world.save_path(self.server).parent
        (folder / "123.arktribe").write_bytes(b"tribe")
        (folder / "nested").mkdir()
        (folder / "nested/extra.bin").write_bytes(b"extra")
        (folder / "empty").mkdir()
        neighbor = World("TheIsland_WP", "other").save_path(self.server)
        neighbor.parent.mkdir(parents=True)
        neighbor.write_bytes(b"not this world")
        self.run_backup(10000)
        with zipfile.ZipFile(self.archives()[0]) as archive:
            names = archive.namelist()
            prefix = "ShooterGame/Saved/SavedArks/main/TheIsland_WP/"
            self.assertIn(prefix + "123.arktribe", names)
            self.assertIn(prefix + "nested/extra.bin", names)
            self.assertIn(prefix + "empty/", names)
            self.assertFalse(any("/other/" in name for name in names))

    def test_retention_is_per_world_and_removes_oldest(self):
        first = None
        for index in range(5):
            self.run_backup(10000 + index * 7200)
            if index == 0: first = self.archives()[0]
        self.assertEqual(len(self.archives()), 4)
        self.assertFalse(first.exists())
        other = World("TheIsland_WP", "other")
        save = other.save_path(self.server)
        save.parent.mkdir(parents=True)
        save.write_bytes(b"other world")
        self.run_backup(40000, other)
        self.assertEqual(len(self.archives()), 5)

    def test_failed_verification_retains_all_old_backups(self):
        self.run_backup(10000)
        before = {p: p.read_bytes() for p in self.archives()}
        with patch.object(zipfile.ZipFile, "testzip", return_value="damaged"):
            with self.assertRaises(zipfile.BadZipFile): self.run_backup(20000, retention=1)
        self.assertEqual({p: p.read_bytes() for p in self.archives()}, before)
        self.assertFalse(list(self.dest.rglob("*.partial")))

    def test_write_failure_retains_old_backups(self):
        self.run_backup(10000)
        before = self.archives()
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.run_backup(20000, retention=1)
        self.assertEqual(self.archives(), before)

    def test_invalid_settings_do_not_delete_backups(self):
        self.run_backup(10000)
        for options in ({"retention": 0}, {"retention": True}, {"interval_hours": -1}):
            with self.assertRaises(ValueError): self.run_backup(20000, **options)
        self.assertEqual(len(self.archives()), 1)


class ShutdownBackupTests(unittest.IsolatedAsyncioTestCase):
    setUp = init_tests.InitTests.setUp

    def prepare(self):
        self.process = SimpleNamespace(returncode=None)
        self.process.poll = lambda: self.process.returncode
        self.server.server_process = self.process
        self.actual = World("TheIsland_WP", "played")
        self.server._running_world = self.actual
        self.server.server_config = SimpleNamespace(path="unused", get={"map": "Ragnarok_WP", "world": "next"}.get)
        self.env.BACKUP_DIR = str(Path(self.temp.name) / "backups")

    async def test_clean_stop_backs_up_actual_running_world_under_lock(self):
        self.prepare()
        def finish(): self.process.returncode = 0
        def backup(*args, **kwargs):
            self.assertTrue(self.server.is_updating())
            self.assertEqual(args[2], self.actual)
            return "Backup created."
        with patch.object(self.server, "save"), patch.object(self.server, "exit", finish), patch.object(
            self.server.asyncio, "sleep", AsyncMock()), patch.object(self.server, "backup_world", backup):
            success, message = await self.server.stop()
        self.assertTrue(success)
        self.assertIn("Backup created", message)
        self.assertFalse(self.server.is_updating())

    async def test_backup_failure_is_reported_after_successful_stop(self):
        self.prepare()
        def finish(): self.process.returncode = 0
        with patch.object(self.server, "save"), patch.object(self.server, "exit", finish), patch.object(
            self.server.asyncio, "sleep", AsyncMock()), patch.object(self.server, "backup_world", side_effect=OSError("disk full")):
            success, message = await self.server.stop()
        self.assertTrue(success)
        self.assertIn("backup failed", message)

    async def test_forced_shutdown_does_not_back_up(self):
        self.prepare()
        def terminate(): self.process.returncode = -1
        self.process.terminate = terminate
        with patch.object(self.server, "save"), patch.object(self.server, "exit"), patch.object(
            self.server.asyncio, "sleep", AsyncMock()), patch.object(self.server, "backup_world") as backup:
            await self.server.stop(timeout=0)
            backup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
