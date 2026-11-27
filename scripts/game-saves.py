"""Game-save archive built on Ludusavi, with one target per gaming root.

A target is one root whose saves are kept apart from every other's:

- an old drive copy (a folder holding a previous system drive, with its Users folder), or
- a live root on this PC: the system drive (profiles, registry, launchers) or another drive
  with game installs.

Each target backs up only files on its own root, into its own folder, so no backup can
rotate another root's saves out under Ludusavi's retention limits.

Everything personal lives in the archive folder, never in this repo:

  <archive>/custom-games.json            games Ludusavi doesn't know, and folders that aren't saves
  <archive>/<target>/target.json         what the target is
  <archive>/<target>/config/             generated Ludusavi config, never edit it
  <archive>/<target>/backup/             the backups

custom-games.json:
  {"games": [{"name": "Defender's Quest", "files": ["<winAppData>/LevelUpLabs/DefendersQuest"]},
             {"name": "Grim Dawn", "integration": "extend", "files": ["<winDocuments>/My Games/Grim Dawn_BAK"]},
             {"name": "Steam emulator saves (CODEX)", "files": ["{drive}/Users/Public/Documents/Steam/CODEX"]}],
   "notSaves": ["AppData/Roaming/Autodesk", "Documents/Fax"]}
  Paths use Ludusavi's placeholders (<home>, <winAppData>, <winLocalAppData>, <winLocalAppDataLow>,
  <winDocuments>), which resolve inside an old drive's profiles too. {drive} is the target's
  drive root (the system drive for live targets); use it where a placeholder points at this PC
  instead, like the Public folder. "extend" adds paths to a game Ludusavi already knows.
  notSaves are profile-relative folders that `gaps` stops reporting.

Usage (the archive is $GAME_SAVES_HOME, or --archive):
  uv run python scripts/game-saves.py add-old-drive old-pc --drive E:/old-c --installs E:/old-c/_games
  uv run python scripts/game-saves.py add-live c --scope C:/ --installs C:/games
  uv run python scripts/game-saves.py add-live d --scope D:/ --installs D:/_games
  uv run python scripts/game-saves.py gaps old-pc      # save-like folders nothing covers (old drives)
  uv run python scripts/game-saves.py preview old-pc   # what a backup would copy, nothing written
  uv run python scripts/game-saves.py backup old-pc
  uv run python scripts/game-saves.py verify old-pc    # every current save file is in the backup, same hash

A live target skips the folders of every other target inside its scope (an old drive copy
kept on C: is its own target). Only the system-drive target keeps registry saves. An old
drive's target ignores the live registry and restores to this PC's matching folders. See
docs/game-saves.md.

Needs ludusavi on PATH (scoop install extras/ludusavi). Standard library only.
"""

import argparse
import hashlib
import json
import os
import re
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
SYSTEM_DRIVE = Path(os.environ.get("SystemDrive", "C:") + "/")


def die(msg: str):
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
    s = str(p).replace("\\", "/")
    return s if re.fullmatch(r"[A-Za-z]:/", s) else s.rstrip("/")


def key(p) -> str:
    """Comparable form of a path: absolute, normalized, case-folded."""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))


def under(path, folder) -> bool:
    f = key(folder)
    return key(path) == f or key(path).startswith(f.rstrip(os.sep) + os.sep)


def outside(scope: Path, skip: list[Path]) -> list[str]:
    """Paths to ignore so only `scope` is scanned: every top-level path on this PC's drives
    that isn't on the way to it, plus the `skip` folders inside it."""
    target = Path(os.path.abspath(scope))
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
    return ignores + [slash(s) for s in skip if under(s, scope)]


def old_profiles(drive: Path) -> list[Path]:
    users = drive / "Users"
    return [p for p in users.iterdir() if p.is_dir() and p.name.lower() not in NOT_USERS
            and not p.is_symlink()] if users.is_dir() else []


class Archive:
    def __init__(self, root: Path):
        self.root = root
        self.custom = read_json(root / "custom-games.json", {"games": [], "notSaves": []})

    def targets(self) -> dict[str, dict]:
        if not self.root.is_dir():
            return {}
        return {d.name: read_json(d / "target.json", None) for d in self.root.iterdir()
                if (d / "target.json").is_file()}

    def target(self, name: str) -> dict:
        t = self.targets().get(name)
        return t or die(f"no target named {name!r}; add it with add-old-drive or add-live")

    def custom_games(self, drive: str) -> list[dict]:
        return [{"name": g["name"], "integration": g.get("integration", "override"),
                 "files": [f.replace("{drive}", slash(drive).rstrip("/")) for f in g.get("files", [])],
                 "registry": g.get("registry", []), "installDir": g.get("installDir", [])}
                for g in self.custom.get("games", [])]

    def write_config(self, name: str, t: dict) -> Path:
        """(Re)generate a target's config.yaml from Ludusavi's defaults plus ours."""
        base = self.root / name
        cfg_dir = base / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        # On a fresh dir Ludusavi writes its defaults, with this PC's detected launcher roots.
        r = ludusavi("config", "show", "--api", config=cfg_dir)
        if r.returncode:
            die(f"ludusavi config show failed: {r.stderr.strip()}")
        cfg = json.loads(r.stdout)
        scope = Path(t["scope"])
        others = [Path(o["scope"]) for n, o in self.targets().items() if n != name]
        flt = cfg["backup"]["filter"]
        flt["ignoredPaths"] = outside(scope, others)
        if t["kind"] == "old-drive":
            roots = [{"store": "otherWindows", "path": slash(scope)}]
            for steam in (scope / "Program Files (x86)" / "Steam", scope / "Program Files" / "Steam"):
                if (steam / "userdata").is_dir():
                    roots.append({"store": "steam", "path": slash(steam)})
            drive = scope
            flt["ignoredRegistry"] = ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"]
            # Backups keep the old drive's paths; a restore lands in this PC's matching folders.
            moves = [(p, Path.home()) for p in old_profiles(scope)]
            moves += [(scope / "Users" / "Public", SYSTEM_DRIVE / "Users" / "Public"),
                      (scope / "ProgramData", SYSTEM_DRIVE / "ProgramData"),
                      (scope / "Program Files (x86)" / "Steam", SYSTEM_DRIVE / "Program Files (x86)" / "Steam")]
            cfg["redirects"] = [{"kind": "restore", "source": slash(s), "target": slash(d)} for s, d in moves]
        else:
            detected = t.get("detectedRoots")
            if detected is None:  # Ludusavi's launcher detection, kept from the first run
                detected = t["detectedRoots"] = cfg["roots"]
                write_json(base / "target.json", t)
            roots = [r for r in detected if under(r["path"], scope)]
            drive = SYSTEM_DRIVE
            if key(scope) != key(SYSTEM_DRIVE):
                flt["ignoredRegistry"] = ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"]
        have = {key(r["path"]) for r in roots}
        roots += [{"store": "other", "path": slash(i)} for i in t.get("installs", []) if key(i) not in have]
        cfg["roots"] = roots
        cfg["backup"]["path"] = slash(base / "backup")
        cfg["restore"]["path"] = slash(base / "backup")
        cfg["customGames"] = self.custom_games(slash(drive))
        # JSON is valid YAML, and Ludusavi reads it as its config.yaml.
        write_json(cfg_dir / "config.yaml", cfg)
        # Each config dir keeps its own copy of the game manifest; without it Ludusavi knows
        # only the custom games.
        if not (cfg_dir / "manifest.yaml").exists():
            r = ludusavi("manifest", "update", config=cfg_dir)
            if r.returncode or not (cfg_dir / "manifest.yaml").exists():
                die(f"couldn't download Ludusavi's game manifest: {r.stderr.strip()}")
        return cfg_dir

    def config(self, name: str) -> Path:
        return self.write_config(name, self.target(name))


def preview_files(cfg_dir: Path, games: list[str] = ()) -> dict:
    r = ludusavi("--try-manifest-update", "backup", "--preview", "--api", *games, config=cfg_dir)
    if r.returncode and not r.stdout.strip():
        die(f"ludusavi preview failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def files_of(data: dict) -> dict[str, dict[str, int]]:
    return {g: {p: f.get("bytes", 0) for p, f in (i.get("files") or {}).items()}
            for g, i in data.get("games", {}).items()}


def add_target(arc: Archive, name: str, t: dict) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        die("target names are lowercase kebab-case, e.g. old-pc-2020")
    clash = [n for n, o in arc.targets().items() if n != name and key(o["scope"]) == key(t["scope"])]
    if clash:
        die(f"{t['scope']} is already target {clash[0]}")
    old = arc.targets().get(name) or {}
    t = {**t, **({"detectedRoots": old["detectedRoots"]} if "detectedRoots" in old else {})}
    write_json(arc.root / name / "target.json", t)
    cfg = arc.write_config(name, t)
    roots = read_json(cfg / "config.yaml", {})["roots"]
    print(f"target {name} ({t['kind']}, scope {t['scope']})\n"
          f"roots: {', '.join(r['store'] + ' ' + r['path'] for r in roots) or 'none'}\n"
          f"backups: {arc.root / name / 'backup'}")


def cmd_add_old_drive(a, arc: Archive) -> None:
    drive = Path(a.drive)
    if not (drive / "Users").is_dir():
        die(f"{drive} has no Users folder; point --drive at the old drive's root")
    add_target(arc, a.name, {"kind": "old-drive", "scope": slash(drive), "installs": [slash(i) for i in a.installs]})


def cmd_add_live(a, arc: Archive) -> None:
    add_target(arc, a.name, {"kind": "live", "scope": slash(Path(a.scope)), "installs": [slash(i) for i in a.installs]})


def cmd_preview(a, arc: Archive) -> None:
    t = arc.target(a.name)
    data = preview_files(arc.config(a.name), a.games)
    files = files_of(data)
    total = sum(sum(f.values()) for f in files.values())
    print(f"{len(files)} games, {sum(len(f) for f in files.values())} files, {total / 1e9:.2f} GB")
    for g in sorted(files):
        print(f"  {g}  ({len(files[g])} files)")
    stray = [p for f in files.values() for p in f if not under(p, t["scope"])]
    if t["kind"] == "old-drive" or key(t["scope"]) != key(SYSTEM_DRIVE):
        stray += [k for i in data.get("games", {}).values() for k in (i.get("registry") or {})]
    if stray:
        print(f"WARNING: {len(stray)} item(s) from outside {t['scope']}, e.g. {stray[0]}")


def cmd_gaps(a, arc: Archive) -> None:
    t = arc.target(a.name)
    if t["kind"] != "old-drive":
        die("gaps is for old drive targets")
    covered = [key(p) for f in files_of(preview_files(arc.config(a.name))).values() for p in f]
    not_saves = {s.lower().replace("\\", "/").strip("/") for s in arc.custom.get("notSaves", [])}
    found = 0
    for prof in old_profiles(Path(t["scope"])):
        for parent in SAVE_PARENTS:
            base = prof / parent
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
                rel = f"{parent}/{child.name}".lower()
                if not child.is_dir() or child.is_symlink() or child.name.lower() in GENERIC_NOT_SAVES \
                        or rel in not_saves:
                    continue
                prefix = key(child) + os.sep
                if any(p.startswith(prefix) for p in covered):
                    continue
                n = sum(len(f) for _, _, f in os.walk(child))
                if n:
                    found += 1
                    print(f"  {prof.name}/{parent}/{child.name}  ({n} files)")
    print(f"{found} folder(s) not covered. Add games to custom-games.json, or their paths to notSaves.")


def cmd_backup(a, arc: Archive) -> None:
    cfg = arc.config(a.name)
    r = ludusavi("--try-manifest-update", "backup", "--force", *a.games, config=cfg, capture=False)
    if r.returncode:
        sys.exit(r.returncode)
    print("\nverifying...")
    sys.exit(verify(arc, a.name, a.games))


# ----------------------------------------------------------------------------- verify


def read_mapping(path: Path) -> tuple[str, dict[str, dict]]:
    """A game's mapping.yaml: its name and {original path: {hash, size, folder}}, latest backup
    winning. Parses only the subset Ludusavi writes."""
    name, files, folder, cur = "", {}, ".", None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r'^name: "?(.*?)"?$', line):
            name = m[1]
        elif m := re.match(r'^\s+- name: "?(.*?)"?$', line):
            folder, cur = m[1], None
        elif re.match(r"^\s+(registry|children|files):", line):
            cur = None  # registry has its own "hash:", which isn't a file's
        elif m := re.match(r'^\s{6,}"(.+)":$', line):
            cur = files[m[1].replace('\\"', '"')] = {"folder": folder}
        elif cur is not None and (m := re.match(r"^\s+(hash|size): (\S+)$", line)):
            cur[m[1]] = m[2]
    return name, files


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(arc: Archive, name: str, games: list[str] = ()) -> int:
    """Every file the source has now is in the backup, with the same hash, and the stored copy
    matches too. Returns 0 when everything is safe."""
    backup = arc.root / name / "backup"
    mappings = {}
    for m in backup.glob("*/mapping.yaml"):
        game, files = read_mapping(m)
        mappings[game] = (m.parent, files)
    current = files_of(preview_files(arc.config(name), games))
    bad = 0
    for game, files in sorted(current.items()):
        folder, stored = mappings.get(game, (None, {}))
        problems = []
        for p in files:
            entry = stored.get(slash(p)) or stored.get(p)
            if not entry:
                problems.append(f"not in backup: {p}")
                continue
            src = Path(p)
            if src.exists() and sha1(src) != entry.get("hash"):
                problems.append(f"changed since the backup: {p}")
                continue
            drive, rest = slash(p).split(":", 1)
            copy = folder / ("" if entry["folder"] == "." else entry["folder"]) / f"drive-{drive}" / rest.lstrip("/")
            if not copy.exists() or sha1(copy) != entry.get("hash"):
                problems.append(f"backup copy missing or damaged: {copy}")
        if problems:
            bad += 1
            print(f"NOT SAFE {game}:")
            for pr in problems[:5]:
                print(f"    {pr}")
    print(f"{len(current) - bad} of {len(current)} games safe" + ("" if not bad else f", {bad} not"))
    return 1 if bad else 0


def cmd_verify(a, arc: Archive) -> None:
    sys.exit(verify(arc, a.name, a.games))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archive", default=os.environ.get("GAME_SAVES_HOME"),
                   help="the save archive folder (default: $GAME_SAVES_HOME)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add-old-drive", help="register an old drive copy as a target")
    s.add_argument("name", help="lowercase kebab-case, e.g. old-pc-2020")
    s.add_argument("--drive", required=True, help="the old drive's root (the folder holding Users)")
    s.add_argument("--installs", nargs="*", default=[], help="folders whose children are game installs")
    s = sub.add_parser("add-live", help="register a root on this PC as a target")
    s.add_argument("name", help="lowercase kebab-case, e.g. c")
    s.add_argument("--scope", required=True, help="the root: the system drive (C:/) or another drive or folder")
    s.add_argument("--installs", nargs="*", default=[], help="folders whose children are game installs")
    for name, help_ in (("preview", "list what a backup would copy, writing nothing"),
                        ("gaps", "save-like folders on an old drive that nothing covers"),
                        ("backup", "copy the saves into the archive, then verify"),
                        ("verify", "check every current save file is in the backup with the same hash")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("name", help="a target name")
        if name != "gaps":
            s.add_argument("games", nargs="*", help="only these games (exact Ludusavi names)")
    a = p.parse_args()
    if not a.archive:
        die("set GAME_SAVES_HOME or pass --archive: the folder that holds the save archive")
    arc = Archive(Path(a.archive))
    {"add-old-drive": cmd_add_old_drive, "add-live": cmd_add_live, "preview": cmd_preview,
     "gaps": cmd_gaps, "backup": cmd_backup, "verify": cmd_verify}[a.cmd](a, arc)


if __name__ == "__main__":
    main()
