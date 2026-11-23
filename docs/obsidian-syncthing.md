# Obsidian and Syncthing (optional)

Obsidian for notes, Syncthing to sync note folders between devices without a cloud service.
Both are optional installs (see "Optional apps" in the README). General notes, gathered while
setting this up on 2026-11-22/23.

## Install and update

```shell
scoop bucket add extras
scoop install extras/obsidian
scoop install main/syncthing
scoop install extras/syncthingtray
```

- **Two packages:** Syncthing (`main`) and Syncthing Tray (`extras`) are separate. Start
  Syncthing Tray from the Start menu; it starts Syncthing with it.
- **Updating:** quit Syncthing from its tray icon before `scoop update`, or scoop skips both as
  running. If it keeps running, end both `syncthing` processes and `syncthingtray` in Task
  Manager.

## Syncthing

- **Syncthing isn't a backup.** Deletions and mistakes copy to every device. Turn on file
  versioning (staggered) on at least one device, and keep a separate real backup of the synced
  folders (File History, OneDrive, restic, or dated robocopy snapshots to another disk).
  Prefer dated snapshots over a mirror: a mirror copies deletions too.
- **One Syncthing folder per Obsidian vault**, each with its own `.stignore`, so each vault can
  go to a different set of devices.
- **`.stignore`** keeps per-device Obsidian state out of sync:

  ```text
  .obsidian/workspace*.json
  .obsidian/cache
  // if the vault also has a local git repo for history, keep it on this PC:
  .git
  ```

- **The `.stfolder` marker:** Syncthing creates it when a folder is added and uses it to tell
  "folder missing" from "everything deleted". If the marker is gone, Syncthing stops that folder
  with an error, which is safe. If the folder exists but is empty and still has its marker,
  Syncthing treats everything as deleted and sends the deletions to every device. To move or
  retire a synced folder: remove it in Syncthing first (with Syncthing and Obsidian closed),
  then move it, then add the new location and re-share it. Other devices accept the new share
  into a new, empty folder.
- **Conflict copies** appear as `*.sync-conflict-*` files next to the original. Merge by hand
  and delete them.

## Obsidian

- **Open a synced folder** with "Open folder as vault", and remove stale entries from the vault
  list after moving folders.
- **`.obsidian/`** holds a vault's settings and plugins. It's hidden, so most tools (search,
  file panels) skip it.
- **Keep vaults outside code repositories.** Syncthing owns the vault folder and git owns the
  code; mixing them means `.gitignore` rules for Obsidian/Syncthing files and accidental
  commits of notes. A separate folder also keeps tools that skip ignored or hidden folders from
  missing your notes.
- **Optional local git history per vault**, never pushed: lets you review and undo edits (for
  example ones Claude makes). `git init` in the vault, add `.git` to its `.stignore`, and a
  `.gitignore` with:

  ```text
  .obsidian/workspace*.json
  .obsidian/cache
  .trash/
  *.sync-conflict-*
  ```

  If a vault does sit inside another git repo, the patterns need `**/` in front
  (`**/.obsidian/workspace*.json`), because a pattern with a slash only matches at the repo
  root.
- **Don't keep passwords in notes:** synced vaults are plain text on every device that has
  them. Use a password manager.
