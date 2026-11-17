import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

from scripts import setup_runtime as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ark setup test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.template = Path(setup.ROOT / ".env.example").read_bytes()
        (self.root / ".env.example").write_bytes(self.template)
        self.root_patch = patch.object(setup, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        runtime_paths = SimpleNamespace(
            SERVER_PATH=self.root / "runtime/server",
            SERVER_EXE_PATH=self.root / "runtime/server/ShooterGame/Binaries/Win64/ArkAscendedServer.exe",
            STEAMCMD_PATH=self.root / "runtime/steamcmd/steamcmd.exe",
            LOG_DIR=self.root / "logs", CLUSTER_DIR=self.root / "runtime/clusters")
        path_patch = patch.object(setup, "paths", runtime_paths)
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_fresh_setup_and_rerun_preserve_env(self):
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run") as run:
            setup.prepare()
            env = self.root / ".env"
            self.assertEqual(env.read_bytes().replace(b"\r\n", b"\n"),
                             self.template.replace(b"\r\n", b"\n"))
            env.write_text(env.read_text() + "\n# keep my settings\n", encoding="utf-8")
            before = env.read_bytes()
            setup.prepare()
            self.assertEqual(env.read_bytes(), before)
            run.assert_not_called()
        self.assertTrue((self.root / "runtime/server").is_dir())
        self.assertTrue((self.root / "logs").is_dir())

    def test_download_extracts_only_bootstrap_and_rerun_skips_download(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("steamcmd.exe", b"mock executable")
            bundle.writestr("../unwanted.txt", b"do not extract")
        destination = self.root / "steamcmd/steamcmd.exe"
        with patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(archive.getvalue())) as download:
            setup.install_steamcmd(destination)
            setup.install_steamcmd(destination)
            download.assert_called_once()
        self.assertEqual(destination.read_bytes(), b"mock executable")
        self.assertFalse((self.root / "unwanted.txt").exists())

    def test_server_install_passes_paths_with_spaces_as_individual_arguments(self):
        executable = self.root / "runtime/server/ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
        def install(args, **kwargs):
            self.assertEqual(args[2], str(self.root / "runtime/server"))
            self.assertEqual(args[6], "2430930")
            self.assertTrue(kwargs["check"])
            executable.parent.mkdir(parents=True)
            executable.touch()
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run", side_effect=install):
            setup.prepare(install_server=True)

    def test_steamcmd_failure_propagates(self):
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "steamcmd")):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.prepare(install_server=True)

    def test_missing_server_executable_is_reported(self):
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run"):
            with self.assertRaisesRegex(RuntimeError, "SERVER_EXE_PATH"):
                setup.prepare(install_server=True)

    def test_exit_7_retries_then_checks_server_executable(self):
        executable = setup.paths.SERVER_EXE_PATH
        def install(args, **kwargs):
            if run.call_count == 1:
                raise subprocess.CalledProcessError(7, args)
            executable.parent.mkdir(parents=True)
            executable.touch()
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run", side_effect=install) as run:
            setup.prepare(install_server=True)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0], run.call_args_list[1])

    def test_exit_7_stops_after_three_attempts(self):
        with patch.object(setup, "install_steamcmd"), patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(7, "steamcmd")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                setup.prepare(install_server=True)
        self.assertEqual(run.call_count, 3)

    def test_environment_path_overrides_are_ignored(self):
        with patch.dict(os.environ, {"SERVER_PATH": "not-the-server", "STEAMCMD_PATH": "not-steamcmd"}):
            with patch.object(setup, "install_steamcmd") as install:
                setup.prepare()
        install.assert_called_once_with(self.root / "runtime/steamcmd/steamcmd.exe")
        self.assertTrue((self.root / "runtime/server").is_dir())


if __name__ == "__main__":
    unittest.main()
