# Retiring an old drive copy

How to empty a copy of a previous system drive (a folder or disk with its own `Users` folder)
so it can be deleted without losing anything personal. Game saves and settings are kept;
software, Windows settings and drivers aren't, since they get reinstalled.

The order matters: saves first, then other personal data, then a check of everything that's
left. The first copy of `C:\_other_c` skipped that last step, and missed chat histories,
unsaved notes and notebook backups that apps keep in AppData.

## 1. Game saves

With [docs/game-saves.md](game-saves.md):

```shell
uv run python scripts/game-saves.py add-old-drive old-pc --drive E:/old-c --installs E:/old-c/_games
uv run python scripts/game-saves.py gaps old-pc       # repeat, with custom-games.json, until it reports 0
uv run python scripts/game-saves.py backup old-pc     # ends with verify: every save file, by SHA-1
uv run python scripts/game-saves.py index old-pc      # games.md: when and how each game was played
```

`gaps` only looks where games usually save. Step 3 catches the rest, such as game screenshots
or a game folder kept under an odd name. Add those to `custom-games.json`, often as `extend` on
a game Ludusavi already knows, back up just those games, and verify again.

## 2. Other personal data

```shell
uv run python scripts/old-drive-personal.py copy E:/old-c --dest D:/_backups/old-drives/old-pc/personal
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
chat clients' account files. Old keys and passwords are best retired, not carried to a new
disk. Step 3 lists what it found, so the decision is yours.

## 3. What's left

```shell
uv run python scripts/old-drive-personal.py leftovers E:/old-c --dest D:/_backups/old-drives/old-pc/personal `
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
anything personal, add its folder to `APP_DATA` in `scripts/old-drive-personal.py` (or to the
game-save archive) and rerun `copy`. Then rerun `leftovers` until only app settings, caches
and cloud clients' local state remain.

Look closely at:

- **Chat apps**: their history is often the only copy left, once the service shuts down
  (Skype, in 2025)
- **Editors and note apps**: unsaved-tab backups, notebook backups, scratch files
- **Image folders inside game data**: screenshots
- **Cloud clients** (SpiderOak, Dropbox, OneDrive): only their local state. The files are in
  the cloud, or in the sync folder if it was on this drive

## 4. Decide, then delete

- **Credential stores**: delete with the drive, or keep in a password manager.
- **The rest**: when step 3 shows only software, settings and caches, the drive copy can go.
  Delete it from Explorer or with `Remove-Item -Recurse`, once you've decided to.

## Where things go

- **Game saves**: `D:\_backups\game-saves\<target>\` (see [game-saves.md](game-saves.md))
- **Personal data**: `D:\_backups\old-drives\<name>\personal\`, at its original paths. Sorting
  it into `D:\_personal` is a separate, later step.
