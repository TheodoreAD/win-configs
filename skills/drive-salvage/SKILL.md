---
name: drive-salvage
description: Save everything personal from a Windows installation or drive before it goes, and keep game saves in a verified archive. Covers old system-drive copies kept as folders, other or offline disks, and this PC itself. It saves personal files, the personal data apps keep in AppData (chat history, unsaved notes, notebooks, mail, playlists, browser bookmarks and history), game saves with Ludusavi plus metadata on when and how each game was played, the old registry, and a list of the software that was installed. Software, drivers, Windows settings and credentials are not kept. Use this whenever the user wants to back up game saves, clean up or delete an old drive or a copy of one, retire or reinstall a Windows install, check that nothing personal is left before deleting, free disk space taken by old backups, find out what was on an old disk, or asks whether it's safe to delete an old folder, even if they don't name this skill.
---

# Drive salvage

Get everything worth keeping off a Windows install or drive, prove it's safe, and only then
let it go. A **drive** is any root with a `Users` folder:

- an old system drive kept as a folder (e.g. `C:\_old-c`)
- another disk, including one Windows keeps offline
- this PC's own C:, before a reinstall or as a regular backup

## What's kept, and what isn't

- **Kept**:
  - personal files
  - personal data that apps keep in AppData: chats, unsaved editor tabs, notebooks, mail,
    playlists, browser bookmarks and history
  - game saves and game settings
  - each game's metadata: save timeline, Steam play time, store IDs, mods, how it was
    acquired
  - the old registry hive (games keep settings there)
  - dotfiles
  - a list of the installed software, as names and versions
- **Not kept**:
  - **software**: it gets reinstalled
  - **drivers, Windows settings, anything machine-specific**
  - **credentials**, ever: `.ssh`, password databases, browser saved logins, chat account
    files, Windows' credential folders. They go with the drive. Never copy, print or move
    them.

## The method

Work in this order, and don't skip a step: each one catches what the one before misses.
Details and commands are in `references/retiring-a-drive.md`.

0. **Get at it read-only**, then run `personal-data.py inventory` for the software list.
1. **Game saves**, with `scripts/game-saves.py` (`references/game-saves.md`):
   - `add-old-drive` (or `add-live` for this PC)
   - `gaps` until it reports 0
   - `backup`, which ends with `verify`
   - `index`
2. **Other personal data**: `personal-data.py copy`. It verifies every file by SHA-1.
3. **What's left**: `personal-data.py leftovers`. Read every line it prints. Anything personal
   goes into the copy lists, or into the save archive, and step 2 or 1 runs again. Repeat
   until only software, app settings, caches and credential stores remain. Then run
   `deep-survey.py`. It looks where `leftovers` deliberately doesn't: inside game installs
   (files changed after install), the Recycle Bin, top-level folders, ProgramData, Steam data,
   portable tools' settings, and profile items copied only partly. Add its finds with
   `copy --extra` or custom games.
4. **Record it**, so it can be read once the drive is gone:
   - write the drive folder's `decisions.md` by hand: what the drive was, what was skipped or
     left and why, what's still undecided
   - `personal-data.py report` writes `salvage.md` from the result files
   - `overview.py` rewrites the archive's front page, `README.md`
5. **Delete only when the user says so**, after they've seen step 3's result.

Step 3 is the one that matters most and the easiest to skip. On the first drive done this
way, the user folders and game saves were all safe, and the drive still held Skype and
Pidgin chat history, unsaved Notepad++ notes, OneNote backups and game screenshots. Nothing
would have flagged them without the full scan. When the user asks "are you sure nothing is
left?", answer with step 3's output, not with what was copied.

## Judgment calls

- **"Is it personal?"** Ask whether it would be lost if the drive went and couldn't be
  recreated: something the user wrote, received, made, collected or played. Settings an app
  recreates, caches, and cloud clients' local state (when the files live in the cloud) aren't
  personal. Chat history is personal, often the only copy once a service shuts down.
- **Game saves inside install folders** are kept: Ludusavi finds them through the install
  roots. Everything else in an install folder is software.
- **Work data** found on a personal drive (notebooks, CAD settings) is kept with the rest.
  Sorting it out is the user's call later.
- **Ownership of a game** comes only from what's on disk: launcher records, install markers,
  release-style names, emulator folders. Never from a web API or an API key.
- **Nothing is changed in place.** Old drives are read, never written. A disk is brought
  online read-only. Backups go to another physical disk.
- **Verify, don't assume.** Both scripts check every file by SHA-1. Report what the check
  says, including failures.

## Where things go

The archive lives on a disk other than the one being salvaged. On this setup that's the
data disk's `_backups` folder:

- **Game saves**: `$GAME_SAVES_HOME` (one target per gaming root: each old drive, `c`, `d`),
  with `games.md` per target
- **Personal data**: `_backups\old-drives\<name>\personal\`, at the original paths
- **Software list**: `_backups\old-drives\<name>\software.md`
- **Records**: each drive's folder also holds
  - `salvage.md`, the report
  - `decisions.md`
  - `manifest.json`, every copied file with SHA-1, so `personal-data.py check` can re-verify
    the copy without the drive
  - `copy.json` and `leftovers.json`

  Each game-save target holds `verify.json`. `_backups\README.md` is the front page: a map of
  all of these, the drives, the targets, and every game across archives with its newest save.

`custom-games.json` in the save archive holds the user's game list. It's personal, so it
never goes in a repo.

## Files

- **`scripts/game-saves.py`** — the game-save archive on Ludusavi (`scoop install extras/ludusavi`):
  `add-old-drive`, `add-live`, `gaps`, `preview`, `backup`, `verify`, `index`
- **`scripts/personal-data.py`** — `inventory`, `copy`, `leftovers`, `check`, `report`
- **`scripts/overview.py`** — the archive's front page and cross-archive game list
- **`scripts/probe-disk.py`** — what's on a disk Windows sees no partitions on (admin, read-only)
- **`scripts/deep-survey.py`** — the closer look after `leftovers`: installs, Recycle Bin, top-level
  folders, portable tools, partly copied profile items
- **`scripts/registry-export.py`** — optional, admin: games' registry keys and the whole
  `HKCU\Software` branch from a copied `NTUSER.DAT`, as readable, restorable `.reg` files. The
  hive is already kept, so this only makes it usable. Check first how many games keep saves
  (not just settings) there: on the first two drives, it was one each.
- **`references/retiring-a-drive.md`** — the full procedure, step by step
- **`references/game-saves.md`** — the archive layout, targets, custom games, the index, restoring

Run the scripts with `python <skill>/scripts/<name>.py`. They need only the standard library
(and robocopy, which ships with Windows).
