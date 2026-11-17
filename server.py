import asyncio
import os
import re
import socket
import subprocess
import time
from datetime import datetime

from mcrcon import MCRcon

import env
from config import server_config

################# PROCESS HANDLERS #################
server_process = None
update_process = None
last_start_time = time.time()

def is_running():
    global server_process
    if server_process is None:
        return False
    return server_process.poll() is None


def is_updating():
    global update_process
    if update_process is None:
        return False
    return update_process.returncode is None


def start():
    global last_start_time
    last_start_time = time.time()

    global server_process
    server_process = subprocess.Popen(
        [env.SERVER_EXE_PATH] + server_config.build_server_args(),
        cwd=os.path.dirname(env.SERVER_EXE_PATH)
    )


async def stop(timeout = 60):
    global server_process
    save()
    await asyncio.sleep(10)
    exit()
    await asyncio.sleep(10)

    start = time.time()
    while time.time() - start < timeout:
        if not is_running():
            break
        await asyncio.sleep(1)
    
    terminate()


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


################# STEAM CMD HENDLERS #################
async def update():
    global update_process
    if is_running():
        return False, "Server is running. Stop it before updating."

    if is_updating():
        return False, "Server is already upating."

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = f"{env.LOG_DIR}/update_{timestamp}.log"

    update_process = await asyncio.create_subprocess_exec(
        env.STEAMCMD_PATH,
        "+force_install_dir", env.SERVER_PATH,
        "+login", "anonymous",
        "+app_update", env.APP_ID, "validate",
        "+quit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            update_process.communicate(),
            timeout=900
        )
    except asyncio.TimeoutError:
        update_process.kill()
        update_process = None
        return False, "Update timed out. Please contact an administrator."

    output = stdout.decode(errors="ignore") + "\n" + stderr.decode(errors="ignore")

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(output)

    if update_process.returncode != 0:
        update_process = None
        return False, "Update failed. Please contact an administrator."

    if "already up to date" in output.lower():
        update_process = None
        return True, "Server is already up to date."

    update_process = None
    return True, "Server updated successfully."


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