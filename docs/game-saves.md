# Game saves

Game saves and settings are kept in one archive, built with [Ludusavi](https://github.com/mtkennerly/ludusavi).
It knows where thousands of games keep their saves (from PCGamingWiki), backs them up per
game, and restores them with one command. `scripts/game-saves.py` organizes the archive into
one **target** per gaming root:

- **Old drive copies**: a folder holding a previous system drive (with its `Users` folder),
  imported once, so the copy can be deleted afterwards
- **The system drive**: this PC's profile, registry and launchers, plus any install folders on it
- **Other drives**: install folders there, for games that keep saves next to the game

Steam and GOG keep cloud saves for many games, but not all old games support them, so the
archive keeps a copy anyway. Software, Windows settings and drivers aren't kept: those get
reinstalled.

## Install

```shell
scoop install extras/ludusavi
```

## The archive

The archive holds everything personal, so it lives outside this repo, on a disk other than C:.
Point `GAME_SAVES_HOME` at it:

```shell
[Environment]::SetEnvironmentVariable('GAME_SAVES_HOME', 'D:\_backups\game-saves', 'User')
```

Layout:

- **`custom-games.json`** — games Ludusavi doesn't know, and folders that aren't saves (see
  below). The one file you edit
- **`<target>/target.json`** — what the target is: its kind, its root (`scope`) and its
  install folders
- **`<target>/config/`** — generated on every run from Ludusavi's defaults plus
  `custom-games.json`. Never edit it by hand
- **`<target>/backup/`** — Ludusavi's backups, one folder per game

Each target backs up only files under its own root, into its own folder. So no backup can
rotate another root's saves out under Ludusavi's retention limits, even for the same game. A
target skips the folders of every other target inside its root, so an old drive copy kept on
C: stays out of the C: target. Only the system-drive target keeps registry saves.

## Setting up targets

```shell
uv run python scripts/game-saves.py add-old-drive old-pc --drive E:/old-c --installs E:/old-c/_games
uv run python scripts/game-saves.py add-live c --scope C:/ --installs C:/games
uv run python scripts/game-saves.py add-live d --scope D:/ --installs D:/_games
```

- **An old drive** is scanned as a Windows drive at its default folder locations, plus its
  Steam install and the install folders you name.
- **A live target** uses the launcher folders Ludusavi detects (Steam, GOG, Microsoft Store)
  that are on its root, plus the install folders you name.

Ludusavi always scans this PC too. The script keeps that out: each target ignores every path
outside its root, and an old drive's target ignores the live registry. `preview` warns if
anything from outside slips through.

## Backing up

```shell
uv run python scripts/game-saves.py gaps old-pc       # old drives: save-like folders nothing covers yet
uv run python scripts/game-saves.py preview old-pc    # what a backup would copy, nothing written
uv run python scripts/game-saves.py backup old-pc     # back up, then verify
uv run python scripts/game-saves.py verify old-pc     # verify again, any time
```

`gaps` lists the folders where games usually save (`Saved Games`, `Documents`,
`Documents\My Games` and the three AppData folders, in every old profile) that nothing
covers yet. Work through it until it reports none: each folder either becomes a custom game
or goes in `notSaves`.

`verify` is the "saves are safe" check. It re-scans the target, then checks two things for
every save file the root holds now: the backup has it with the same SHA-1, and the stored copy
still matches. A game passes only if every file does. `backup` runs it at the end, and any
command takes game names to limit it to those.

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
- **`{drive}`**: the old drive's root, or the system drive for live targets. Use it where a
  placeholder would point at this PC instead, like the Public folder (`<winPublic>` always
  means this PC's).
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
ludusavi --config "$env:GAME_SAVES_HOME\old-pc\config" restore --preview "<game>"
ludusavi --config "$env:GAME_SAVES_HOME\old-pc\config" restore "<game>"
```
