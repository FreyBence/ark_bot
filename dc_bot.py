import asyncio
import time

import discord
from discord.ext import commands

import env
import server
from config import dc_config, server_config
from steam_progress import SteamProgress
from worlds import resolve_map, select_world
from permissions import (AdminRequired, MemberMention, PermissionLevel, add_admin as grant_admin,
                         admin_only, get_permission_level)

intent = discord.Intents.default()
intent.message_content = True
bot = commands.Bot(command_prefix="!", intents=intent, help_command=None)


@bot.command()
async def start(ctx):
    if server.is_updating():
        await ctx.send("đźźˇ Server maintenance or map creation is in progress. Please wait.")
        return

    if server.is_running():
        await ctx.send("đźźˇ Server already running.")
        return

    try:
        server.start()
    except (OSError, RuntimeError, ValueError) as error:
        await ctx.send(str(error))
        return
    await ctx.send("đźźˇ Starting server...")

    is_ready = await server.wait_for_ready()
    if is_ready:
        await ctx.send("đźź˘ Server is ready.")
    else:
        server.terminate()
        await ctx.send("đź”´ Server failed to start. Please try again!")

    is_empty = await server.is_running_empty()

    if is_empty:
        await ctx.send("đźźˇ Server is closing due to inactivity...")
        _, result = await server.stop()
        await ctx.send(result)


@bot.command()
async def stop(ctx):
    if server.is_creating_map():
        await ctx.send("Wait for map creation to finish before stopping the server.")
        return
    if not server.is_running():
        await ctx.send("đźźˇ Server is not running.")
        return

    if server.is_someone_online():
        await ctx.send("đźźˇ Please wait for players to leave before stopping the server.")
        return

    await ctx.send("đźźˇ Server is saving...")
    _, result = await server.stop()
    await ctx.send(result)


@bot.command(ignore_extra=False)
@admin_only()
async def init(ctx):
    await _run_with_progress(ctx, server.init, "Initializing ARK server")


@bot.command()
async def update(ctx):
    await _run_with_progress(ctx, server.update, "Updating ARK server")


async def _run_with_progress(ctx, operation, title):
    progress = SteamProgress()
    message = await ctx.send(progress.render(title))

    async def report():
        while True:
            await asyncio.sleep(5)
            try:
                await message.edit(content=progress.render(title))
            except discord.HTTPException:
                # A deleted message or Discord outage must not abort SteamCMD.
                return

    reporter = asyncio.create_task(report())
    try:
        success, result = await operation(progress=progress)
    finally:
        reporter.cancel()
        try:
            await reporter
        except asyncio.CancelledError:
            pass
    status = "Completed" if success else "Failed"
    elapsed = int(time.monotonic() - progress.started)
    content = f"{title}: {status} ({elapsed // 60:02d}:{elapsed % 60:02d})\n{result}"
    try:
        await message.edit(content=content)
    except discord.HTTPException:
        await ctx.send(content)


@bot.command()
async def info(ctx):
    player_list = server.get_online_players()

    status = "Running đźź˘" if server.is_running() else "Stopped đź”´"
    if status == "Running đźź˘" and player_list is None:
        status = "Loading đźźˇ"

    msg = f"""
    đź¦– **ARK SA Server**

    Status: {status}
    Name: {env.NAME}
    Password: {env.PASSWORD}
    Current map: {server_config.get("map").replace("_WP", "")}
    Selected world: {server_config.get("world", "default")}

    Players: {player_list}
    """
    await ctx.send(msg)


@bot.command()
async def maps(ctx):
    try:
        available = await server.get_maps()
    except (OSError, ValueError):
        await ctx.send("The installed map catalog could not be read. Ask an admin to run !init or inspect the host.")
        return
    entries = ["**Detected maps:**"]
    for map_id, instances in available.items():
        entries.append(f"{map_id}: available ({len(instances)} instances)" if instances
                       else f"{map_id}: unavailable (not created)")
        entries.extend(f"- {world.world_id}" for world in instances)
    lines = []
    for line in entries:
        if len("\n".join(lines + [line])) > 1900:
            await ctx.send("\n".join(lines))
            lines = []
        lines.append(line)
    await ctx.send("\n".join(lines))


@bot.command(ignore_extra=False)
@admin_only()
async def create_map(ctx, map_name: str = "", world_name: str | None = None):
    if not map_name:
        await ctx.send("Use !create_map <map> [world], for example !create_map TheIsland or !create_map TheIsland main.")
        return
    async def operation(progress):
        return await server.create_map(map_name, world_name, progress=progress)
    await _run_with_progress(ctx, operation, f"Creating {map_name} / {world_name or 'automatic name'}")


@bot.command()
@admin_only()
async def mods(ctx):
    selected = server_config.get_mods()
    if not selected:
        await ctx.send("No mods are selected.")
        return
    lines = ["**Selected mods (load order; applied on the next server start):**"]
    for index, mod_id in enumerate(selected, 1):
        line = f"{index}. {mod_id}"
        if len("\n".join(lines + [line])) > 1900:
            await ctx.send("\n".join(lines))
            lines = []
        lines.append(line)
    await ctx.send("\n".join(lines))


@bot.command()
@admin_only()
async def add_mod(ctx, *, mod_id: str = ""):
    try:
        added = server_config.add_mod(mod_id)
    except ValueError as error:
        await ctx.send(str(error))
        return
    if added:
        await ctx.send("Mod added. The change applies on the next ARK server start.")
    else:
        await ctx.send("That mod is already selected; no changes made.")


@bot.command()
@admin_only()
async def remove_mod(ctx, *, mod_id: str = ""):
    try:
        removed = server_config.remove_mod(mod_id)
    except ValueError as error:
        await ctx.send(str(error))
        return
    if removed:
        await ctx.send("Mod removed. The change applies on the next ARK server start.")
    else:
        await ctx.send("That mod is not selected; no changes made.")


@bot.command(ignore_extra=False)
async def set_map(ctx, map_name: str, world_name: str | None = None):
    if server.is_creating_map():
        await ctx.send("Wait for map creation to finish before selecting a map.")
        return
    try:
        available = await server.get_maps()
        map_key = resolve_map(map_name, available)
    except (OSError, ValueError):
        await ctx.send("Map not found or the installed catalog is unavailable. Use !maps.")
        return
    # Recheck after reading the catalog, which yields to other commands.
    if server.is_creating_map():
        await ctx.send("Wait for map creation to finish before selecting a map.")
        return
    try:
        world = select_world(map_key, world_name, available[map_key])
    except ValueError as error:
        await ctx.send(str(error))
        return
    server_config.update({"map": world.map_id, "world": world.world_id})
    await ctx.send(f"Selected **{world.map_id} / {world.world_id}**. Restart the server to apply changes.")


@bot.command()
async def set_channel(ctx):
    ids = set(dc_config.get("channel_ids", []))
    ids.add(ctx.channel.id)
    dc_config.set("channel_ids", list(ids))
    await ctx.send("đźź˘ Channel set ark_bot will watch this channel.")


@bot.command()
async def remove_channel(ctx):
    ids = set(dc_config.get("channel_ids", []))
    curr_id = ctx.channel.id

    if curr_id not in ids:
        await ctx.send("This channel wasnâ€™t configured; no changes made.")
        return

    ids.remove(curr_id)

    dc_config.set("channel_ids", list(ids))

    if ids:
        await ctx.send("Channel removed. The bot will watch the remaining configured channels.")
    else:
        await ctx.send("Channel removed. The bot will watch every channel.")


@bot.command(ignore_extra=False)
@commands.guild_only()
@admin_only()
async def add_admin(ctx, member: MemberMention):
    added = grant_admin(ctx, member)
    if added:
        await ctx.send(f"{member.mention} is now an ARK admin. "
                       "Only internal ARK admins now have administrator access.")
    else:
        await ctx.send(f"{member.mention} is already an ARK admin; no changes made.")


@add_admin.error
async def add_admin_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("Use !add_admin @person in a Discord server.")
    elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument,
                            commands.TooManyArguments)):
        await ctx.send("Use !add_admin @person with a Discord user mention. "
                       "The person must be a member of this Discord server and cannot be a bot.")
    elif isinstance(error, AdminRequired):
        await ctx.send(str(error))
    else:
        await commands.Bot.on_command_error(bot, ctx, error)


@bot.command()
async def permissions(ctx):
    level = get_permission_level(ctx).name.lower()
    await ctx.send(f"Your ark-bot permission level: **{level}**.")


@bot.command()
async def help(ctx):
    msg = """
    đź¦– **ARK BOT GUIDE**
    Ark bot allows you to interact with the ARK server.

    Commands:
    !help: Show this message.
    !permissions: Show your ark-bot permission level.

    !start: Start the server.
    !stop: Stop the server.
    !info: List server informations.
    !update: Update the server. It is only required after game updates, otherwise it is not recommended to use.

    !maps: List available maps.
    !set_map <map> [world]: Select a world. Example: !set_map TheIsland main.

    !set_channel: Add this Discord channel to the configured channels.
    !remove_channel: Remove this Discord channel. If none remain, the bot watches every channel.
    """
    if get_permission_level(ctx) == PermissionLevel.ADMIN:
        msg += """
    **Administrator commands:**
    !add_admin @person: Grant ARK admin access.
    !init: Install and initialize the server.
    !create_map <map> [world]: Create a named world while the server is stopped.
    !mods: List selected mods in load order.
    !add_mod <id>: Add a mod by its numeric ID.
    !remove_mod <id>: Remove a selected mod.
    """
    await ctx.send(msg)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_ids = dc_config.get("channel_ids", [])

    if channel_ids != [] and message.channel.id not in channel_ids:
        return

    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if ctx.command is not None and ctx.command.has_error_handler():
        return
    if isinstance(error, AdminRequired):
        await ctx.send(str(error))
        return
    if (ctx.command is not None and ctx.command.name in ("create_map", "set_map")
            and isinstance(error, (commands.MissingRequiredArgument, commands.TooManyArguments))):
        usage = "!create_map <map> [world]" if ctx.command.name == "create_map" else "!set_map <map> [world]"
        await ctx.send(f"Use {usage}. Check !maps for available maps and worlds.")
        return
    # Keep discord.py's normal handling for unrelated command errors.
    await commands.Bot.on_command_error(bot, ctx, error)


@bot.event
async def on_ready():
    print("Bot ready")


bot.run(env.DC_TOKEN)
