import json
import os
from typing import Any, Dict
from worlds import validate_world_name



class ConfigManager:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.save()
            return

        with open(self.path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)


    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any, autosave: bool = True) -> None:
        self.data[key] = value
        if autosave:
            self.save()

    def update(self, updates: Dict[str, Any], autosave: bool = True) -> None:
        self.data.update(updates)
        if autosave:
            self.save()
    

class ServerConfigManager(ConfigManager):
    def __init__(self, path: str = "configs\\server_config.json"):
        super().__init__(path)

    @staticmethod
    def normalize_mod_id(mod_id: str) -> str:
        value = str(mod_id).strip()
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            raise ValueError("Mod ID must be a positive number, for example 939688.")
        return str(int(value))

    def get_mods(self) -> list[str]:
        # Preserve configured load order; format IDs only for the launch argument.
        mods = []
        for value in self.get("mods", []):
            mod_id = self.normalize_mod_id(value)
            if mod_id not in mods:
                mods.append(mod_id)
        return mods

    def add_mod(self, mod_id: str) -> bool:
        mod_id = self.normalize_mod_id(mod_id)
        mods = self.get_mods()
        if mod_id in mods:
            return False
        mods.append(mod_id)
        self.set("mods", mods)
        return True

    def remove_mod(self, mod_id: str) -> bool:
        mod_id = self.normalize_mod_id(mod_id)
        mods = self.get_mods()
        if mod_id not in mods:
            return False
        mods.remove(mod_id)
        self.set("mods", mods)
        return True

    def build_server_args(self, map_id: str | None = None, world_id: str | None = None) -> list[str]:
        cfg = self.data
        selected_map = map_id if map_id is not None else cfg["map"]
        selected_world = validate_world_name(world_id if world_id is not None else cfg.get("world", "default"))
        if selected_world != "default":
            selected_map += f"?AltSaveDirectoryName={selected_world}"

        args = [
            selected_map,
            f"-port={cfg['port']}",
            f"-WinLiveMaxPlayers={cfg['max_players']}",
            # f"-clusterid={cfg['cluster_id']}",
            f"-ServerPlatform={cfg['platform']}",
        ]

        mods = self.get_mods()
        if mods:
            args.append(f"-mods={','.join(mods)}")

        if not cfg.get("battleye", True):
            args.append("-NoBattlEye")

        if cfg.get("log"):
            args.append("-log")

        if cfg.get("servergamelog"):
            args.append("-servergamelog")

        return [arg for arg in args if arg is not None]


server_config = ServerConfigManager()
dc_config = ConfigManager("configs\\dc_config.json")
