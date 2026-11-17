import asyncio
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class InitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ark init test ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.exe = root / "server/ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
        steam = root / "steamcmd/steamcmd.exe"
        steam.parent.mkdir(); steam.touch()
        self.env = SimpleNamespace(SERVER_PATH=str(root / "server"), SERVER_EXE_PATH=str(self.exe),
            STEAMCMD_PATH=str(steam), LOG_DIR=str(root / "logs"), APP_ID="2430930",
            NAME="My server", PASSWORD="join", RCON_PASSWORD="secret", RCON_PORT=27020)
        spec = importlib.util.spec_from_file_location("server_under_test", Path(__file__).resolve().parents[1] / "server.py")
        self.server = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"env": self.env, "paths": self.env}):
            spec.loader.exec_module(self.server)
        self.spawns = 0

    def process(self, code=0, create_exe=True):
        test = self
        class Process:
            returncode = None
            def __init__(self):
                self.stdout = asyncio.StreamReader()
                self.stdout.feed_data(b"Update state (0x5) validating, progress: 50.0\r\nSteamCMD finished")
                self.stdout.feed_eof()
            def kill(self): self.returncode = -1
            async def wait(self):
                if self.returncode is None:
                    if create_exe:
                        test.exe.parent.mkdir(parents=True, exist_ok=True)
                        test.exe.touch()
                    self.returncode = code
                return self.returncode
        return Process()

    async def spawn(self, *args, **kwargs):
        self.spawns += 1
        self.assertTrue(self.server.is_updating())
        self.assertEqual(args[2], self.env.SERVER_PATH)
        self.assertIn("validate", args)
        await asyncio.sleep(0)
        return self.process()

    async def test_fresh_init_and_idempotent_rerun_preserve_files(self):
        with patch.object(self.server.asyncio, "create_subprocess_exec", self.spawn):
            success, _ = await self.server.init()
            self.assertTrue(success)
            ini = Path(self.env.SERVER_PATH) / "ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini"
            self.assertIn("RCONEnabled=True", ini.read_text())
            self.assertIn("ServerAdminPassword=secret", ini.read_text())
            ini.write_text("custom settings")
            save = Path(self.env.SERVER_PATH) / "ShooterGame/Saved/keep.ark"
            save.write_bytes(b"world")
            self.assertTrue((await self.server.init())[0])
            self.assertEqual(ini.read_text(), "custom settings")
            self.assertEqual(save.read_bytes(), b"world")
            self.assertEqual(self.spawns, 2)
            self.assertTrue(list(Path(self.env.LOG_DIR).glob("init_*.log")))
        self.assertFalse(self.server.is_updating())

    async def test_existing_executable_still_requires_successful_validation(self):
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"broken executable")
        async def failed(*args, **kwargs):
            self.assertIn("validate", args)
            return self.process(code=1, create_exe=False)
        with patch.object(self.server.asyncio, "create_subprocess_exec", failed):
            self.assertFalse((await self.server.init())[0])
        with patch.object(self.server.asyncio, "create_subprocess_exec", self.spawn):
            self.assertTrue((await self.server.init())[0])
        self.assertEqual(self.spawns, 1)

    async def test_rerun_refills_missing_ini_after_validation(self):
        with patch.object(self.server.asyncio, "create_subprocess_exec", self.spawn):
            self.assertTrue((await self.server.init())[0])
            directory = Path(self.env.SERVER_PATH) / "ShooterGame/Saved/Config/WindowsServer"
            ini = directory / "GameUserSettings.ini"
            ini.write_text("keep these settings")
            (directory / "Game.ini").unlink()
            self.assertTrue((await self.server.init())[0])
            self.assertTrue((directory / "Game.ini").is_file())
            self.assertEqual(ini.read_text(), "keep these settings")
        self.assertEqual(self.spawns, 2)

    async def test_competing_init_and_update_are_rejected(self):
        with patch.object(self.server.asyncio, "create_subprocess_exec", self.spawn):
            results = await asyncio.gather(self.server.init(), self.server.init(), self.server.update())
        self.assertEqual(sum(result[0] for result in results), 1)
        self.assertEqual(self.spawns, 1)

    async def test_failed_install_and_missing_executable_do_not_create_ini(self):
        for code in (0, 1):
            async def spawn(*args, **kwargs): return self.process(code, create_exe=False)
            with patch.object(self.server.asyncio, "create_subprocess_exec", spawn):
                self.assertFalse((await self.server.init())[0])
            self.assertFalse(self.server.is_updating())
            self.assertFalse((Path(self.env.SERVER_PATH) / "ShooterGame/Saved/Config").exists())

    async def test_cancelled_install_keeps_log_and_releases_process_and_lock(self):
        process = self.process(create_exe=False)
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_data(b"partial download output\n")
        async def spawn(*args, **kwargs): return process
        with patch.object(self.server.asyncio, "create_subprocess_exec", spawn):
            task = asyncio.create_task(self.server.init())
            for _ in range(50):
                await asyncio.sleep(0)
                logs = list(Path(self.env.LOG_DIR).glob("init_*.log"))
                if logs and logs[0].read_bytes():
                    break
            self.assertEqual(logs[0].read_bytes(), b"partial download output\n")
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(process.returncode, -1)
        self.assertFalse(self.server.is_updating())
        self.assertIsNone(self.server.update_process)
        self.assertEqual(logs[0].read_bytes(), b"partial download output\n")

    async def test_running_server_and_missing_credentials_do_not_spawn(self):
        with patch.object(self.server.asyncio, "create_subprocess_exec") as spawn:
            with patch.object(self.server, "is_running", return_value=True):
                self.assertFalse((await self.server.init())[0])
            self.env.RCON_PASSWORD = ""
            self.assertFalse((await self.server.init())[0])
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
