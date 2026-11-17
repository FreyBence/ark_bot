"""Project-owned runtime paths, independent of environment variables and CWD."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SERVER_PATH = PROJECT_ROOT / "runtime/server"
SERVER_EXE_PATH = SERVER_PATH / "ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
STEAMCMD_PATH = PROJECT_ROOT / "runtime/steamcmd/steamcmd.exe"
CLUSTER_DIR = PROJECT_ROOT / "runtime/clusters"
LOG_DIR = PROJECT_ROOT / "logs"

BACKUP_DIR = PROJECT_ROOT / "backups"
