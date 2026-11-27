# Game saves

Game saves and settings are kept in one archive, built with [Ludusavi](https://github.com/mtkennerly/ludusavi).
It knows where thousands of games keep their saves (from PCGamingWiki), backs them up per
game, and restores them with one command. `scripts/game-saves.py` sets it up for two jobs:

- **This PC**: the live saves, backed up regularly, so unfinished games survive a reinstall
- **Old drive copies**: a folder holding a previous system drive (with its `Users` folder), imported once,
  so the copy can be deleted afterwards

Software, Windows settings and drivers aren't kept: those get reinstalled.

## Install

```shell
scoop install extras/ludusavi
```

## The archive

The archive holds everything personal, so it lives outside this repo. Put it on a drive other
than C:, or in a synced folder, and point `GAME_SAVES_HOME` at it:

```shell
[Environment]::SetEnvironmentVariable('GAME_SAVES_HOME', 'D:\game-saves', 'User')
```

Layout:

- **`custom-games.json`** — games Ludusavi doesn't know, and folders that aren't saves (see
  below). The one file you edit
- **`live/`** — this PC's config and backups
- **`sources/<name>/`** — one old drive copy each: its config, backups and `source.json`

Each source backs up into its own folder. So a backup of this PC can never rotate an old
drive's saves out under Ludusavi's retention limits, even for the same game. The `config/`
folders are generated on every run from Ludusavi's defaults plus `custom-games.json`: never
edit them by hand.

## This PC

```shell
uv run python scripts/game-saves.py init-live --installs C:/games   # launcher roots plus your install folders
uv run python scripts/game-saves.py preview live                     # what a backup would copy, nothing written
uv run python scripts/game-saves.py backup live
```

## An old drive copy

```shell
uv run python scripts/game-saves.py add-source old-pc-2020 --drive E:/old-c --installs E:/old-c/_games
uv run python scripts/game-saves.py gaps old-pc-2020      # save-like folders nothing covers yet
uv run python scripts/game-saves.py preview old-pc-2020
uv run python scripts/game-saves.py backup old-pc-2020
```

Ludusavi scans the old drive as a Windows drive, at its default folder locations, plus its
Steam install and any install folders you name. It also always scans this PC. The script
keeps those parts out: an old drive's config ignores everything outside the drive's folder,
and the live registry. `preview` warns if anything from outside slips through.

`gaps` lists the folders where games usually save (`Saved Games`, `Documents`,
`Documents\My Games` and the three AppData folders, in every old profile) that nothing
covers yet. Work through it until it reports none: each folder either becomes a custom game
or goes in `notSaves`.

## custom-games.json

```json
{
  "games": [
    {"name": "Defender's Quest", "files": ["<winAppData>/LevelUpLabs/DefendersQuest"]},
    {"name": "Grim Dawn", "integration": "extend", "files": ["<winDocuments>/My Games/Grim Dawn_BAK"]},
    {"name": "Steam emulator saves", "files": ["{drive}/Users/Public/Documents/Steam/CODEX"]}
  ],
  "notSaves": ["AppData/Roaming/Autodesk", "Documents/Fax"]
}
```

- **Placeholders**: Ludusavi's `<home>`, `<winAppData>`, `<winLocalAppData>`,
  `<winLocalAppDataLow>` and `<winDocuments>` resolve inside an old drive's profiles too.
- **`{drive}`**: the drive root (C: for this PC). Use it where a placeholder would point at this
  PC instead, like the Public folder (`<winPublic>` always means this PC's).
- **`integration`**: `extend` adds paths to a game Ludusavi already knows. The default,
  `override`, defines a new game, and replaces a known game of the same name.
- **`notSaves`**: profile-relative folders that `gaps` stops reporting.

## Restoring

Backups keep each file's original path. An old drive's config adds restore redirects:

- **Old profile**: restores to your profile
- **Old Public, ProgramData and Steam**: restore to this PC's

Saves from inside game install folders keep their old path, so redirect those by hand or copy
them. Always preview first:

```shell
ludusavi --config "$env:GAME_SAVES_HOME\sources\old-pc-2020\config" restore --preview "<game>"
ludusavi --config "$env:GAME_SAVES_HOME\sources\old-pc-2020\config" restore "<game>"
```
