# Retiring a drive

How to empty a Windows drive so it can be deleted or wiped without losing anything personal.
"Drive" means any root with a `Users` folder: a copy of a previous system drive kept as a
folder, another disk, or this PC's own C: before a reinstall. Game saves and settings are
kept; software, Windows settings and drivers aren't, since they get reinstalled. Credentials
are never kept.

The order matters: saves first, then other personal data, then a check of everything that's
left. The first drive copy done this way skipped that last step, and missed chat histories,
unsaved notes and notebook backups that apps keep in AppData.

## 0. Get at it, read-only

- **A folder copy**: nothing to do.
- **A disk Windows shows as offline** (`Get-Disk`, "Offline by policy"): bring it online
  read-only from an admin shell first, so nothing can change it, then give it a letter:
  `Set-Disk <n> -IsReadOnly $true; Set-Disk <n> -IsOffline $false`.
- **A drive that holds other drives**: an old system disk often contains an older copy kept
  as a folder (`E:\_old-c`) and `Windows.old` from a reinstall. Check a nested copy against
  any copy already salvaged: `robocopy <a> <b> /L /E /XJ /NJH /NJS /NDL /NC /NS /FP` in
  both directions lists every file that differs, so an empty list means it's the same. Make
  `Windows.old` a target of its own if it has a `Users` folder. Then pass both to `--skip`
  (`add-old-drive ... --skip E:/_old-c E:/Windows.old`, and the same on `leftovers`), so
  neither is scanned twice.
- **This PC's C:**: running apps hold some files open. Close chat apps, mail and browsers
  first, or expect a few files to be skipped (the copy says which).

Then record what software it had. It's names and versions only, for reinstalling later:

```shell
python <skill>/scripts/personal-data.py inventory E:/old-c --out D:/_backups/old-drives/old-pc --installs E:/old-c/_games
```

## 1. Game saves

With [game-saves.md](game-saves.md):

```shell
python <skill>/scripts/game-saves.py add-old-drive old-pc --drive E:/old-c --installs E:/old-c/_games
python <skill>/scripts/game-saves.py gaps old-pc       # repeat, with custom-games.json, until it reports 0
python <skill>/scripts/game-saves.py backup old-pc     # ends with verify: every save file, by SHA-1
python <skill>/scripts/game-saves.py index old-pc      # games.md: when and how each game was played
```

For this PC's own drives, use `add-live` targets instead (`add-live c --scope C:/`, `add-live d
--scope D:/ --installs D:/_games`). `gaps` works on them too, for the install folders.

Ludusavi misses saves inside install folders when it doesn't know the game, or knows it only
from a store install. That's common for downloaded releases, which keep saves in `save`,
`SaveData`, `storage` or `Profile\IGGGAMES`. On the first data drive checked, 16 of 34
installs had saves or emulator data in their own folder, and Ludusavi found 3 of them by
itself. `gaps` lists the rest.

`gaps` only looks where games usually save. Step 3 catches the rest, such as game screenshots
or a game folder kept under an odd name. Add those to `custom-games.json`, often as `extend` on
a game Ludusavi already knows, back up just those games, and verify again.

## 2. Other personal data

```shell
python <skill>/scripts/personal-data.py copy E:/old-c --dest D:/_backups/old-drives/old-pc/personal
```

For every profile on the drive, it copies:

- **The user folders**: Desktop, Documents, Pictures, Music, Videos and the rest, plus code
  folders
- **Personal data apps keep in AppData**: Skype and Pidgin chat history, unsaved Notepad++
  tabs, OneNote backups, Outlook and Thunderbird mail, Sticky Notes, MusicBee and Winamp
  libraries and playlists, browser bookmarks and history
- **Dotfiles and `NTUSER.DAT`**: the old registry, for games that keep saves there

It keeps the drive-relative paths and the files' dates, then checks every copied file against
its original by SHA-1. Running it again copies only what's new.

It never copies credential stores: `.ssh`, password databases, browser saved logins, and
chat clients' account files. They go with the drive: old keys and passwords are retired, not
carried to a new disk. Step 3 lists the ones it found, so it's clear what goes.

## 3. What's left

```shell
python <skill>/scripts/personal-data.py leftovers E:/old-c --dest D:/_backups/old-drives/old-pc/personal `
    --saves D:/_backups/game-saves/old-pc/backup --installs E:/old-c/_games
```

It walks every file and sets aside four kinds:

- what's in either backup
- software: Program Files, ProgramData, Windows, the game install folders, and app installs
  inside profiles
- caches
- credential stores, which are listed separately

What's left is listed by folder, with counts of personal-looking file types: documents,
images, audio and video, archives, mail and chat databases, code, CAD. Read every line. For
anything personal, add its folder to `APP_DATA` in `scripts/personal-data.py` (or to the
game-save archive) and rerun `copy`. Then rerun `leftovers` until only app settings, caches
and cloud clients' local state remain.

Look closely at:

- **Chat apps**: their history is often the only copy left, once the service shuts down
  (Skype, in 2025)
- **Editors and note apps**: unsaved-tab backups, notebook backups, scratch files
- **Image folders inside game data**: screenshots
- **Cloud clients** (SpiderOak, Dropbox, OneDrive): only their local state. The files are in
  the cloud, or in the sync folder if it was on this drive

## 4. Record it

Write `decisions.md` in the drive's folder by hand. It holds what the drive was (which
system, which years), what was skipped as handled elsewhere, what was left on purpose and
why, and what's undecided. Then:

```shell
python <skill>/scripts/personal-data.py report E:/old-c D:/_backups/old-drives/old-pc --name old-pc `
    --saves-targets D:/_backups/game-saves/old-pc
python <skill>/scripts/overview.py
```

`report` writes `salvage.md` from the result files the earlier steps left:

- `software.json`
- `copy.json` and `manifest.json`
- `leftovers.json`
- each target's `verify.json` and `games.json`
- `decisions.md`

`overview.py` writes `_backups\README.md`. It maps every record file, lists the drives and
targets, and lists all games across archives with the newest save of each.

Later, without the drive:

```shell
python <skill>/scripts/personal-data.py check D:/_backups/old-drives/old-pc   # every file against manifest.json
```

## 5. Delete, once the owner says so

When step 3 shows only software, settings, caches and credential stores, and step 4's record
is written, the drive can go.
Deleting is the owner's decision, made after seeing step 3's result. Delete it from Explorer or
with `Remove-Item -Recurse` for a folder copy, or wipe the disk.

## Where things go

- **Game saves**: `$GAME_SAVES_HOME\<target>\`, e.g. `D:\_backups\game-saves\` (see [game-saves.md](game-saves.md))
- **Personal data**: `<backup disk>\_backups\old-drives\<name>\personal\`, at its original
  paths. Sorting it into a personal archive is a separate, later step.
- **Software list**: `<backup disk>\_backups\old-drives\<name>\software.md` and `.json`
