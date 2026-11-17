"""Verified rotating backups; restoration is deliberately manual."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import zipfile


STAMP = "%Y%m%dT%H%M%S%fZ"


def backup_world(server_root, backup_root, world, retention=4,
                 interval_hours=2, now=None):
    if isinstance(retention, bool) or not isinstance(retention, int) or retention < 1:
        raise ValueError("backup_count must be a positive integer.")
    interval_hours = float(interval_hours)
    if not math.isfinite(interval_hours) or interval_hours < 0:
        raise ValueError("backup_interval_hours must be a nonnegative number.")
    now = time.time() if now is None else now
    server_root = Path(server_root).resolve()
    backup_root = Path(backup_root).resolve()
    world_file = world.save_path(server_root)
    if not world.available(server_root):
        raise ValueError("The stopped world's save is missing or empty.")
    destination = backup_root / world.map_id / world.world_id
    if not destination.resolve().is_relative_to(backup_root):
        raise ValueError("Backup directory is outside the backup root.")
    destination.mkdir(parents=True, exist_ok=True)
    previous = []
    for path in destination.glob("backup_*.zip"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            created = datetime.strptime(path.stem.removeprefix("backup_"), STAMP).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        previous.append((created, path))
    previous.sort(key=lambda item: item[0])
    if previous and now - previous[-1][0] < interval_hours * 3600:
        return "Backup skipped: the minimum backup interval has not elapsed."
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime(STAMP)
    archive = destination / f"backup_{stamp}.zip"
    temporary = destination / f"backup_{stamp}.partial"
    write_world_archive(server_root, world, archive, now=now)
    # Only a completed, verified archive permits pruning old backups.
    for _, old in (previous + [(now, archive)])[:-retention]:
        try:
            old.unlink()
        except OSError as error:
            print("Backup retention cleanup failed:", error)
            return "Backup created and verified, but old-backup cleanup failed. Inspect the host."
    return f"Backup created for {world.map_id} / {world.world_id} (keeping up to {retention})."


def write_world_archive(server_root, world, archive, now=None, require_save=True):
    """Publish a verified archive without retention; also used for current snapshots."""
    server_root = Path(server_root).resolve()
    world_file = world.save_path(server_root)
    archive = Path(archive)
    temporary = archive.with_suffix(".partial")
    now = time.time() if now is None else now
    if require_save and not world.available(server_root):
        raise ValueError("World save is missing or empty.")
    if not world_file.parent.is_dir():
        raise ValueError("World directory is missing.")
    # Back up this complete world folder only; shared server state stays outside.
    world_root = world_file.parent.resolve()
    files = {}
    for path in world_file.parent.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(world_root):
            continue
        if path.is_file() or path.is_dir():
            files[path.relative_to(server_root).as_posix()] = path
    output = temporary.open("xb")
    try:
        with output, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
            for name, path in sorted(files.items()):
                bundle.write(path, name)
            bundle.writestr("backup_metadata.json", json.dumps({
                "map": world.map_id, "world": world.world_id,
                "created_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            }, indent=2))
        with zipfile.ZipFile(temporary) as bundle:
            damaged = bundle.testzip()
            if damaged is not None:
                raise zipfile.BadZipFile(f"Backup verification failed: {damaged}")
            if require_save and bundle.getinfo(world_file.relative_to(server_root).as_posix()).file_size == 0:
                raise zipfile.BadZipFile("World save is empty in the archive.")
        if archive.exists():
            raise FileExistsError("A backup already exists with this timestamp.")
        temporary.rename(archive)
    finally:
        temporary.unlink(missing_ok=True)
