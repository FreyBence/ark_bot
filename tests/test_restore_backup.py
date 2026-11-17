import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from backups import backup_world
from scripts.restore_backup import restore_world, choose_backup, require_offline
import test_backups as backup_tests


class RestoreTests(unittest.TestCase):
    setUp = backup_tests.BackupTests.setUp

    def prepare(self):
        backup_world(self.server, self.dest, self.world, now=10000)
        self.directory = self.dest / self.world.map_id / self.world.world_id
        self.archive = next(self.directory.glob("backup_*.zip"))
        self.save = self.world.save_path(self.server)
        self.save.write_bytes(b"current live world")

    def restore(self, date):
        return restore_world(self.server, self.dest, self.world, date, offline_check=lambda: None)

    def test_restore_current_increment_and_retention_exclusion(self):
        self.prepare()
        _, current = self.restore(self.archive.name)
        self.assertEqual(current.name, "current.zip")
        self.assertEqual(self.save.read_bytes(), b"world")
        _, second = self.restore("current")
        self.assertEqual(second.name, "current_1.zip")
        self.assertEqual(self.save.read_bytes(), b"current live world")
        self.restore("current_1")
        self.assertEqual(self.save.read_bytes(), b"world")
        self.assertTrue((self.directory / "current_2.zip").is_file())
        backup_world(self.server, self.dest, self.world, now=20000, retention=1)
        self.assertEqual(len(list(self.directory.glob("backup_*.zip"))), 1)
        self.assertEqual(len(list(self.directory.glob("current*.zip"))), 3)

    def test_restores_exact_folder_and_preserves_shared_settings(self):
        self.prepare()
        (self.save.parent / "extra.bin").write_bytes(b"not in old backup")
        shared = self.server / "ShooterGame/Saved/Config/WindowsServer/Game.ini"
        self.restore(self.archive.name)
        self.assertFalse((self.save.parent / "extra.bin").exists())
        self.assertEqual(shared.read_text(), "shared config")
        with zipfile.ZipFile(self.directory / "current.zip") as current:
            self.assertTrue(any(n.endswith("extra.bin") for n in current.namelist()))

    def test_corrupt_or_mismatched_archive_never_changes_live_world(self):
        self.prepare()
        for malicious in (False, True):
            with zipfile.ZipFile(self.archive, "w") as archive:
                archive.writestr("backup_metadata.json", json.dumps({"map": self.world.map_id, "world": self.world.world_id if malicious else "wrong"}))
                archive.writestr("../../outside.txt", b"bad")
            with self.assertRaises(ValueError): self.restore(self.archive.name)
            self.assertEqual(self.save.read_bytes(), b"current live world")
            self.assertFalse((self.directory / "current.zip").exists())
        self.archive.write_bytes(b"not zip")
        with self.assertRaises(zipfile.BadZipFile): self.restore(self.archive.name)
        self.assertEqual(self.save.read_bytes(), b"current live world")

    def test_failed_safety_snapshot_leaves_world_untouched(self):
        self.prepare()
        with patch("scripts.restore_backup.write_world_archive", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.restore(self.archive.name)
        self.assertEqual(self.save.read_bytes(), b"current live world")

    def test_failed_swap_rolls_original_directory_back(self):
        self.prepare()
        rename = Path.rename
        def fail_stage(path, target):
            if path.name.startswith(".restore-stage-"):
                raise OSError("test swap failure")
            return rename(path, target)
        with patch.object(Path, "rename", fail_stage):
            with self.assertRaises(OSError): self.restore(self.archive.name)
        self.assertEqual(self.save.read_bytes(), b"current live world")
        self.assertTrue((self.directory / "current.zip").exists())

    def test_date_ambiguity_and_unsafe_selectors_are_rejected(self):
        self.prepare()
        backup_world(self.server, self.dest, self.world, now=20000)
        with self.assertRaisesRegex(ValueError, "Several"):
            choose_backup(self.directory, "1970-01-01")
        with self.assertRaises(ValueError): choose_backup(self.directory, "../current")

    def test_busy_process_check_refuses_restore(self):
        import subprocess
        with patch("scripts.restore_backup.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="busy")):
            with self.assertRaises(RuntimeError): require_offline()


if __name__ == "__main__":
    unittest.main()
