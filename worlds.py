"""Installed map discovery and save locations; no per-world gameplay settings."""
from dataclasses import dataclass
from pathlib import Path
import re


def discover_maps(server_path):
    manifest = Path(server_path) / "Manifest_UFSFiles_Win64.txt"
    found = set()
    with manifest.open(encoding="utf-8-sig") as source:
        for line in source:
            asset = line.split("\t", 1)[0].strip()
            match = re.fullmatch(
                r"ShooterGame/Content/(?:Maps|Mods)/([A-Za-z0-9_]+)/([A-Za-z0-9_]+)_WP\.umap", asset)
            if match and match[1].removesuffix("SubMaps").casefold() == match[2].casefold():
                found.add(match[2] + "_WP")
    if not found:
        raise ValueError("No main-map candidates were found in the installed manifest. Run !init or inspect the host.")
    return sorted(found, key=str.casefold)


def resolve_map(name, catalog):
    def key(value):
        return value.strip().casefold().removesuffix("_wp").replace(" ", "")
    for map_id in catalog:
        if key(map_id) == key(name):
            return map_id
    raise ValueError("Map not found in this installation. Use !maps to list detected maps.")


def validate_world_name(name):
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name) is None:
        raise ValueError("World names must be 1-64 letters, digits, underscores or hyphens, starting with a letter or digit. Paths are not allowed.")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10))
    if name.upper() in reserved:
        raise ValueError("That world name is reserved by Windows.")
    return name


@dataclass(frozen=True)
class World:
    map_id: str
    world_id: str = "default"

    def save_path(self, server_path):
        validate_world_name(self.world_id)
        if re.fullmatch(r"[A-Za-z0-9_]+_WP", self.map_id) is None:
            raise ValueError("Invalid map identifier.")
        root = Path(server_path) / "ShooterGame/Saved/SavedArks"
        directory = root if self.world_id == "default" else root / self.world_id
        result = directory / self.map_id / (self.map_id + ".ark")
        if not result.resolve().is_relative_to(root.resolve()):
            raise ValueError("World save path is outside the server save directory.")
        return result

    def available(self, server_path):
        save = self.save_path(server_path)
        return save.is_file() and save.stat().st_size > 0


def discover_worlds(server_path, map_id):
    worlds = []
    legacy = World(map_id)
    if legacy.available(server_path):
        worlds.append(legacy)
    root = Path(server_path) / "ShooterGame/Saved/SavedArks"
    if root.is_dir():
        for directory in root.iterdir():
            if not directory.is_dir() or directory.is_symlink() or directory.name.casefold() == "default":
                continue
            try:
                world = World(map_id, validate_world_name(directory.name))
                if world.available(server_path):
                    worlds.append(world)
            except ValueError:
                continue
    return sorted(worlds, key=lambda world: world.world_id.casefold())


def next_world_name(server_path, map_id):
    root = Path(server_path) / "ShooterGame/Saved/SavedArks"
    entries = {entry.name.casefold(): entry for entry in root.iterdir()} if root.is_dir() else {}
    number = 1
    while True:
        name = f"UN_{number}"
        existing = entries.get(name.casefold())
        if existing is None:
            return name
        if existing.is_dir() and not existing.is_symlink() and not (existing / map_id).exists():
            return existing.name
        number += 1


def select_world(map_id, world_name, worlds):
    if not worlds:
        raise ValueError("This map has no created worlds. An admin must use !create_map first.")
    if world_name is None:
        if len(worlds) != 1:
            raise ValueError("There are multiple instances. Check !maps and use !set_map <map> <world>.")
        return worlds[0]
    validate_world_name(world_name)
    for world in worlds:
        if world.world_id.casefold() == world_name.casefold():
            return world
    raise ValueError("That world is unavailable. Check !maps for the created world names.")
