import discord
from discord.ext import commands

import consts
import env
import server
from config import dc_config, server_config

intent = discord.Intents.default()
intent.message_content = True
bot = commands.Bot(command_prefix="!", intents=intent, help_command=None)


@bot.command()
async def start(ctx):
    if server.is_updating():
        await ctx.send("🟡 Server is currently updating. Please wait until it is finished.")
        return

    if server.is_running():
        await ctx.send("🟡 Server already running.")
        return

    server.start()
    await ctx.send("🟡 Starting server...")

    is_ready = await server.wait_for_ready()
    if is_ready:
        await ctx.send("🟢 Server is ready.")
    else:
        server.terminate()
        await ctx.send("🔴 Server failed to start. Please try again!")

    is_empty = await server.is_running_empty()

    if is_empty:
        await ctx.send("🟡 Server is closing due to inactivity...")
        await server.stop()
        await ctx.send("🔴 Server stopped.")
    

@bot.command()
async def stop(ctx):
    if not server.is_running():
        await ctx.send("🟡 Server is not running.")
        return
    
    if server.is_someone_online():
        await ctx.send("🟡 Please wait for players to leave before stopping the server.")
        return

    await ctx.send("🟡 Server is saving...")
    await server.stop()
    await ctx.send("🔴 Server stopped.")


@bot.command()
async def update(ctx):
    await ctx.send("🟡 Updating server...")

    success, message = await server.update()

    indicator = "🟢" 
    if success is False:
        indicator = "🔴"

    await ctx.send(f"{indicator} {message}")


@bot.command()
async def info(ctx):
    player_list = server.get_online_players()

    status = "Running 🟢" if server.is_running() else "Stopped 🔴"
    if status == "Running 🟢" and player_list is None:
        status = "Loading 🟡"

    msg = f"""
    🦖 **ARK SA Server**

    Status: {status}
    Name: {env.NAME}
    Password: {env.PASSWORD}
    Current map: {server_config.get("map").replace("_WP", "")}

    Players: {player_list}
    """
    await ctx.send(msg)


@bot.command()
async def maps(ctx):
    msg = "🗺️ **Available maps**\n\n"

    msg += "\n".join(
        f"• {key.replace("_WP", "")} : {'🟢 available' if value else '🔴 unavailable'}"
        for key, value in consts.available_maps.items()
    )
    
    await ctx.send(msg)


@bot.command()
async def set_map(ctx, *, map_name: str):
    lower_map_name = map_name.lower()
    lookup = {
        key.replace("_WP", "").lower(): key
        for key in consts.available_maps.keys()
    }

    if lower_map_name not in lookup:
        await ctx.send("🔴 Map not found. Use !maps to see available maps.")
        return
    
    map_key = lookup[lower_map_name]
    is_available = consts.available_maps[map_key]

    if not is_available:
        await ctx.send(f"🟡 {map_name} is currently unavailable. Use !maps to see available maps.")
        return

    server_config.set("map", map_key)
    await ctx.send(f"🟢 Map set to **{map_key.replace("_WP", "")}**. Please restart server to apply changes.")


@bot.command()
async def set_channel(ctx):
    ids = set(dc_config.get("channel_ids"))
    ids.add(ctx.channel.id)
    dc_config.set("channel_ids", list(ids))
    await ctx.send("🟢 Channel set ark_bot will watch this channel.")


@bot.command()
async def remove_channel(ctx):
    ids = set(dc_config.get("channel_ids"))
    curr_id = ctx.channel.id

    if curr_id in ids:
        ids.remove(curr_id)

    dc_config.set("channel_ids", list(ids))

    await ctx.send("🟡 Channel removed, ark_bot will watch every channel.")


@bot.command()
async def help(ctx):
    msg = """
    🦖 **ARK BOT GUIDE**
    Ark bot allows you to interact with the ARK server.

    Commands:
    !help: Show this message.

    !start: Start the server.
    !stop: Stop the server.
    !info: List server informations.
    !update: Update the server. It is only required after game updates, otherwise it is not recommended to use.

    !maps: List available maps.
    !set_map {map_name}: Set a map for the server. Example: !set_map TheIsland.

    !set_channel: Set the current discord channel for the bot, the bot will ignore any other channels.
    !remove_channel: Remove the setted discord channel, the bot will watch every channel.
    """
    await ctx.send(msg)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_ids = dc_config.get("channel_ids")

    if channel_ids != [] and message.channel.id not in channel_ids:
        return

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print("Bot ready")


bot.run(env.DC_TOKEN)