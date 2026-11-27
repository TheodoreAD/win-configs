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
   "notSaves": ["AppData/Roaming/Autodesk", "Documents/Fax"],
   "acquired": {"Grim Dawn": "steam"}}
  Paths use Ludusavi's placeholders (<home>, <winAppData>, <winLocalAppData>, <winLocalAppDataLow>,
  <winDocuments>), which resolve inside an old drive's profiles too. {drive} is the target's
  drive root (the system drive for live targets); use it where a placeholder points at this PC
  instead, like the Public folder. "extend" adds paths to a game Ludusavi already knows.
  notSaves are profile-relative folders that `gaps` stops reporting. acquired overrides how
  `index` says a game was obtained.

Usage (the archive is $GAME_SAVES_HOME, or --archive):
  python <skill>/scripts/game-saves.py add-old-drive old-pc --drive E:/old-c --installs E:/old-c/_games
  python <skill>/scripts/game-saves.py add-live c --scope C:/ --installs C:/games
  python <skill>/scripts/game-saves.py add-live d --scope D:/ --installs D:/_games
  python <skill>/scripts/game-saves.py gaps old-pc      # save-like folders nothing covers (old drives)
  python <skill>/scripts/game-saves.py preview old-pc   # what a backup would copy, nothing written
  python <skill>/scripts/game-saves.py backup old-pc
  python <skill>/scripts/game-saves.py verify old-pc    # every current save file is in the backup, same hash
  python <skill>/scripts/game-saves.py index old-pc     # games.json/.md: save timeline, play time, mods

A live target skips the folders of every other target inside its scope (an old drive copy
kept on C: is its own target). Only the system-drive target keeps registry saves. An old
drive's target ignores the live registry and restores to this PC's matching folders. See
references/game-saves.md.

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
import time
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


# ----------------------------------------------------------------------------- index
# What the archive can tell about each game, to remember when and how it was played:
# save timeline (from the files' modified dates, which backups keep), recent save names,
# Steam play time and last-played date, store IDs and cloud support, registry keys the game
# uses, and mods found next to the saves, in the install folder or in Steam Workshop.

# Not "plugins": Unity games ship their engine DLLs in <game>_Data/Plugins.
MOD_DIRS = {"mods", "mod", "workshop", "bepinex", "override", "modding", "usermods"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds", ".webp"}
# Engine bookkeeping that sits next to saves; kept in the backup, left out of the timeline.
NOISE_DIRS = {"unity", "analytics", "logs", "log", "crashes", "crashreports", "cache", "shadercache"}


# Where a copy came from. Evidence only: a store's own install records or markers, or the
# traces a cracked release leaves. What it can't tell is "unknown"; custom-games.json's
# "acquired" map overrides it per game.
EMULATOR_DIRS = {"codex", "skidrow", "smartsteamemu", "ali213", "3dmgame", "goldberg", "steamemu"}
CRACK_FILES = {"steam_emu.ini", "smartsteamemu.ini", "smartsteamemu.dll", "codex.ini", "steam_api.cdx",
               "steam_api64.cdx", "ali213.ini", "3dmgame.ini", "3dmgame.dll", "cream_api.ini",
               "skidrow.ini", "cpy.ini", "onlinefix.ini", "steamclient_loader.exe", "uplay_r1_loader.dll.bak"}
CRACK_DIRS = {"steam_settings", "crack", "_crack"}
ACCOUNTS: tuple[dict, dict] = ({}, {})  # set by `index` from account_libraries()
RELEASE_PREFIX = re.compile(r"^(igg|codex|skidrow|plaza|reloaded|flt|darksiders|cpy|elamigos|fitgirl)[-_. ]", re.I)
RELEASE_VERSION = re.compile(r"[._ -]v?\d+(?:[._]\d+)+[a-z]?\b.*$|[._ -]v\d+\b.*$", re.I)


def account_libraries() -> tuple[dict, dict]:
    """What the accounts on this PC own, whatever drive a copy came from: GOG Galaxy's library
    ({gog id: purchase date}) and this PC's Steam account ({app id: play time, last played})."""
    gog = {}
    db = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "GOG.com/Galaxy/storage/galaxy-2.0.db"
    if db.is_file():
        import sqlite3
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:  # Galaxy keeps it open; read a copy
            copy = Path(tmp) / db.name
            shutil.copy2(db, copy)
            con = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)
            try:
                rows = con.execute("select gameReleaseKey, coalesce(purchaseDate, addedDate) "
                                   "from ProductPurchaseDates where gameReleaseKey like 'gog\\_%' escape '\\'")
                gog = {k.split("_", 1)[1]: (d or "")[:10] for k, d in rows}
            except sqlite3.Error:
                pass
            finally:
                con.close()
    steam_root = None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam_root = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        pass
    played, _, _ = steam_info([steam_root]) if steam_root and steam_root.is_dir() else ({}, {}, {})
    return gog, played


def release_name(name: str) -> str:
    """A folder or game name reduced for matching: no release prefix, version or punctuation."""
    n = RELEASE_PREFIX.sub("", name)
    n = RELEASE_VERSION.sub("", n)
    return re.sub(r"[^a-z0-9]", "", n.lower())


def acquisition_evidence(entry: dict, install: Path | None, played: dict, steam_installs: dict,
                         files: list[dict]) -> list[tuple[str, str]]:
    ev = []
    sid = str(entry.get("steamId", ""))
    if sid and sid in steam_installs:
        ev.append(("steam", "installed through Steam"))
    if sid and played.get(sid, {}).get("lastPlayed"):
        ev.append(("steam", f"launched from Steam, last {day(played[sid]['lastPlayed'])}"))
    if install and install.is_dir():
        if RELEASE_PREFIX.match(install.name) or (RELEASE_VERSION.search(install.name) and "." in install.name):
            ev.append(("downloaded", f"release-style folder name {install.name}"))
        base = len(install.parts)
        for r, dirs, fs in os.walk(install):
            if len(Path(r).parts) - base >= 3:
                dirs[:] = []
            lower = {f.lower() for f in fs}
            if hit := sorted(lower & CRACK_FILES):
                ev.append(("downloaded", f"{hit[0]} in {slash(Path(r).relative_to(install)) or '.'}"))
            if hit := sorted({d.lower() for d in dirs} & CRACK_DIRS):
                ev.append(("downloaded", f"{hit[0]} folder in the install"))
            if any(f.startswith("goggame-") and f.endswith(".info") for f in lower):
                ev.append(("gog", "GOG install marker (goggame-*.info)"))
            if ".egstore" in {d.lower() for d in dirs}:
                ev.append(("epic", "Epic install marker (.egstore)"))
    for f in files:
        if {x.lower() for x in Path(f["path"]).parts} & EMULATOR_DIRS:
            ev.append(("downloaded", "saves in an emulator folder"))
            break
    gog_owned, steam_account = ACCOUNTS
    if (gid := str(entry.get("gogId", ""))) and gid in gog_owned:
        bought = gog_owned[gid]
        later = ", after the last save" if bought and entry.get("lastSave") and bought > entry["lastSave"] else ""
        ev.append(("gog", f"in your GOG library{', bought ' + bought if bought else ''}{later}"))
    if sid and (p := steam_account.get(sid)) and (p["playtimeMinutes"] or p["lastPlayed"]):
        hours = f"{p['playtimeMinutes'] / 60:.1f} h, " if p["playtimeMinutes"] else ""
        ev.append(("steam", f"played on your current Steam account ({hours}last {day(p['lastPlayed'])})"))
        entry["steamAccount"] = {"playtimeHours": round(p["playtimeMinutes"] / 60, 1),
                                 "lastPlayed": day(p["lastPlayed"]) if p["lastPlayed"] else None}
    seen, out = set(), []
    for e in ev:  # one line per distinct finding
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:8]


def vdf(text: str) -> dict:
    """Valve's KeyValues text format, enough of it for localconfig.vdf and appmanifest files."""
    root, stack, k = {}, [], None
    cur = root
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        tok, brace = m[1], m[2]
        if brace == "{":
            new = {}
            cur[k] = new
            stack.append(cur)
            cur, k = new, None
        elif brace == "}":
            cur = stack.pop() if stack else root
        elif k is None:
            k = tok
        else:
            cur[k], k = tok, None
    return root


def find_key(d: dict, name: str):
    """First nested value under a key named `name`, case-insensitively."""
    for k, v in d.items():
        if k.lower() == name.lower():
            return v
        if isinstance(v, dict) and (found := find_key(v, name)) is not None:
            return found
    return None


def steam_info(steam_roots: list[Path]) -> tuple[dict, dict, dict]:
    """{appid: {playtimeMinutes, lastPlayed}}, {appid: installdir}, {appid: workshop item names}."""
    played, installs, workshop = {}, {}, {}
    for root in steam_roots:
        for cfg in root.glob("userdata/*/config/localconfig.vdf"):
            # Several sections are called "apps"; take every numeric app id that carries
            # LastPlayed or Playtime, wherever it sits. Older clients record only LastPlayed.
            stack = [vdf(cfg.read_text(encoding="utf-8", errors="replace"))]
            while stack:
                d = stack.pop()
                for k, v in d.items():
                    if not isinstance(v, dict):
                        continue
                    if k.isdigit() and ("LastPlayed" in v or "Playtime" in v):
                        p = played.setdefault(k, {"playtimeMinutes": 0, "lastPlayed": 0})
                        p["playtimeMinutes"] += int(v.get("Playtime", 0) or 0)
                        p["lastPlayed"] = max(p["lastPlayed"], int(v.get("LastPlayed", 0) or 0))
                    else:
                        stack.append(v)
        for acf in root.glob("steamapps/appmanifest_*.acf"):
            st = vdf(acf.read_text(encoding="utf-8", errors="replace")).get("AppState", {})
            if st.get("appid") and st.get("installdir"):
                installs[st["appid"]] = root / "steamapps" / "common" / st["installdir"]
        for d in root.glob("steamapps/workshop/content/*"):
            workshop[d.name] = sorted(c.name for c in d.iterdir())
    return played, installs, workshop


def placeholder_regex(pattern: str, ctx: dict) -> re.Pattern:
    """A manifest path pattern (placeholders, * globs) as a regex matching a path or its prefix."""
    out, i = "", 0
    for m in re.finditer(r"<(\w+)>|\*\*|\*|[^<*]+", pattern):
        tok = m[0]
        if m[1]:
            vals = ctx.get(m[1])
            out += "(?:" + "|".join(re.escape(slash(v)) for v in vals) + ")" if vals else "[^/]+"
        elif tok == "**":
            out += ".*"
        elif tok == "*":
            out += "[^/]*"
        else:
            out += re.escape(tok)
    return re.compile("^" + out + "(?:/|$)", re.IGNORECASE)


def day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def mod_folders(top: Path, depth: int = 3) -> dict[str, list[str]]:
    """Mod-like folders under `top` (a few levels down), each with the names inside it."""
    found = {}
    if not top.is_dir():
        return found
    base_depth = len(top.parts)
    for r, dirs, _ in os.walk(top):
        if len(Path(r).parts) - base_depth >= depth:
            dirs[:] = []
        for d in list(dirs):
            if d.lower() in MOD_DIRS:
                p = Path(r) / d
                names = sorted(c.name for c in p.iterdir() if c.name.lower() not in ("desktop.ini",))
                if names:
                    found[slash(p.relative_to(top))] = names[:40]
    return found


def cmd_index(a, arc: Archive) -> None:
    t = arc.target(a.name)
    cfg_dir = arc.config(a.name)
    cfg = read_json(cfg_dir / "config.yaml", {})
    r = ludusavi("--try-manifest-update", "manifest", "show", "--api", config=cfg_dir)
    manifest = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    scope = Path(t["scope"])
    profiles = old_profiles(scope) if t["kind"] == "old-drive" else [Path.home()]
    drive = scope if t["kind"] == "old-drive" else SYSTEM_DRIVE
    ctx = {"home": profiles, "osUserName": [p.name for p in profiles],
           "winAppData": [p / "AppData/Roaming" for p in profiles],
           "winLocalAppData": [p / "AppData/Local" for p in profiles],
           "winLocalAppDataLow": [p / "AppData/LocalLow" for p in profiles],
           "winDocuments": [p / "Documents" for p in profiles],
           "winPublic": [drive / "Users/Public"], "winProgramData": [drive / "ProgramData"],
           "winDir": [drive / "Windows"]}
    roots = cfg.get("roots", [])
    steam_roots = [Path(r["path"]) for r in roots if r["store"] == "steam"]
    install_roots = [Path(r["path"]) for r in roots if r["store"] in ("other", "gogGalaxy")]
    played, steam_installs, workshop = steam_info(steam_roots)
    global ACCOUNTS
    ACCOUNTS = account_libraries()

    games, emulated = {}, {}
    backup = arc.root / a.name / "backup"
    for m in sorted(backup.glob("*/mapping.yaml")):
        game, stored = read_mapping(m)
        text = m.read_text(encoding="utf-8")
        when = re.findall(r'when: "([^"]+)"', text)
        man = manifest.get(game, {})
        tagged = [(placeholder_regex(pat, ctx), info.get("tags", []))
                  for pat, info in (man.get("files") or {}).items()
                  if not info.get("when") or any(w.get("os") in (None, "windows") for w in info["when"])]
        files = []
        for p, e in stored.items():
            drv, rest = p.split(":", 1)
            copy = m.parent / ("" if e["folder"] == "." else e["folder"]) / f"drive-{drv}" / rest.lstrip("/")
            mtime = copy.stat().st_mtime if copy.exists() else 0
            tags = next((tg for rx, tg in tagged if rx.match(p)), [])
            files.append({"path": p, "size": int(e.get("size", 0)), "mtime": mtime, "tags": tags})
        noise = [f for f in files if {p.lower() for p in Path(f["path"]).parts} & NOISE_DIRS]
        kept = [f for f in files if f not in noise]
        saves = [f for f in kept if "save" in f["tags"]] or \
                [f for f in kept if "config" not in f["tags"] and Path(f["path"]).suffix.lower() not in
                 {".ini", ".cfg", ".log", ".txt", ".xml", ".json"} | IMAGE_EXTS]
        timeline = saves or files
        dated = sorted(f["mtime"] for f in timeline if f["mtime"])
        by_year = {}
        for ts in dated:
            by_year[day(ts)[:4]] = by_year.get(day(ts)[:4], 0) + 1
        recent = sorted(saves, key=lambda f: f["mtime"], reverse=True)[:10]
        locations = sorted({slash(Path(f["path"]).parent) for f in files})
        common = os.path.commonpath([Path(f["path"]).parent for f in files]) if files else ""
        entry = {
            "name": game,
            "backedUp": when[-1] if when else None,
            "files": len(files), "bytes": sum(f["size"] for f in files),
            "saveFiles": len(saves),
            "configFiles": sorted({Path(f["path"]).name for f in files if "config" in f["tags"]})[:30],
            "screenshotsInSaves": sum(1 for f in files if Path(f["path"]).suffix.lower() in IMAGE_EXTS),
            "firstSave": day(dated[0]) if dated else None,
            "lastSave": day(dated[-1]) if dated else None,
            "activeDays": len({day(ts) for ts in dated}),
            "savesByYear": by_year,
            "savesByMonth": {mo: sum(1 for ts in dated if day(ts)[:7] == mo)
                             for mo in sorted({day(ts)[:7] for ts in dated})},
            "recentSaves": [{"name": slash(Path(f["path"]).relative_to(common)) if common else f["path"],
                             "date": day(f["mtime"])} for f in recent],
            "locations": locations[:20],
        }
        if sid := (man.get("steam") or {}).get("id"):
            entry["steamId"] = sid
            p = played.get(str(sid))
            if p and (p["playtimeMinutes"] or p["lastPlayed"]):
                entry["steam"] = {"playtimeHours": round(p["playtimeMinutes"] / 60, 1),
                                  "lastPlayed": day(p["lastPlayed"]) if p["lastPlayed"] else None}
            if workshop.get(str(sid)):
                entry["steamWorkshopItems"] = workshop[str(sid)][:100]
        if gid := (man.get("gog") or {}).get("id"):
            entry["gogId"] = gid
        if man.get("cloud"):
            entry["cloudSaves"] = sorted(k for k, v in man["cloud"].items() if v)
        if man.get("registry"):
            entry["registryKeys"] = sorted(man["registry"])
            if t["kind"] == "old-drive":
                entry["registryNote"] = "not in this backup; the old profile's NTUSER.DAT is copied with the personal data"
        # Install folder: Steam's own record, else a known install-folder name under an install
        # root, also when it carries a release prefix or version ("IGG-Name.v1.2").
        names = {release_name(n) for n in (man.get("installDir") or {})} | {release_name(game)}
        install = steam_installs.get(str(entry.get("steamId", "")))
        if not install:
            install = next((c for r in install_roots if r.is_dir() for c in r.iterdir()
                            if c.is_dir() and release_name(c.name) in names), None)
        for f in files:  # emulator save folders are named by Steam app id
            parts = [x.lower() for x in Path(f["path"]).parts]
            for i, x in enumerate(parts[:-1]):
                if x in EMULATOR_DIRS and parts[i + 1].isdigit():
                    emulated.setdefault(parts[i + 1], []).append((x, f))
        mods = {}
        for loc in {Path(common)} if common else set():
            for k, v in mod_folders(loc, 2).items():
                mods[f"saves: {k}"] = v
        if install and install.exists():
            entry["installFolder"] = slash(install)
            for k, v in mod_folders(install).items():
                mods[f"install: {k}"] = v
        if mods:
            entry["mods"] = mods
        entry["_evidence"] = acquisition_evidence(entry, install, played, steam_installs, files)
        games[game] = entry

    # Saves in emulator folders belong to the game with that Steam app id; that's also the only
    # way those folders get a name.
    by_steam_id = {str(v["steam"]["id"]): n for n, v in manifest.items() if (v.get("steam") or {}).get("id")}
    for appid, hits in sorted(emulated.items()):
        name = by_steam_id.get(appid, f"Steam app {appid}")
        dated = sorted(f["mtime"] for _, f in hits if f["mtime"])
        info = {"emulator": sorted({e for e, _ in hits}), "files": len(hits),
                "firstSave": day(dated[0]) if dated else None, "lastSave": day(dated[-1]) if dated else None,
                "storedUnder": sorted({g for g, gi in games.items()
                                       if {slash(Path(f["path"]).parent) for _, f in hits} & set(gi.get("locations", []))})}
        entry = games.setdefault(name, {"name": name, "steamId": int(appid), "savedOnlyByEmulator": True,
                                        "lastSave": info["lastSave"], "firstSave": info["firstSave"],
                                        "files": len(hits), "saveFiles": len(hits), "bytes": 0,
                                        "activeDays": len({day(ts) for ts in dated}), "_evidence": []})
        if entry.get("savedOnlyByEmulator") and not entry["_evidence"]:
            if gid := (manifest.get(name, {}).get("gog") or {}).get("id"):
                entry["gogId"] = gid
            entry["_evidence"] = acquisition_evidence(entry, None, played, steam_installs, [])
        entry["emulatorSaves"] = info
        entry["_evidence"].append(("downloaded", f"saves in {'/'.join(info['emulator'])} emulator folder {appid}"))

    overrides = {k.lower(): v for k, v in (arc.custom.get("acquired") or {}).items()}
    for g in games.values():
        evidence = g.pop("_evidence", [])
        kinds = {k for k, _ in evidence}
        stores = sorted(kinds - {"downloaded"})
        if g["name"].lower() in overrides:
            g["acquired"], g["acquiredSource"] = overrides[g["name"].lower()], "custom-games.json"
        elif stores and "downloaded" in kinds:
            g["acquired"] = "mixed: " + ", ".join(stores) + " and downloaded"
        elif stores:
            g["acquired"] = ", ".join(stores)
        elif "downloaded" in kinds:
            g["acquired"] = "downloaded"
        else:
            g["acquired"] = "unknown"
        if evidence:
            g["acquiredEvidence"] = [e for _, e in evidence]

    out = arc.root / a.name
    write_json(out / "games.json", {"target": a.name, "scope": t["scope"], "games": games})
    write_index_md(out / "games.md", a.name, t, games)
    with_play = sum(1 for g in games.values() if "steam" in g)
    with_mods = sum(1 for g in games.values() if "mods" in g or "steamWorkshopItems" in g)
    acquired = {}
    for g in games.values():
        k = g["acquired"].split(":")[0]
        acquired[k] = acquired.get(k, 0) + 1
    print(f"indexed {len(games)} games: {with_play} with Steam play time, {with_mods} with mods\n"
          f"acquired: {', '.join(f'{k} {n}' for k, n in sorted(acquired.items(), key=lambda x: -x[1]))}\n"
          f"{out / 'games.json'}\n{out / 'games.md'}")


def write_index_md(path: Path, name: str, t: dict, games: dict) -> None:
    rows = sorted(games.values(), key=lambda g: g.get("lastSave") or "", reverse=True)
    lines = [f"# Game saves: {name}", "", f"From `{t['scope']}`, newest save first.", ""]
    for g in rows:
        lines.append(f"## {g['name']}")
        lines.append("")
        span = f"{g['firstSave']} to {g['lastSave']}" if g.get("firstSave") else "no dates"
        lines.append(f"- **Saves**: {g['saveFiles']} save files ({g['files']} files, "
                     f"{g['bytes'] / 1e6:.1f} MB), {span}, on {g['activeDays']} day{'' if g['activeDays'] == 1 else 's'}")
        lines.append(f"- **Acquired**: {g.get('acquired', 'unknown')}"
                     + (f" ({'; '.join(g['acquiredEvidence'][:3])})" if g.get("acquiredEvidence") else "")
                     + (" (set in custom-games.json)" if g.get("acquiredSource") else ""))
        if g.get("emulatorSaves"):
            e = g["emulatorSaves"]
            lines.append(f"- **Emulator saves**: {e['files']} files in {', '.join(e['emulator'])}, "
                         f"{e['firstSave']} to {e['lastSave']}")
        if g.get("savesByYear"):
            lines.append("- **By year**: " + ", ".join(f"{y}: {n}" for y, n in sorted(g["savesByYear"].items())))
        if g.get("steam"):
            s = g["steam"]
            hours = f"{s['playtimeHours']} h played, " if s["playtimeHours"] else ""
            lines.append(f"- **Steam**: {hours}last played {s.get('lastPlayed') or 'unknown'}")
        if g.get("steamAccount"):
            s = g["steamAccount"]
            hours = f"{s['playtimeHours']} h played, " if s["playtimeHours"] else ""
            lines.append(f"- **Steam account now**: {hours}last played {s.get('lastPlayed') or 'unknown'}")
        ids = [f"Steam {g['steamId']}" if g.get("steamId") else "", f"GOG {g['gogId']}" if g.get("gogId") else ""]
        if any(ids):
            lines.append("- **Store IDs**: " + ", ".join(i for i in ids if i)
                         + (f"; cloud saves on {', '.join(g['cloudSaves'])}" if g.get("cloudSaves") else ""))
        if g.get("recentSaves"):
            lines.append("- **Recent saves**: " + "; ".join(f"`{r['name']}` ({r['date']})" for r in g["recentSaves"][:5]))
        if g.get("installFolder"):
            lines.append(f"- **Installed at**: `{g['installFolder']}`")
        for k, v in (g.get("mods") or {}).items():
            lines.append(f"- **Mods** ({k}): " + ", ".join(f"`{n}`" for n in v[:15]) + (" ..." if len(v) > 15 else ""))
        if g.get("steamWorkshopItems"):
            lines.append(f"- **Steam Workshop**: {len(g['steamWorkshopItems'])} items")
        if g.get("registryKeys"):
            lines.append(f"- **Registry**: " + ", ".join(f"`{k}`" for k in g["registryKeys"][:3]))
        if g.get("screenshotsInSaves"):
            lines.append(f"- **Images with the saves**: {g['screenshotsInSaves']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


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
                        ("verify", "check every current save file is in the backup with the same hash"),
                        ("index", "write games.json and games.md: timeline, play time, mods, store IDs")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("name", help="a target name")
        if name not in ("gaps", "index"):
            s.add_argument("games", nargs="*", help="only these games (exact Ludusavi names)")
    a = p.parse_args()
    if not a.archive:
        die("set GAME_SAVES_HOME or pass --archive: the folder that holds the save archive")
    arc = Archive(Path(a.archive))
    {"add-old-drive": cmd_add_old_drive, "add-live": cmd_add_live, "preview": cmd_preview,
     "gaps": cmd_gaps, "backup": cmd_backup, "verify": cmd_verify, "index": cmd_index}[a.cmd](a, arc)


if __name__ == "__main__":
    main()
