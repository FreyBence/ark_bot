# ARK Bot

A Discord bot for managing one ARK: Survival Ascended server with multiple named
worlds, shared settings, and automatic backups.

## Setup

Requires Windows and Python 3.12 or newer, available on PATH or through `py`.

1. Run `setup.bat` to install bot dependencies and SteamCMD.
2. Fill in `.env`: Discord token, server name, game password, and a nonempty
   RCON password. Keep the other values unless your setup requires changes.
3. Enable **Message Content Intent** in the Discord Developer Portal. Invite the
   bot with permission to view channels and send messages.
4. Review `configs/server_config.json` for ports, mods, and server options.
5. Run `start_bot.bat`.

In Discord, complete the first setup:

```text
!add_admin @YourDiscordUser
!init
!maps
!create_map TheIsland main
!set_map TheIsland main
!start
```

The first `!add_admin` requires Discord's Manage Server or Administrator
permission, or server ownership. Afterward, only explicitly added ARK admins
have admin access. Use `!permissions` to check your level.

`!init` installs or repairs ARK and creates missing INI files. Existing settings
and saves are preserved. For existing INIs, ensure `RCONEnabled=True`,
`RCONPort` matches `.env`'s `RCON_PORT`, and `ServerAdminPassword` matches
`RCON_PASSWORD`. Configure the host firewall and router for your game ports.

## Using the bot

Type `!help` in Discord to see the commands available to you. Admins see the
extended help with administration commands.

## Files

| Location | Contents |
| --- | --- |
| `.env` | Credentials and network settings |
| `configs/server_config.json` | Server options, selected world, mods, backup settings |
| `configs/dc_config.json` | Local channel and admin assignments; created automatically |
| `runtime/server/` | ARK installation and saves |
| `runtime/server/ShooterGame/Saved/Config/WindowsServer/` | Shared ARK INI files |
| `logs/` | Installation and update logs |
| `backups/<map>/<world>/` | World backup archives |

Runtime paths are defined in `paths.py`. Credentials, Discord assignments,
runtime files, logs, and backups are ignored by Git. Keep a separate copy of
`.env` and `configs/dc_config.json` when moving hosts.

## Backups and restoration

After a clean stop, the bot backs up the complete world folder if no backup
exists or the minimum interval has elapsed. Defaults in `server_config.json`
are `backup_count: 4` per world and `backup_interval_hours: 2`. Old backups are
removed only after the new archive is verified. Shared INIs and transfer data
outside the world folder are excluded.

To restore, stop **both ARK and the bot**, then run:

```bat
restore_backup.bat TheIsland main 2026-11-17
```

Arguments are `<map> <world> <date>`. Dates use UTC. If several backups match,
use the exact filename shown by the script instead of the date.

Before replacement, the existing world is saved as `current.zip`, then
`current_1.zip`, etc. These snapshots are excluded from automatic retention
and can also be restored:

```bat
restore_backup.bat TheIsland main current
restore_backup.bat TheIsland main current_1
```

Restoration replaces only the world folder and leaves the server stopped.
