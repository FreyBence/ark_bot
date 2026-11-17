"""Offline world restoration, with verified current snapshots before replacement."""
import argparse
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths
from backups import STAMP, write_world_archive
from worlds import World, validate_world_name


def require_offline():
    # Require the bot stopped too: its automatic starts/backups must not race us.
    command = (
        "$ErrorActionPreference='Stop'; "
        "$busy = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -ieq 'ArkAscendedServer.exe' -or "
        "($_.Name -match '^python(w)?(\\d+(\\.\\d+)?)?\\.exe$' -and "
        "$_.CommandLine -match 'dc_bot\\.py') }; "
        "if ($busy) { Write-Output 'busy' } else { Write-Output 'offline' }"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=True)
    if result.stdout.strip() != "offline":
        raise RuntimeError("Stop the ARK server and dc_bot.py before restoring a backup.")


def backup_directory(backup_root, world):
    root = Path(backup_root).resolve()
    directory = root / world.map_id / world.world_id
    if not directory.resolve().is_relative_to(root):
        raise ValueError("Backup directory escapes the backup root.")
    return directory


def choose_backup(directory, date):
    if re.fullmatch(r"current(?:_[1-9][0-9]*)?(?:\.zip)?", date):
        candidates = [directory / (date if date.endswith(".zip") else date + ".zip")]
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        day = datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d")
        candidates = sorted(directory.glob(f"backup_{day}T*.zip"))
    else:
        stamp = date.removeprefix("backup_").removesuffix(".zip")
        datetime.strptime(stamp, STAMP)
        candidates = [directory / f"backup_{stamp}.zip"]
    candidates = [p for p in candidates if p.is_file() and not p.is_symlink()]
    if not candidates:
        raise ValueError("No matching backup found. Check the filenames in the world's backup folder.")
    if len(candidates) != 1:
        raise ValueError("Several backups match this UTC date. Supply the full timestamp or filename: "
                         + ", ".join(p.name for p in candidates))
    return candidates[0]


def extract_world(archive, stage, server_root, world):
    prefix = world.save_path(server_root).parent.relative_to(Path(server_root).resolve()).as_posix() + "/"
    seen = set()
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise zipfile.BadZipFile("Selected backup failed CRC verification.")
        metadata = json.loads(bundle.read("backup_metadata.json"))
        if metadata.get("map") != world.map_id or metadata.get("world") != world.world_id:
            raise ValueError("Backup metadata does not match the requested map and world.")
        for member in bundle.infolist():
            name = member.filename
            if name == "backup_metadata.json":
                continue
            if not name.startswith(prefix) or "\\" in name:
                raise ValueError("Backup contains files outside the requested world folder.")
            relative = name[len(prefix):]
            parts = PurePosixPath(relative).parts
            if not parts or any(part in (".", "..") for part in parts):
                raise ValueError("Unsafe archive path.")
            for part in parts:
                if (re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((".", " "))
                        or part.split(".", 1)[0].upper() in
                        {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
                    raise ValueError("Archive contains an invalid Windows filename.")
            key = "/".join(parts).casefold()
            if key in seen or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Archive contains duplicate paths or symbolic links.")
            seen.add(key)
            target = stage.joinpath(*parts)
            if not target.resolve().is_relative_to(stage.resolve()):
                raise ValueError("Archive path escapes the staging directory.")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    if archive.name.startswith("backup_"):
        save = stage / (world.map_id + ".ark")
        if not save.is_file() or save.stat().st_size == 0:
            raise ValueError("Selected backup has no nonempty world save.")


def restore_world(server_root, backup_root, world, date, offline_check=require_offline):
    server_root = Path(server_root).resolve()
    target = world.save_path(server_root).parent
    directory = backup_directory(backup_root, world)
    # Resolve the source before allocating a current name; current may itself be
    # the requested source and must remain unchanged.
    archive = choose_backup(directory, date)
    offline_check()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".restore-stage-", dir=target.parent) as temp:
        stage = Path(temp)
        extract_world(archive, stage, server_root, world)
        offline_check()
        current = None
        if target.exists():
            if not target.is_dir():
                raise ValueError("Existing world path is not a directory.")
            number = 0
            while True:
                candidate = directory / ("current.zip" if number == 0 else f"current_{number}.zip")
                if not candidate.exists() and not candidate.with_suffix(".partial").exists():
                    break
                number += 1
            write_world_archive(server_root, world, candidate, require_save=False)
            current = candidate
        offline_check()
        rollback = target.parent / (".restore-old-" + uuid.uuid4().hex)
        # Validate all filesystem mutation targets before moving/removing trees.
        for candidate in (target, stage, rollback):
            if not candidate.resolve().is_relative_to(server_root):
                raise ValueError("Restore target is outside the server installation.")
        moved_old = False
        try:
            if target.exists():
                target.rename(rollback)
                moved_old = True
            stage.rename(target)
        except BaseException:
            if moved_old and not target.exists():
                rollback.rename(target)
            raise
        if moved_old:
            try:
                shutil.rmtree(rollback)
            except OSError:
                print(f"Restored successfully, but the old staging folder needs manual cleanup: {rollback}")
    return archive, current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", help="Map identifier, e.g. TheIsland or TheIsland_WP")
    parser.add_argument("world", help="Named world, e.g. main; default means the legacy world")
    parser.add_argument("date", help="UTC YYYY-MM-DD, full backup timestamp/filename, current, or current_N")
    args = parser.parse_args()
    try:
        validate_world_name(args.world)
        map_id = args.map if args.map.lower().endswith("_wp") else args.map + "_WP"
        # Resolve names from backup folders, so restore works even if ARK is damaged.
        matches = [p.name for p in paths.BACKUP_DIR.iterdir() if p.name.casefold() == map_id.casefold()]
        if len(matches) != 1:
            raise ValueError("Map backup directory was not found.")
        map_id = matches[0]
        worlds = [p.name for p in (paths.BACKUP_DIR / map_id).iterdir() if p.name.casefold() == args.world.casefold()]
        if len(worlds) != 1:
            raise ValueError("World backup directory was not found.")
        world = World(map_id, worlds[0])
        archive, current = restore_world(paths.SERVER_PATH, paths.BACKUP_DIR, world, args.date)
        print(f"Restored {world.map_id} / {world.world_id} from {archive.name}.")
        print(f"Previous state preserved as {current.name}." if current else "No previous world folder existed.")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f"Restore failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
