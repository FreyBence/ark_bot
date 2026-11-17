import asyncio
import codecs
import os
import re
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from mcrcon import MCRcon, MCRconException

import env
import paths
from config import server_config
from backups import backup_world
from steam_progress import SteamProgress
from worlds import (World, discover_maps, resolve_map, discover_worlds,
                    select_world, validate_world_name, next_world_name)

################# PROCESS HANDLERS #################
server_process = None
update_process = None
_update_lock = asyncio.Lock()
_creating_map = False
_running_world = None
last_start_time = time.time()

def is_running():
    global server_process
    if server_process is None:
        return False
    return server_process.poll() is None


def is_updating():
    global update_process
    return _update_lock.locked() or (
        update_process is not None and update_process.returncode is None
    )


def is_creating_map():
    return _creating_map


def start():
    if is_updating() or is_running():
        raise RuntimeError("Server is busy or already running.")
    if not World(server_config.get("map"), server_config.get("world", "default")).available(paths.SERVER_PATH):
        raise RuntimeError("The selected map has no saved world yet. Ask an admin to use !create_map first.")
    _launch_server()


def _launch_server(map_id=None, world_id=None):
    global _running_world
    global last_start_time
    last_start_time = time.time()

    global server_process
    server_process = subprocess.Popen(
        [paths.SERVER_EXE_PATH] + server_config.build_server_args(map_id, world_id),
        cwd=os.path.dirname(paths.SERVER_EXE_PATH)
    )
    _running_world = World(map_id or server_config.get("map"),
                           world_id or server_config.get("world", "default"))


async def stop(timeout=60):
    global _running_world
    if is_updating():
        return False, "Server maintenance, shutdown or map creation is already in progress."
    if not is_running():
        return False, "Server is not running."
    async with _update_lock:
        process = server_process
        world = _running_world
        save()
        await asyncio.sleep(10)
        exit()
        await asyncio.sleep(10)
        deadline = time.monotonic() + timeout
        while process.poll() is None and time.monotonic() < deadline:
            await asyncio.sleep(1)
        if process.poll() is None:
            terminate()
            return False, "Server required forced termination; automatic backup skipped."
        _running_world = None
        if process.returncode != 0:
            return True, "Server stopped abnormally; automatic backup skipped."
        if world is None:
            return True, "Server stopped; backup skipped because the running world was not identified."
        try:
            job = asyncio.create_task(asyncio.to_thread(
                backup_world, paths.SERVER_PATH, paths.BACKUP_DIR, world,
                retention=server_config.get("backup_count", 4),
                interval_hours=server_config.get("backup_interval_hours", 2),
            ))
            try:
                result = await asyncio.shield(job)
            except asyncio.CancelledError:
                # Finish the filesystem operation before releasing maintenance.
                await job
                raise
            return True, f"Server stopped. {result}"
        except Exception as error:
            print("Automatic backup failed:", error)
            return True, "Server stopped, but the automatic backup failed. Inspect the host logs; previous backups were retained."


def terminate():
    global server_process
    if is_running():
        server_process.terminate()


def is_someone_online():
    online_players = get_online_players()
    if online_players is None:
        return True
    return "No Players Connected" not in online_players


async def is_running_empty(time_period: int = 600) -> bool:
    start_time = last_start_time
    last_empty_time = None

    while is_running() and last_start_time == start_time:
        if is_someone_online():
            last_empty_time = None
        else:
            if last_empty_time is None:
                last_empty_time = time.time()
            elif time.time() - last_empty_time > time_period:
                return True

        await asyncio.sleep(60)

    return False


async def refresh_maps():
    catalog = await asyncio.to_thread(discover_maps, paths.SERVER_PATH)
    if server_config.get("official_maps") != catalog:
        server_config.set("official_maps", catalog)
    return catalog


async def get_maps():
    catalog = await refresh_maps()
    return {map_id: discover_worlds(paths.SERVER_PATH, map_id) for map_id in catalog}


def _creation_rcon(command):
    with MCRcon(env.RCON_IP, env.RCON_PASSWORD, port=env.RCON_PORT, timeout=5) as client:
        return client.command(command)


async def _wait_creation_ready(process, timeout):
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        try:
            result = await asyncio.to_thread(_creation_rcon, "ListPlayers")
            if result and "no response" not in result.lower():
                return True
        except (OSError, MCRconException):
            # Connection refusals and protocol errors are normal during startup.
            pass
        await asyncio.sleep(5)
    return False


async def _wait_creation_exit(process, timeout):
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        await asyncio.sleep(1)
    return process.poll() is not None


async def create_map(map_name, world_name=None, progress=None, startup_timeout=900, save_timeout=180, shutdown_timeout=120):
    global _creating_map, server_process
    progress = progress if progress is not None else SteamProgress()
    if is_running():
        return False, "Stop the server before creating a map."
    if is_updating():
        return False, "Server maintenance or map creation is already in progress."
    async with _update_lock:
        _creating_map = True
        process = None
        try:
            catalog = await refresh_maps()
            map_id = resolve_map(map_name, catalog)
            if world_name is None:
                world_name = next_world_name(paths.SERVER_PATH, map_id)
            validate_world_name(world_name)
            if world_name.casefold() == "default":
                return False, "The name default is reserved for existing worlds without an alternate save directory. Choose another name."
            root = Path(paths.SERVER_PATH) / "ShooterGame/Saved/SavedArks"
            # Windows directory names are case-insensitive. Reuse the actual
            # spelling across different map types and reject existing targets.
            if root.is_dir():
                for directory in root.iterdir():
                    if directory.name.casefold() == world_name.casefold():
                        world_name = directory.name
                        break
            world = World(map_id, world_name)
            save_path = world.save_path(paths.SERVER_PATH)
            if save_path.parent.exists():
                return False, "This world directory already exists. It will not be overwritten; inspect incomplete worlds on the host."
            if not Path(paths.SERVER_EXE_PATH).is_file():
                return False, "Initialize the server with !init before creating maps."
            progress.stage, progress.percent = f"Starting {map_id}", None
            _launch_server(map_id, world_name)
            process = server_process
            if not await _wait_creation_ready(process, startup_timeout):
                return False, "Map startup failed or timed out. Check the ARK log on the host."
            progress.stage = "Saving the new world"
            await asyncio.to_thread(_creation_rcon, "SaveWorld")
            deadline = time.monotonic() + save_timeout
            while not world.available(paths.SERVER_PATH):
                if process.poll() is not None or time.monotonic() >= deadline:
                    return False, "World save was not created in time. Check the ARK log on the host."
                await asyncio.sleep(2)
            progress.stage = "Stopping the creation server"
            await asyncio.to_thread(_creation_rcon, "DoExit")
            if not await _wait_creation_exit(process, shutdown_timeout):
                return False, "Server did not stop cleanly. Inspect the saved world on the host."
            if process.returncode != 0:
                return False, "Server exited abnormally. Inspect the saved world on the host."
            if not world.available(paths.SERVER_PATH):
                return False, "World save is missing or empty after shutdown."
            return True, f"{map_id} / {world_name} created and available. The selected map is unchanged. Use !set_map to select it."
        except ValueError as error:
            return False, str(error)
        except (OSError, MCRconException) as error:
            print("Map creation failed:", error)
            return False, "Map creation failed. Inspect the ARK log and shared RCON settings on the host."
        except Exception:
            return False, "Map creation failed during server communication. Check the ARK log on the host."
        finally:
            try:
                if process is not None and process.poll() is None:
                    process.terminate()
                    if not await _wait_creation_exit(process, 10):
                        process.kill()
                        await asyncio.to_thread(process.wait)
            finally:
                if process is not None and server_process is process:
                    server_process = None
                _creating_map = False


################# STEAM CMD HENDLERS #################
async def update(progress=None):
    return await _install_or_update(progress=progress)


async def init(progress=None):
    return await _install_or_update(initialize=True, progress=progress)


async def _install_or_update(initialize=False, progress=None):
    progress = progress if progress is not None else SteamProgress()
    global update_process
    if is_running():
        return False, "Server is running. Stop it before installing or updating."
    if is_updating():
        return False, "Server installation or update is already in progress."

    async with _update_lock:
        try:
            if initialize:
                if not env.RCON_PASSWORD:
                    return False, "Set RCON_PASSWORD in .env before initializing the server."
                for value in (env.NAME, env.PASSWORD, env.RCON_PASSWORD):
                    if any(char in value for char in "\r\n"):
                        return False, "Server name and passwords cannot contain line breaks."

            if not os.path.isfile(paths.STEAMCMD_PATH):
                return False, "SteamCMD was not found. Run setup.bat on the host first."
            os.makedirs(paths.SERVER_PATH, exist_ok=True)
            os.makedirs(paths.LOG_DIR, exist_ok=True)
            operation = "init" if initialize else "update"
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            log_file = os.path.join(paths.LOG_DIR, f"{operation}_{timestamp}.log")
            update_process = await asyncio.create_subprocess_exec(
                paths.STEAMCMD_PATH,
                "+force_install_dir", paths.SERVER_PATH,
                "+login", "anonymous",
                "+app_update", env.APP_ID, "validate", "+quit",
                cwd=os.path.dirname(paths.STEAMCMD_PATH),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                await asyncio.wait_for(
                    _stream_steamcmd(update_process, log_file, progress),
                    timeout=7200 if initialize else 900,
                )
            except asyncio.TimeoutError:
                update_process.kill()
                await update_process.wait()
                return False, "SteamCMD timed out. You can retry the operation."

            if update_process.returncode != 0:
                return False, f"SteamCMD failed. See the {operation} log on the host."
            if not os.path.isfile(paths.SERVER_EXE_PATH):
                return False, "SteamCMD finished but the server executable was not found. Check the paths and SteamCMD log."
            if (Path(paths.SERVER_PATH) / "Manifest_UFSFiles_Win64.txt").is_file():
                await refresh_maps()
            if initialize:
                progress.stage, progress.percent = "Preparing configuration", None
                _create_initial_config()
                return True, "Server installation validated and missing configuration files created. Existing settings and saves were preserved. Use !start to launch it."
            if progress.already_current:
                return True, "Server is already up to date."
            return True, "Server updated successfully."
        except OSError:
            return False, "Server installation/update could not complete. Check host paths, permissions and available disk space, then retry."
        finally:
            if update_process is not None and update_process.returncode is None:
                update_process.kill()
                await update_process.wait()
            update_process = None


async def _stream_steamcmd(process, log_file, progress):
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    with open(log_file, "wb") as log:
        while chunk := await process.stdout.read(4096):
            log.write(chunk)
            log.flush()
            progress.feed(decoder.decode(chunk))
        progress.feed(decoder.decode(b"", final=True))
        await process.wait()


def _create_initial_config():
    """Create missing ARK INIs without rewriting existing settings or saves."""
    directory = Path(paths.SERVER_PATH) / "ShooterGame/Saved/Config/WindowsServer"
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "GameUserSettings.ini": (
            "[ServerSettings]\n"
            "RCONEnabled=True\n"
            f"RCONPort={env.RCON_PORT}\n"
            f"ServerAdminPassword={env.RCON_PASSWORD}\n"
            f"ServerPassword={env.PASSWORD}\n\n"
            "[SessionSettings]\n"
            f"SessionName={env.NAME}\n"
        ),
        "Game.ini": "",
    }
    created = False
    for name, content in files.items():
        try:
            with (directory / name).open("x", encoding="utf-8") as output:
                output.write(content)
            created = True
        except FileExistsError:
            pass
    return created


################# RCON HANDLERS #################
async def wait_for_ready(timeout=300):
    start_time = time.time()

    while time.time() - start_time < timeout and is_running():
        players = get_online_players()

        if players is not None:
            return True

        await asyncio.sleep(5)

    return False


def get_online_players(timeout=1):
    try:
        socket.setdefaulttimeout(timeout)

        with MCRcon(env.RCON_IP, env.RCON_PASSWORD, port=env.RCON_PORT) as mcr:
            response = mcr.command("ListPlayers")
            if "no response" in response:
                print("RCON error when listing player:", response)
                return None
            response = re.sub(r',\s[^,\n]+$', '', response, flags=re.MULTILINE)
            return response
    except socket.timeout:
        return None
    except Exception as e:
        print("RCON error when listing player:", e)
        return None
    

def save():
    try:
        with MCRcon(env.RCON_IP, env.RCON_PASSWORD, port=env.RCON_PORT) as mcr:
            return mcr.command("SaveWorld")
    except Exception as e:
        print("RCON error when saving world:", e)
        return None
    

def exit():
    try:
        with MCRcon(env.RCON_IP, env.RCON_PASSWORD, port=env.RCON_PORT) as mcr:
            return mcr.command("DoExit")
    except Exception as e:
        print("RCON error when exitting sever:", e)
        return None