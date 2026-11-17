import unittest
from types import SimpleNamespace
from unittest.mock import patch

from discord.ext import commands

import permissions


class PermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {}
        config = SimpleNamespace(get=self.settings.get, update=self.settings.update)
        mock = patch.object(permissions, "dc_config", config)
        mock.start()
        self.addCleanup(mock.stop)
        self.ctx = SimpleNamespace(
            author=SimpleNamespace(id=123, roles=[SimpleNamespace(id=456)],
                                   guild_permissions=SimpleNamespace(administrator=False, manage_guild=False)),
            guild=SimpleNamespace(id=789, owner_id=999), bot=SimpleNamespace(can_run=self.can_run),
            command=None,
        )

    async def can_run(self, ctx):
        return True

    def test_missing_settings_do_not_grant_admin_even_to_discord_admin(self):
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.PLAYER)

    def test_explicit_user_id_grants_admin(self):
        self.settings["admin_user_ids"] = [123]
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.ADMIN)

    def test_bootstrap_manager_then_internal_admin_only(self):
        self.ctx.author.guild_permissions.manage_guild = True
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.ADMIN)
        member = SimpleNamespace(id=777, bot=False)
        self.assertTrue(permissions.add_admin(self.ctx, member))
        self.assertTrue(self.settings["admin_setup_completed"])
        self.assertEqual(self.settings["admin_user_ids"], [777])
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.PLAYER)
        with self.assertRaises(permissions.AdminRequired):
            permissions.add_admin(self.ctx, SimpleNamespace(id=888, bot=False))
        self.ctx.author.id = 777
        self.assertTrue(permissions.add_admin(self.ctx, SimpleNamespace(id=888, bot=False)))
        self.assertFalse(permissions.add_admin(self.ctx, member))

    def test_owner_and_administrator_bootstrap_but_no_bypass_after_setup(self):
        for attribute in ("owner", "administrator"):
            with self.subTest(attribute=attribute):
                self.ctx.author.id = 999 if attribute == "owner" else 123
                self.ctx.author.guild_permissions.administrator = attribute == "administrator"
                self.settings.clear()
                self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.ADMIN)
                self.settings["admin_setup_completed"] = True
                self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.PLAYER)

    def test_role_ids_do_not_grant_access(self):
        self.settings.update(admin_role_ids=[456], admin_setup_completed=True)
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.PLAYER)

    def test_dm_cannot_bootstrap(self):
        self.ctx.guild = None
        self.ctx.author.guild_permissions.manage_guild = True
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.PLAYER)

    def test_bot_account_rejected_without_initializing(self):
        self.ctx.author.guild_permissions.manage_guild = True
        with self.assertRaises(commands.BadArgument):
            permissions.add_admin(self.ctx, SimpleNamespace(id=777, bot=True))
        self.assertEqual(self.settings, {})

    async def test_mention_converter_rejects_names_ids_and_roles(self):
        converter = permissions.MemberMention()
        for value in ("Alice", "123", "<@&456>", "@everyone", "<@123> extra"):
            with self.subTest(value=value), self.assertRaises(commands.BadArgument):
                await converter.convert(self.ctx, value)

    def test_explicit_user_admin_works_in_dm(self):
        self.settings["admin_user_ids"] = [123]
        self.ctx.guild = None
        del self.ctx.author.roles
        self.assertEqual(permissions.get_permission_level(self.ctx), permissions.PermissionLevel.ADMIN)

    async def test_command_guard_rejects_player_and_accepts_admin(self):
        @commands.command()
        @permissions.admin_only()
        async def restricted(ctx):
            pass

        with self.assertRaises(permissions.AdminRequired):
            await restricted.can_run(self.ctx)
        self.settings["admin_user_ids"] = [123]
        self.assertTrue(await restricted.can_run(self.ctx))
        self.settings["admin_user_ids"] = []
        with self.assertRaises(permissions.AdminRequired):
            await restricted.can_run(self.ctx)

    async def test_undecorated_commands_remain_available(self):
        @commands.command()
        async def public(ctx):
            pass

        self.assertTrue(await public.can_run(self.ctx))


if __name__ == "__main__":
    unittest.main()
