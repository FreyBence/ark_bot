import json
import os
from typing import Any, Dict

# import env


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

    def build_server_args(self) -> list[str]:
        cfg = self.data

        args = [
            cfg["map"],
            f"-port={cfg['port']}",
            f"-WinLiveMaxPlayers={cfg['max_players']}",
            f"-mods={cfg['mods']}",
            # f"-clusterid={cfg['cluster_id']}",
            # f"-ClusterDirOverride={env.CLUSTER_DIR}",
            f"-ServerPlatform={cfg['platform']}",
        ]

        if not cfg.get("battleye", True):
            args.append("-NoBattlEye")

        if cfg.get("log"):
            args.append("-log")

        if cfg.get("servergamelog"):
            args.append("-servergamelog")

        return [arg for arg in args if arg is not None]


server_config = ServerConfigManager()
dc_config = ConfigManager("configs\\dc_config.json")
