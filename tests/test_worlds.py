import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from config import ServerConfigManager
import test_server_init as init_tests
from worlds import World, discover_maps, resolve_map, discover_worlds, select_world, validate_world_name


class MapCreationTests(unittest.IsolatedAsyncioTestCase):
    setUp = init_tests.InitTests.setUp

    def prepare(self):
        root = Path(self.env.SERVER_PATH)
        root.mkdir(parents=True)
        self.manifest = root / "Manifest_UFSFiles_Win64.txt"
        self.manifest.write_text(
            "ShooterGame/Content/Maps/TheIslandSubMaps/TheIsland_WP.umap\tdate\n"
            "ShooterGame/Content/Maps/TheIslandSubMaps/BossArena_01_WP.umap\tdate\n"
            "ShooterGame/Content/Maps/TheIslandSubMaps/_Generated_/ABC.umap\tdate\n"
            "ShooterGame/Content/Mods/Ragnarok/Ragnarok_WP.umap\tdate\n")
        self.exe.parent.mkdir(parents=True)
        self.exe.touch()
        self.config = ServerConfigManager(str(root.parent / "config.json"))
        self.config.update({"map": "Ragnarok_WP", "mods": ["123"], "port": 7777,
                            "max_players": 20, "platform": "ALL"})
        self.server.server_config = self.config
        self.process = SimpleNamespace(returncode=None)
        self.process.poll = lambda: self.process.returncode
        self.process.terminate = lambda: setattr(self.process, "returncode", -1)
        self.process.kill = self.process.terminate
        self.process.wait = lambda: self.process.returncode

    def launch(self, map_id, world_id):
        self.assertEqual(world_id, "main")
        self.assertEqual(map_id, "TheIsland_WP")
        self.assertTrue(self.server.is_creating_map())
        self.server.server_process = self.process

    def rcon(self, command):
        if command == "SaveWorld":
            path = World("TheIsland_WP", "main").save_path(self.env.SERVER_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test saved world")
        elif command == "DoExit":
            self.process.returncode = 0
        return "OK"

    def test_manifest_filters_sublevels_and_handles_bundled_mod_folder(self):
        self.prepare()
        catalog = discover_maps(self.env.SERVER_PATH)
        self.assertEqual(catalog, ["Ragnarok_WP", "TheIsland_WP"])
        self.assertEqual(resolve_map("the island", catalog), "TheIsland_WP")
        with self.assertRaises(ValueError): resolve_map("../bad", catalog)
        with self.assertRaises(ValueError): World("../bad").save_path(self.env.SERVER_PATH)
        self.assertIn("second", str(World("TheIsland_WP", "second").save_path(self.env.SERVER_PATH)))

    def test_named_world_discovery_single_selection_and_ambiguity(self):
        self.prepare()
        root = self.env.SERVER_PATH
        for name in ("main", "theOther"):
            save = World("TheIsland_WP", name).save_path(root)
            save.parent.mkdir(parents=True)
            save.write_bytes(b"world")
        worlds = discover_worlds(root, "TheIsland_WP")
        self.assertEqual([w.world_id for w in worlds], ["main", "theOther"])
        with self.assertRaisesRegex(ValueError, "multiple instances"):
            select_world("TheIsland_WP", None, worlds)
        self.assertEqual(select_world("TheIsland_WP", "THEOTHER", worlds).world_id, "theOther")
        self.assertEqual(select_world("TheIsland_WP", None, worlds[:1]).world_id, "main")
        with self.assertRaises(ValueError): select_world("TheIsland_WP", "missing", worlds)
        with self.assertRaises(ValueError): select_world("TheIsland_WP", None, [])

    def test_world_names_reject_paths_and_windows_reserved_names(self):
        for name in ("", "/", "../main", "main/other", "main\\other", "..", ".main", "C:main",
                     "CON", "nul", "LPT1", "COM9", "with space", "name.", "a" * 65, "main?listen"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_world_name(name)
        self.assertEqual(validate_world_name("theOther_2-test"), "theOther_2-test")

    def test_legacy_world_and_named_worlds_are_independent(self):
        self.prepare()
        save = World("TheIsland_WP").save_path(self.env.SERVER_PATH)
        save.parent.mkdir(parents=True)
        save.write_bytes(b"legacy world")
        worlds = discover_worlds(self.env.SERVER_PATH, "TheIsland_WP")
        self.assertEqual([w.world_id for w in worlds], ["default"])
        self.assertFalse(World("TheIsland_WP", "main").available(self.env.SERVER_PATH))
        self.config.update({"map": "TheIsland_WP", "world": "main"})
        self.assertEqual(self.config.build_server_args()[0], "TheIsland_WP?AltSaveDirectoryName=main")
        self.assertEqual(self.config.build_server_args("Ragnarok_WP", "theOther")[0],
                         "Ragnarok_WP?AltSaveDirectoryName=theOther")
        self.assertEqual(self.config.build_server_args("TheIsland_WP", "default")[0], "TheIsland_WP")
        self.assertEqual(save.read_bytes(), b"legacy world")

    async def test_duplicate_name_case_and_partial_directories_are_preserved(self):
        self.prepare()
        directory = World("TheIsland_WP", "Main").save_path(self.env.SERVER_PATH).parent
        directory.mkdir(parents=True)
        with patch.object(self.server, "_launch_server") as launch:
            self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
            self.assertFalse((await self.server.create_map("TheIsland", "../escape"))[0])
            self.assertFalse((await self.server.create_map("TheIsland", "default"))[0])
            launch.assert_not_called()

    async def test_success_preserves_selected_map_and_launch_settings_and_survives_reload(self):
        self.prepare()
        before_args = self.config.build_server_args()
        save = World("TheIsland_WP", "main").save_path(self.env.SERVER_PATH)
        self.assertFalse(World("TheIsland_WP", "main").available(self.env.SERVER_PATH))
        with patch.object(self.server, "_launch_server", self.launch), patch.object(
            self.server, "_wait_creation_ready", AsyncMock(return_value=True)), patch.object(
            self.server, "_creation_rcon", self.rcon):
            success, message = await self.server.create_map("TheIsland", "main")
        self.assertTrue(success, message)
        self.assertFalse(self.server.is_creating_map())
        self.assertFalse(self.server.is_updating())
        self.assertEqual(self.config.build_server_args(), before_args)
        self.assertEqual(ServerConfigManager(self.config.path).get("map"), "Ragnarok_WP")
        self.assertEqual([world.world_id for world in (await self.server.get_maps())["TheIsland_WP"]], ["main"])
        self.assertEqual(self.config.get("official_maps"), ["Ragnarok_WP", "TheIsland_WP"])
        self.assertIsNone(self.server.server_process)

    async def test_existing_world_is_not_launched_or_overwritten(self):
        self.prepare()
        self.rcon("SaveWorld")
        save = World("TheIsland_WP", "main").save_path(self.env.SERVER_PATH)
        original = save.read_bytes()
        with patch.object(self.server, "_launch_server") as launch:
            self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
            launch.assert_not_called()
        self.assertEqual(save.read_bytes(), original)

    async def test_startup_failure_terminates_process_and_releases_lock(self):
        self.prepare()
        with patch.object(self.server, "_launch_server", self.launch), patch.object(
            self.server, "_wait_creation_ready", AsyncMock(return_value=False)):
            self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
        self.assertEqual(self.process.returncode, -1)
        self.assertFalse(self.server.is_updating())
        self.assertFalse(World("TheIsland_WP", "main").available(self.env.SERVER_PATH))

    async def test_missing_save_is_failure_even_after_ready(self):
        self.prepare()
        with patch.object(self.server, "_launch_server", self.launch), patch.object(
            self.server, "_wait_creation_ready", AsyncMock(return_value=True)), patch.object(
            self.server, "_creation_rcon", return_value="OK"):
            self.assertFalse((await self.server.create_map("TheIsland", "main", save_timeout=0))[0])
        self.assertEqual(self.process.returncode, -1)

    async def test_cancellation_blocks_competing_commands_and_cleans_up(self):
        self.prepare()
        entered = asyncio.Event()
        async def wait(*args):
            entered.set()
            await asyncio.Event().wait()
        with patch.object(self.server, "_launch_server", self.launch), patch.object(
            self.server, "_wait_creation_ready", wait):
            task = asyncio.create_task(self.server.create_map("TheIsland", "main"))
            await entered.wait()
            self.assertFalse((await self.server.create_map("Ragnarok"))[0])
            self.assertFalse((await self.server.update())[0])
            with self.assertRaises(RuntimeError): self.server.start()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(self.process.returncode, -1)
        self.assertFalse(self.server.is_updating())
        self.assertFalse(self.server.is_creating_map())

    async def test_shutdown_timeout_fails_and_forces_cleanup(self):
        self.prepare()
        def rcon(command):
            if command == "SaveWorld": self.rcon(command)
            return "OK"
        with patch.object(self.server, "_launch_server", self.launch), patch.object(
            self.server, "_wait_creation_ready", AsyncMock(return_value=True)), patch.object(
            self.server, "_creation_rcon", rcon), patch.object(
            self.server, "_wait_creation_exit", AsyncMock(return_value=False)):
            self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
        self.assertEqual(self.process.returncode, -1)
        self.assertFalse(self.server.is_creating_map())

    async def test_empty_existing_world_not_available_and_not_overwritten(self):
        self.prepare()
        save = World("TheIsland_WP", "main").save_path(self.env.SERVER_PATH)
        save.parent.mkdir(parents=True)
        save.touch()
        self.assertFalse(World("TheIsland_WP", "main").available(self.env.SERVER_PATH))
        with patch.object(self.server, "_launch_server") as launch:
            self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
            launch.assert_not_called()

    async def test_discord_listing_and_selection_of_named_worlds(self):
        import ast
        import discord
        from discord.ext import commands
        from worlds import select_world
        self.prepare()
        for name in ("main", "theOther"):
            save = World("TheIsland_WP", name).save_path(self.env.SERVER_PATH)
            save.parent.mkdir(parents=True)
            save.write_bytes(b"world")
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), help_command=None)
        self.addAsyncCleanup(bot.close)
        tree = ast.parse(Path("dc_bot.py").read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name in ("maps", "set_map")]
        namespace = {"bot": bot, "server": self.server, "server_config": self.config,
                     "resolve_map": resolve_map, "select_world": select_world}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "dc_bot.py", "exec"), namespace)
        ctx = SimpleNamespace(send=AsyncMock())
        await bot.get_command("maps").callback(ctx)
        listing = ctx.send.await_args.args[0]
        self.assertIn("available (2 instances)", listing)
        self.assertIn("- main", listing)
        self.assertIn("- theOther", listing)
        await bot.get_command("set_map").callback(ctx, "TheIsland")
        self.assertIn("multiple instances", ctx.send.await_args.args[0])
        self.assertEqual(self.config.get("map"), "Ragnarok_WP")
        await bot.get_command("set_map").callback(ctx, "TheIsland", "theOther")
        reloaded = ServerConfigManager(self.config.path)
        self.assertEqual(reloaded.get("map"), "TheIsland_WP")
        self.assertEqual(reloaded.get("world"), "theOther")
        self.assertEqual(reloaded.build_server_args()[0], "TheIsland_WP?AltSaveDirectoryName=theOther")

    async def test_automatic_names_increment_and_skip_incomplete_worlds(self):
        self.prepare()
        launched = []
        def launch(map_id, world_id):
            launched.append(world_id)
            self.process.returncode = None
            self.server.server_process = self.process
        def rcon(command):
            if command == "SaveWorld":
                save = World("TheIsland_WP", launched[-1]).save_path(self.env.SERVER_PATH)
                save.parent.mkdir(parents=True)
                save.write_bytes(b"world")
            elif command == "DoExit":
                self.process.returncode = 0
            return "OK"
        with patch.object(self.server, "_launch_server", launch), patch.object(
            self.server, "_wait_creation_ready", AsyncMock(return_value=True)), patch.object(
            self.server, "_creation_rcon", rcon):
            self.assertTrue((await self.server.create_map("TheIsland"))[0])
            self.assertTrue((await self.server.create_map("TheIsland"))[0])
            partial = World("TheIsland_WP", "un_3").save_path(self.env.SERVER_PATH)
            partial.parent.mkdir(parents=True)
            self.assertTrue((await self.server.create_map("TheIsland"))[0])
        self.assertEqual(launched, ["UN_1", "UN_2", "UN_4"])
        self.assertEqual(self.config.get("map"), "Ragnarok_WP")

    async def test_unknown_map_and_running_server_rejected(self):
        self.prepare()
        with patch.object(self.server, "_launch_server") as launch:
            self.assertFalse((await self.server.create_map("NoSuchMap"))[0])
            with patch.object(self.server, "is_running", return_value=True):
                self.assertFalse((await self.server.create_map("TheIsland", "main"))[0])
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
