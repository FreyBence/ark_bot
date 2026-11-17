# ARK bot: Windows setup

Install **Python 3.12 or newer** from https://www.python.org/downloads/windows/.
Enable the Python launcher or add Python to PATH during installation.

From this folder, run:

```bat
setup.bat
```

This creates `.venv`, installs `requirements.txt`, downloads SteamCMD from
Valve, creates local runtime folders, and copies `.env.example` to `.env` if
needed. It preserves an existing `.env` and existing SteamCMD executable.
Python itself is a prerequisite, not downloaded by the script.

To also download the ARK: Survival Ascended dedicated server:

```bat
setup.bat --install-server
```

Stop the bot and server before using `--install-server`, including on reruns.
The download can take a while and needs sufficient free disk space. SteamCMD
runs in the console so its progress and errors remain visible. Rerunning this
option uses SteamCMD's update/validation process for the configured installation.
Setup does not start the bot or server automatically.

Default local layout:

```text
.venv/             Python and bot libraries
runtime/steamcmd/  Valve SteamCMD
runtime/server/    ARK binaries, configuration and saves
runtime/clusters/ Cluster directory
logs/              Bot update logs
```

These generated directories and `.env` are excluded from Git. Runtime locations
are defined in `paths.py`, relative to the repository directory, and are shared
by the bot and setup script. They are not read from `.env` or the process
environment. No existing server files are moved automatically. Keep backups of
server saves separately. Moving the repo does not make the Python virtual
environment portable: recreate `.venv` with setup on the new host.

## Finish configuration

1. Edit `.env`: set `DC_TOKEN`, `NAME`, `PASSWORD`, and `RCON_PASSWORD`.
   `APP_ID=2430930` targets ARK: Survival Ascended.
2. Enable Message Content Intent for your bot in the Discord Developer Portal.
   Invite it to your server with permission to view channels and send messages.
3. Configure ARK itself in
   `runtime/server/ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini`
   under the project directory. Preserve existing settings; add/update the appropriate keys:

   ```ini
   [ServerSettings]
   RCONEnabled=True
   RCONPort=27020
   ServerAdminPassword=your-rcon-password
   ServerPassword=your-game-password

   [SessionSettings]
   SessionName=ARK Server
   ```

   `ServerAdminPassword` must match `.env`'s `RCON_PASSWORD`, and `RCONPort`
   must match `RCON_PORT`. Match the session name and game password to `NAME`
   and `PASSWORD`. The bot currently displays these two `.env` values; it does
   not write them into ARK's configuration. Setup leaves ARK INI files alone.
4. Review `configs/server_config.json`, particularly the map, mods and port.
   Its `port` controls the bot's ARK launch argument; keep `.env`'s `PORT`
   consistent. Configure Windows firewall/router access for your chosen game
   ports as needed. Keep RCON restricted to the host or a trusted network.
5. Run `start_bot.bat`, then use `!start` in Discord.

If ARK reports missing native runtime components, install the required Microsoft
Visual C++ runtime from Microsoft's documentation:
https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
Setup does not install system runtimes or change firewall/router settings.

## Initialize the server through Discord

After `setup.bat`, configure `.env` and start the bot. Run `!init` as an ARK
admin to install the single server into `runtime/server`. Set a nonempty
`RCON_PASSWORD` first. The executable and other runtime paths are defined in
`paths.py`.

Initialization downloads through SteamCMD and creates missing
`GameUserSettings.ini` and `Game.ini` under
`ShooterGame/Saved/Config/WindowsServer`. Generated settings enable RCON and use
`.env` values for the session name, game password, RCON port and admin password.
Existing INIs and saved worlds are preserved; their settings must already match
`.env`. Initialization does not start the server, create a world or set up a
cluster. Use `!start` afterward with the existing map selection.

Every `!init` runs SteamCMD validation, even if the executable already exists.
SteamCMD repairs missing or damaged installation files before the bot creates
missing INIs. This can also update the server to the current build. No launch
or RCON readiness test is performed. Servers started outside the bot must be
checked and stopped manually on the host. Use `!update` for routine binary updates. Installation and updates share a lock that blocks Discord
starts. Initial downloads have a two-hour timeout and can be retried. Logs are
saved as `init_*.log` or `update_*.log` under the `logs` directory defined in `paths.py`. Firewall rules are not
changed.

Both `!init` and `!update` edit one Discord progress message every five seconds.
It shows elapsed time, the current SteamCMD stage, and a progress bar when a
percentage is available. Percentages describe the current stage, not the whole
operation. During quiet periods the message continues showing elapsed time.
Completion or failure replaces the progress display. SteamCMD output is flushed
to its log as it arrives, preserving received output on cancellation or timeout.
Discord progress edit failures do not stop the install/update operation.

## Discord permission levels

`configs/dc_config.json` is local to the host and ignored by Git. On first bot
startup, it is created automatically with empty `channel_ids` and
`admin_user_ids` lists and `admin_setup_completed: false`. Existing settings
are preserved. Back up this file manually to retain admin assignments.

Use `!permissions` to see your level. Existing everyday commands stay available
to players. `!add_admin @person` is restricted and requires an actual user mention
in a Discord server; names, raw IDs, roles and bot accounts are not accepted.

Before initial setup, the Discord owner and members with Manage Server or
Administrator permissions have initial ARK admin access. They can run
`!add_admin @person` to appoint the first internal admin (including themselves).
That command immediately persists `admin_setup_completed: true` together with
the user ID in `configs/dc_config.json`. From then on, **only** IDs in
`admin_user_ids` grant ARK admin access, even for the Discord owner. Only an
internal admin can add further admins. No restart is required.

Admin IDs apply to this bot/host across Discord servers. Channel restrictions
still apply. Discord roles no longer grant access after setup. An existing
nonempty `admin_user_ids` list also disables initial access for older configs.

The completion flag stays true even if the list becomes empty. To recover from
lockout, use host access (for example AnyDesk), put your numeric Discord user ID
in `admin_user_ids`, keep `admin_setup_completed` true, and restart the bot.
There is no automatic fallback to Discord permissions after setup.

Future administration commands can use the reusable check:

```python
from permissions import admin_only

@bot.command()
@admin_only()
async def create_instance(ctx):
    ...
```

The check uses discord.py's command check API:
https://discordpy.readthedocs.io/en/stable/ext/commands/commands.html#checks

## Download sources

If SteamCMD reports `Missing configuration` and exits with code 7 during
`setup.bat --install-server`, setup retries up to three attempts. This can
occur during SteamCMD's first run or self-update. If all attempts fail, keep
the full SteamCMD output for diagnosis; setup will still report failure.

- Valve SteamCMD documentation: https://developer.valvesoftware.com/wiki/SteamCMD
- Valve Windows bootstrap archive:
  https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
- ARK server setup reference: https://ark.wiki.gg/wiki/Server_setup

The repository contains setup code, not copies of third-party executables.

## Selecting mods

ARK admins can use `!mods`, `!add_mod 939688`, and `!remove_mod 939688`.
All three commands are restricted and appear only in the admin help section.
Use numeric mod IDs; names and URLs are not accepted. IDs are not looked up
against an online catalog, so administrators must supply the correct IDs.

Changes are saved immediately in the existing `mods` field of
`configs/server_config.json` as a JSON list of ID strings, for example
`"mods": ["939688", "1125041"]`. IDs are joined with commas only when building
the server launch argument. Adding a mod
appends it to the load order. Duplicate additions and removal of an unselected
mod leave the configuration unchanged. An empty selection omits `-mods` from
the launch arguments. Changes apply on the next ARK server start; these commands
do not restart the server, delete downloaded mods, or modify saved worlds.

## Creating maps

Run `!maps` to discover main-map candidates from the installed
`Manifest_UFSFiles_Win64.txt`. The catalog is saved as `official_maps` in the
existing `configs/server_config.json` and refreshed after successful installs
and updates and when listing/creating maps. The scan includes bundled maps under
`Content/Mods`, but excludes generated cells, caves and boss sublevels using
main-map filename/folder matching. This is a heuristic, not a guarantee that
unreleased content will start. No external mod-map registration is provided.

An ARK admin can run `!create_map TheIsland` for an automatic name (`UN_1`,
`UN_2`, etc.), or choose a name with `!create_map TheIsland main` or
`!create_map TheIsland theOther`. Stop the server first. Names must be 1-64 ASCII
letters, digits, underscores or hyphens, starting with a letter or digit.
Slashes, backslashes, traversal, spaces, Windows device names, and the reserved
legacy name `default` are rejected. Name matching is case-insensitive.

Creation launches the selected map with `?AltSaveDirectoryName=<world>` and the
shared INIs/mods. It waits up to 15 minutes for RCON readiness, requests a save,
waits up to three minutes for a nonempty world file, then requests exit and waits
up to two minutes for shutdown. It leaves the selected map and world unchanged.
Progress uses one Discord message. Competing lifecycle operations and selection
are blocked. External server processes must be stopped manually on the host.

The expected native save layout is:

```text
ShooterGame/Saved/SavedArks/
  main/TheIsland_WP/TheIsland_WP.ark
  theOther/TheIsland_WP/TheIsland_WP.ark
  TheIsland_WP/TheIsland_WP.ark  # existing legacy world, listed as default
```

`!maps` lists each detected map's created instance count and world names. Empty
directories and empty saves do not count. Named worlds are rediscovered from
files after a bot restart. No archive swapping or per-world INIs are involved.
Existing legacy worlds remain in place and launch without an alternate-directory
argument. Creation refuses an existing target world directory, including partial
creation remnants, rather than overwriting files. Inspect those on the host.

`!set_map TheIsland` selects the world automatically only when exactly one
exists. With several worlds, use `!set_map TheIsland main`. Selection remains
available to players and persists the `map` and `world` fields together in the
existing flat `server_config.json`. Use `!start` to launch the selected world;
normal starts require a nonempty save file.

File existence is not save-integrity verification. Interrupted creation retains
partial files for manual recovery. The native alternate-directory layout and
character/item/dino transfers between named worlds still require a live test on
this host. Settings stay shared and no cluster options are added; successful
cross-world transfer has not been assumed or simulated by copying player data.

Automatic world names choose the first unused `UN_<number>` for that map.
Existing target directories, including incomplete worlds and case variants,
are skipped. Names are discovered from disk, so numbering survives bot restarts.

## Automatic backups

After a clean normal stop (manual `!stop` or inactivity shutdown), the bot checks
when the actually running named world was last backed up. The first backup is
immediate; later backups require the configured interval to have elapsed. No
backup is made during map creation, failed startup, or forced termination.

The existing flat `configs/server_config.json` controls retention:

```json
"backup_count": 4,
"backup_interval_hours": 2
```

Each ZIP contains the entire selected world folder, including player/tribe files,
nested files and empty subdirectories, plus a small identification metadata file.
For example, `ShooterGame/Saved/SavedArks/main/TheIsland_WP/` is backed up for
`TheIsland / main`. Neighboring worlds, shared INIs, shared transfer/profile
files outside that folder, and bot configuration are excluded. Those shared files
remain a separate manual maintainer responsibility.

Archives are stored under `backups/<map>/<world>/`. Interval checks use archive
filenames and survive bot restarts. The new ZIP must pass CRC verification and
contain the nonempty world save before it is published and older backups are
pruned for that world only. A failed archive never causes old backups to be
removed. Cleanup failures are reported and may temporarily leave extra archives.
Starts and maintenance remain blocked until backup work finishes. The stop
message reports whether a backup was created, skipped or failed. Restoration is performed offline using `restore_backup.bat`, never through
Discord. No storage-check or backup-clear commands are provided.

## Offline restoration

Stop ARK and the Discord bot first. The script refuses to proceed when it detects
an ARK server or `dc_bot.py` running. From the project directory:

```bat
restore_backup.bat TheIsland main 2026-11-17
restore_backup.bat TheIsland main backup_20261117T140000000000Z.zip
restore_backup.bat TheIsland main current
restore_backup.bat TheIsland main current_1
```

Arguments are `<map> <world-name> <date>`. Map identifiers work with or without
`_WP`. Use `default` as the world name for the legacy default directory.
Date-only selection uses UTC dates; if several archives match, the command
fails and lists exact filenames to choose from. A full archive timestamp or
filename selects one precisely. `restore_backup.bat --help` shows usage.

The selected archive is verified and unpacked to a temporary sibling directory.
Only files from the requested world's folder are accepted. Before replacement,
the existing complete world folder is archived and verified as `current.zip`,
then `current_1.zip`, `current_2.zip`, etc., without overwriting previous snapshots.
These snapshots are not dated backups: they neither count toward retention nor
get deleted by it. Selecting `current` restores `current.zip` specifically; use
`current_N` to select another. Restoring a current snapshot creates another
current snapshot of the outgoing state. If no live folder exists, it restores
without making an outgoing snapshot.

The live folder is replaced rather than merged, so files absent from the backup
do not linger. Shared settings, transfer state outside the world folder, and
other worlds are untouched. If swapping directories fails, the script attempts
to restore the original directory. A host crash during the swap may require
manual recovery from the retained current ZIP or `.restore-old-*` directory.
The script never starts ARK or changes the selected world in the bot config.
