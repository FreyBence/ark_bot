"""Prepare Windows runtime dependencies without importing or starting the bot."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths

ROOT = paths.PROJECT_ROOT
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"


def install_steamcmd(destination):
    if destination.is_file():
        print("SteamCMD already exists; keeping it.")
        return
    if destination.name.lower() != "steamcmd.exe":
        raise ValueError("STEAMCMD_PATH must end in steamcmd.exe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading SteamCMD from Valve...")
    with tempfile.TemporaryDirectory(prefix="ark-bot-") as temp:
        archive = Path(temp) / "steamcmd.zip"
        with urllib.request.urlopen(STEAMCMD_URL, timeout=120) as response:
            with archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        with zipfile.ZipFile(archive) as bundle:
            # Valve's bootstrap archive contains steamcmd.exe. Extract only that
            # member, avoiding archive paths writing outside the chosen folder.
            with bundle.open("steamcmd.exe") as source:
                staged = Path(temp) / "steamcmd.exe"
                with staged.open("wb") as output:
                    shutil.copyfileobj(source, output)
        shutil.copyfile(staged, destination)
    print("SteamCMD installed.")


def prepare(install_server=False):
    env_path = ROOT / ".env"
    if not env_path.exists():
        # Exclusive creation avoids overwriting settings if setup runs twice.
        with env_path.open("x", encoding="utf-8") as output:
            output.write((ROOT / ".env.example").read_text(encoding="utf-8"))
        print("Created .env. Fill in your Discord token and server credentials.")
    else:
        print("Keeping existing .env settings.")

    # Match python-dotenv's default: process environment overrides .env values.
    settings = {**dotenv_values(env_path), **os.environ}
    steamcmd = paths.STEAMCMD_PATH
    server_path = paths.SERVER_PATH
    executable = paths.SERVER_EXE_PATH
    for path in (server_path, paths.LOG_DIR, paths.CLUSTER_DIR):
        path.mkdir(parents=True, exist_ok=True)
    install_steamcmd(steamcmd)

    if install_server:
        app_id = settings.get("APP_ID", "")
        if not app_id.isdecimal():
            raise ValueError("APP_ID must be a numeric Steam application ID in .env.")
        print("Installing/updating ARK. Keep the server stopped until this finishes.")
        command = [str(steamcmd), "+force_install_dir", str(server_path),
                   "+login", "anonymous", "+app_update", app_id, "validate", "+quit"]
        for attempt in range(3):
            try:
                subprocess.run(command, cwd=steamcmd.parent, check=True)
                break
            except subprocess.CalledProcessError as error:
                # SteamCMD can exit with 7 after a bootstrap update or a
                # transient "Missing configuration" failure on first install.
                if error.returncode != 7 or attempt == 2:
                    raise
                print("SteamCMD exited with code 7; retrying installation "
                      f"({attempt + 2}/3)...", flush=True)
        if not executable.is_file():
            raise RuntimeError("SteamCMD finished but SERVER_EXE_PATH was not found. "
                               "Check its output and the paths in paths.py.")
    elif not executable.is_file():
        print("ARK is not installed at SERVER_EXE_PATH. Run setup.bat --install-server.")
    print("Setup finished. See README.md for credentials, RCON and starting the bot.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-server", action="store_true",
                        help="Download/update ARK through SteamCMD; stop the server first.")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This installer targets Windows hosts.")
    try:
        prepare(args.install_server)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
