import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands
from config import ServerConfigManager
import permissions


class ModTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "server_config.json"
        self.initial = {"map": "TheIsland_WP", "port": 7777, "max_players": 20,
                        "mods": ["939688", "1125041"], "platform": "ALL"}
        self.path.write_text(json.dumps(self.initial))
        self.config = ServerConfigManager(str(self.path))

    def test_mod_changes_survive_reload_and_keep_other_settings_and_order(self):
        self.assertTrue(self.config.add_mod(" 000123 "))
        self.assertFalse(self.config.add_mod("123"))
        self.assertTrue(self.config.remove_mod("939688"))
        self.assertFalse(self.config.remove_mod("999"))
        reloaded = ServerConfigManager(str(self.path))
        self.assertEqual(reloaded.get_mods(), ["1125041", "123"])
        self.assertEqual(json.loads(self.path.read_text())["mods"], ["1125041", "123"])
        self.assertIn("-mods=1125041,123", reloaded.build_server_args())
        self.assertEqual(reloaded.get("map"), self.initial["map"])
        self.assertEqual(reloaded.get("port"), self.initial["port"])

    def test_invalid_ids_do_not_modify_config(self):
        before = self.path.read_bytes()
        for value in ("", "0", "-1", "1.5", "abc", "1,2", "123 456", "<@123>"):
            for operation in (self.config.add_mod, self.config.remove_mod):
                with self.assertRaises(ValueError): operation(value)
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_mods_omit_launch_argument(self):
        self.config.remove_mod("939688")
        self.config.remove_mod("1125041")
        self.assertEqual(ServerConfigManager(str(self.path)).get_mods(), [])
        self.assertFalse(any(arg.startswith("-mods=") for arg in self.config.build_server_args()))
        del self.config.data["mods"]
        self.assertEqual(self.config.get_mods(), [])

    async def test_discord_commands_are_restricted_and_help_hides_them(self):
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), help_command=None)
        self.addAsyncCleanup(bot.close)
        ns = {"bot": bot, "admin_only": permissions.admin_only,
              "server_config": self.config, "get_permission_level": permissions.get_permission_level,
              "PermissionLevel": permissions.PermissionLevel}
        tree = ast.parse(Path("dc_bot.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                 and n.name in ("mods", "add_mod", "remove_mod", "help")]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "dc_bot.py", "exec"), ns)
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), guild=None, bot=bot,
                              command=None, send=AsyncMock())
        settings = {"admin_setup_completed": True, "admin_user_ids": []}
        with patch.object(permissions, "dc_config", SimpleNamespace(get=settings.get)):
            for name in ("mods", "add_mod", "remove_mod"):
                with self.assertRaises(permissions.AdminRequired):
                    await bot.get_command(name).can_run(ctx)
            await bot.get_command("help").callback(ctx)
            self.assertNotIn("!add_mod", ctx.send.await_args.args[0])
            settings["admin_user_ids"] = [1]
            for name in ("mods", "add_mod", "remove_mod"):
                self.assertTrue(await bot.get_command(name).can_run(ctx))
            await bot.get_command("help").callback(ctx)
            self.assertIn("!add_mod", ctx.send.await_args.args[0])
            await bot.get_command("add_mod").callback(ctx, mod_id="456")
            self.assertEqual(ServerConfigManager(str(self.path)).get_mods()[-1], "456")
            await bot.get_command("remove_mod").callback(ctx, mod_id="456")
            self.assertNotIn("456", ServerConfigManager(str(self.path)).get_mods())
            await bot.get_command("mods").callback(ctx)
            self.assertIn("939688", ctx.send.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
