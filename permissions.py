"""Bot permission levels, independent of Discord's built-in Administrator flag."""

from enum import IntEnum
import re

from discord.ext import commands

from config import dc_config


class PermissionLevel(IntEnum):
    PLAYER = 0
    ADMIN = 1


class AdminRequired(commands.CheckFailure):
    """The caller is not configured as an ark-bot administrator."""


def get_permission_level(ctx) -> PermissionLevel:
    admin_ids = dc_config.get("admin_user_ids", [])
    if ctx.author.id in admin_ids:
        return PermissionLevel.ADMIN

    # Existing internal admins also disable bootstrap in older config files.
    initialized = dc_config.get("admin_setup_completed", False) or bool(admin_ids)
    if not initialized and ctx.guild is not None:
        if (ctx.author.id == ctx.guild.owner_id
                or ctx.author.guild_permissions.manage_guild
                or ctx.author.guild_permissions.administrator):
            return PermissionLevel.ADMIN

    return PermissionLevel.PLAYER


def add_admin(ctx, member) -> bool:
    """Recheck access after member conversion, then save the handover together."""
    if get_permission_level(ctx) < PermissionLevel.ADMIN:
        raise AdminRequired("This command requires ark-bot administrator access.")
    if member.bot:
        raise commands.BadArgument("Bot accounts cannot be ARK admins.")
    ids = list(dc_config.get("admin_user_ids", []))
    if member.id in ids:
        return False
    ids.append(member.id)
    dc_config.update({"admin_user_ids": ids, "admin_setup_completed": True})
    return True


class MemberMention(commands.MemberConverter):
    async def convert(self, ctx, argument):
        if re.fullmatch(r"<@!?[0-9]+>", argument) is None:
            raise commands.BadArgument("Use !add_admin @person with a Discord user mention.")
        return await super().convert(ctx, argument)


def admin_only():
    """Place below @bot.command() on future administration commands."""
    async def predicate(ctx):
        if get_permission_level(ctx) < PermissionLevel.ADMIN:
            raise AdminRequired("This command requires ark-bot administrator access.")
        return True

    return commands.check(predicate)
