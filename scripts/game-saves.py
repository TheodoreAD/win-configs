"""Game-save archive built on Ludusavi: this PC's live saves, plus imports from old drive copies.

Everything personal lives in the archive folder, never in this repo:

  <archive>/custom-games.json         games Ludusavi doesn't know, and folders that aren't saves
  <archive>/live/{config,backup}/     this PC
  <archive>/sources/<name>/{config,backup}/, source.json   one old drive copy each

Each source backs up into its own folder, so a later live backup can never rotate an old
drive's saves out under Ludusavi's retention limits. The configs are generated: edit
custom-games.json and rerun, never the config.yaml files.

custom-games.json:
  {"games": [{"name": "Defender's Quest", "files": ["<winAppData>/LevelUpLabs/DefendersQuest"]},
             {"name": "Grim Dawn", "integration": "extend", "files": ["<winDocuments>/My Games/Grim Dawn_BAK"]},
             {"name": "Steam emulator saves (CODEX)", "files": ["{drive}/Users/Public/Documents/Steam/CODEX"]}],
   "notSaves": ["AppData/Roaming/Autodesk", "Documents/Fax"]}
  Paths use Ludusavi's placeholders (<home>, <winAppData>, <winLocalAppData>, <winLocalAppDataLow>,
  <winDocuments>), which resolve inside an old drive's profiles too. {drive} is the drive root
  (C: for live); use it where a placeholder points at this PC instead, like the Public folder.
  "extend" adds paths to a game Ludusavi already knows. notSaves are profile-relative folders
  that `gaps` stops reporting.

Usage (the archive is $GAME_SAVES_HOME, or --archive):
  uv run python scripts/game-saves.py init-live --installs C:/games
  uv run python scripts/game-saves.py add-source old-pc-2020 --drive E:/old-c --installs E:/old-c/_games
  uv run python scripts/game-saves.py preview old-pc-2020   # what would be backed up, nothing written
  uv run python scripts/game-saves.py gaps old-pc-2020      # save-like folders nothing covers yet
  uv run python scripts/game-saves.py backup old-pc-2020    # copy the saves into the archive
  uv run python scripts/game-saves.py backup live

An old drive's config ignores everything on this PC outside the drive's folder, and the live
registry, since Ludusavi always scans this PC too. Its restore redirects send the old
profile, Public, ProgramData and Steam folders to this PC's. See docs/game-saves.md.

Needs ludusavi on PATH (scoop install extras/ludusavi). Standard library only.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

NOT_USERS = {"public", "default", "default user", "all users", "guest", "defaultapppool"}
# Folders under a profile where games keep saves; `gaps` lists their children.
SAVE_PARENTS = ["Saved Games", "Documents", "Documents/My Games", "AppData/Roaming",
                "AppData/LocalLow", "AppData/Local"]
# Children of those that are never game saves, for any user. Personal ones go in notSaves.
GENERIC_NOT_SAVES = {
    "microsoft", "adobe", "google", "mozilla", "nvidia", "nvidia corporation", "intel", "amd",
    "packages", "programs", "temp", "crashdumps", "d3dscache", "connecteddevicesplatform",
    "comms", "package cache", "virtualstore", "microsoft help", "microsoftedge", "squirreltemp",
    "pip", "npm-cache", "nuget", "jetbrains", "code", "visual studio setup", "vstelemetry",
    "servicehub", "diagnostics", "isolatedstorage", "placeholdertilelogofolder", "cache", "cef",
    "unity", "my games", "steam", "spotify", "slack", "skype", "dropbox", "teamviewer",
    "windowsapps", "my music", "my pictures", "my videos", "desktop.ini",
}


def die(msg: str) -> None:
    sys.exit(f"game-saves: {msg}")


def ludusavi(*args: str, config: Path, capture: bool = True) -> subprocess.CompletedProcess:
    exe = shutil.which("ludusavi") or die("ludusavi not on PATH: scoop install extras/ludusavi")
    return subprocess.run([exe, "--config", str(config), *args], capture_output=capture,
                          text=True, encoding="utf-8", errors="replace")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def slash(p) -> str:
    return str(p).replace("\\", "/").rstrip("/")


class Archive:
    def __init__(self, root: Path):
        self.root = root
        self.custom = read_json(root / "custom-games.json", {"games": [], "notSaves": []})

    def target(self, name: str) -> Path:
        return self.root / ("live" if name == "live" else f"sources/{name}")

    def source(self, name: str) -> dict:
        if name == "live":
            return {"drive": "C:", "installs": []}
        info = read_json(self.target(name) / "source.json", None)
        return info or die(f"no source named {name!r}; add it with add-source")

    def custom_games(self, drive: str) -> list[dict]:
        games = []
        for g in self.custom.get("games", []):
            entry = {"name": g["name"], "integration": g.get("integration", "override"),
                     "files": [f.replace("{drive}", slash(drive)) for f in g.get("files", [])],
                     "registry": g.get("registry", []), "installDir": g.get("installDir", [])}
            games.append(entry)
        return games

    def write_config(self, name: str, roots: list[dict] | None = None) -> Path:
        """(Re)generate a target's config.yaml from Ludusavi's own config plus ours."""
        t = self.target(name)
        cfg_dir = t / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        # On a fresh dir Ludusavi writes its defaults, with this PC's detected roots.
        r = ludusavi("config", "show", "--api", config=cfg_dir)
        if r.returncode:
            die(f"ludusavi config show failed: {r.stderr.strip()}")
        cfg = json.loads(r.stdout)
        if roots is not None:
            cfg["roots"] = roots
        cfg["backup"]["path"] = slash(t / "backup")
        cfg["restore"]["path"] = slash(t / "backup")
        cfg["customGames"] = self.custom_games(self.source(name)["drive"])
        if name != "live":
            # Ludusavi always scans this PC's own folders and registry too; keep those out of
            # an old drive's archive.
            flt = cfg["backup"]["filter"]
            flt["ignoredPaths"] = outside(Path(self.source(name)["drive"]))
            flt["ignoredRegistry"] = ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"]
            # Backups keep the old drive's paths; a restore lands in this PC's matching folders.
            # Saves from game install folders keep their old path: redirect those by hand.
            drive = Path(self.source(name)["drive"])
            here = Path(os.environ.get("SystemDrive", "C:") + "/")
            moves = [(p, Path.home()) for p in old_profiles(drive)]
            moves += [(drive / "Users" / "Public", here / "Users" / "Public"),
                      (drive / "ProgramData", here / "ProgramData"),
                      (drive / "Program Files (x86)" / "Steam", here / "Program Files (x86)" / "Steam")]
            cfg["redirects"] = [{"kind": "restore", "source": slash(s), "target": slash(t)}
                                for s, t in moves]
        # JSON is valid YAML, and Ludusavi reads it as its config.yaml.
        write_json(cfg_dir / "config.yaml", cfg)
        # Each config dir keeps its own copy of the game manifest; without it Ludusavi knows
        # only the custom games.
        if not (cfg_dir / "manifest.yaml").exists():
            r = ludusavi("manifest", "update", config=cfg_dir)
            if r.returncode or not (cfg_dir / "manifest.yaml").exists():
                die(f"couldn't download Ludusavi's game manifest: {r.stderr.strip()}")
        return cfg_dir


def outside(drive: Path) -> list[str]:
    """Every top-level path on this PC's drives that isn't on the way to `drive`."""
    target = Path(os.path.abspath(drive))
    ignores = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        try:
            if not root.exists():
                continue
            if target.drive.upper() != f"{letter}:":
                ignores += [slash(c) for c in root.iterdir()]
                continue
            cur = root
            for part in target.parts[1:]:
                ignores += [slash(c) for c in cur.iterdir() if c.name.lower() != part.lower()]
                cur = cur / part
        except OSError:
            continue
    return ignores


def old_profiles(drive: Path) -> list[Path]:
    users = drive / "Users"
    return [p for p in users.iterdir() if p.is_dir() and p.name.lower() not in NOT_USERS
            and not p.is_symlink()] if users.is_dir() else []


def preview_files(cfg_dir: Path) -> dict:
    r = ludusavi("--try-manifest-update", "backup", "--preview", "--api", config=cfg_dir)
    if r.returncode and not r.stdout.strip():
        die(f"ludusavi preview failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def cmd_init_live(a, arc: Archive) -> None:
    cfg = arc.write_config("live")
    if a.installs:  # added to the launcher roots Ludusavi detected
        roots = read_json(cfg / "config.yaml", {})["roots"]
        have = {r["path"].lower() for r in roots}
        roots += [{"store": "other", "path": slash(i)} for i in a.installs if slash(i).lower() not in have]
        cfg = arc.write_config("live", roots)
    roots = read_json(cfg / "config.yaml", {})["roots"]
    print(f"live config: {cfg}\nroots: {', '.join(r['store'] + ' ' + r['path'] for r in roots)}\n"
          f"backups go to: {arc.target('live') / 'backup'}")


def cmd_add_source(a, arc: Archive) -> None:
    drive = Path(a.drive)
    if not (drive / "Users").is_dir():
        die(f"{drive} has no Users folder; point --drive at the old drive's root")
    t = arc.target(a.name)
    write_json(t / "source.json", {"drive": slash(drive), "installs": [slash(i) for i in a.installs]})
    roots = [{"store": "otherWindows", "path": slash(drive)}]
    for steam in (drive / "Program Files (x86)" / "Steam", drive / "Program Files" / "Steam"):
        if (steam / "userdata").is_dir():
            roots.append({"store": "steam", "path": slash(steam)})
    roots += [{"store": "other", "path": slash(i)} for i in a.installs]
    cfg = arc.write_config(a.name, roots)
    print(f"source {a.name}: drive {drive}, roots {', '.join(r['store'] for r in roots)}\nconfig: {cfg}")


def summarize(data: dict) -> None:
    games = data.get("games", {})
    files = sizes = 0
    for info in games.values():
        for f in (info.get("files") or {}).values():
            files += 1
            sizes += f.get("bytes", 0)
    print(f"{len(games)} games, {files} files, {sizes / 1e9:.2f} GB")
    for g in sorted(games):
        print(f"  {g}  ({len(games[g].get('files') or {})} files)")


def regenerate(arc: Archive, name: str) -> Path:
    if name == "live":
        return arc.write_config("live")
    cfg = read_json(arc.target(name) / "config" / "config.yaml", None) or die(f"no source named {name!r}")
    return arc.write_config(name, cfg["roots"])


def cmd_preview(a, arc: Archive) -> None:
    cfg = regenerate(arc, a.name)
    data = preview_files(cfg)
    summarize(data)
    if a.name != "live":
        drive = os.path.normcase(os.path.normpath(arc.source(a.name)["drive"])) + os.sep
        stray = [p for info in data.get("games", {}).values() for p in (info.get("files") or {})
                 if not os.path.normcase(os.path.normpath(p)).startswith(drive)]
        stray += [k for info in data.get("games", {}).values() for k in (info.get("registry") or {})]
        if stray:
            print(f"WARNING: {len(stray)} item(s) from outside the old drive, e.g. {stray[0]}")


def cmd_gaps(a, arc: Archive) -> None:
    if a.name == "live":
        die("gaps is for old drive sources")
    src = arc.source(a.name)
    drive = Path(src["drive"])
    cfg = regenerate(arc, a.name)
    covered = [os.path.normcase(os.path.normpath(p))
               for info in preview_files(cfg).get("games", {}).values() for p in (info.get("files") or {})]
    not_saves = {s.lower().replace("\\", "/").strip("/") for s in arc.custom.get("notSaves", [])}
    found = 0
    for prof in old_profiles(drive):
        for parent in SAVE_PARENTS:
            base = prof / parent
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
                rel = f"{parent}/{child.name}".lower()
                if not child.is_dir() or child.is_symlink() or child.name.lower() in GENERIC_NOT_SAVES \
                        or rel in not_saves:
                    continue
                prefix = os.path.normcase(os.path.normpath(child)) + os.sep
                if any(p.startswith(prefix) for p in covered):
                    continue
                n = sum(len(f) for _, _, f in os.walk(child))
                if n:
                    found += 1
                    print(f"  {prof.name}/{parent}/{child.name}  ({n} files)")
    print(f"{found} folder(s) not covered. Add games to custom-games.json, or their paths to notSaves.")


def cmd_backup(a, arc: Archive) -> None:
    cfg = regenerate(arc, a.name)
    r = ludusavi("--try-manifest-update", "backup", "--force", config=cfg, capture=False)
    sys.exit(r.returncode)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archive", default=os.environ.get("GAME_SAVES_HOME"),
                   help="the save archive folder (default: $GAME_SAVES_HOME)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init-live", help="create or refresh the config for this PC")
    s.add_argument("--installs", nargs="*", default=[], help="folders whose children are game installs")
    s = sub.add_parser("add-source", help="register an old drive copy")
    s.add_argument("name", help="a short kebab-case name, e.g. other-c-2020")
    s.add_argument("--drive", required=True, help="the old drive's root (the folder holding Users)")
    s.add_argument("--installs", nargs="*", default=[], help="folders whose children are game installs")
    for name, help_ in (("preview", "list what a backup would copy, writing nothing"),
                        ("gaps", "save-like folders on an old drive that nothing covers"),
                        ("backup", "copy the saves into the archive")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("name", help="a source name, or live")
    a = p.parse_args()
    if not a.archive:
        die("set GAME_SAVES_HOME or pass --archive: the folder that holds the save archive")
    arc = Archive(Path(a.archive))
    {"init-live": cmd_init_live, "add-source": cmd_add_source, "preview": cmd_preview,
     "gaps": cmd_gaps, "backup": cmd_backup}[a.cmd](a, arc)


if __name__ == "__main__":
    main()
