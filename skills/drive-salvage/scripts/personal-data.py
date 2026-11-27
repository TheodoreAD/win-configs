"""Copy a Windows drive's personal data (everything that isn't a game save or software) to a
backup disk, verify it, list what software it had, and find what's still left. The drive is
any root holding a Users folder: an old system drive copy, another disk, or this PC's C:.
See references/retiring-a-drive.md for the procedure.

  python <skill>/scripts/personal-data.py inventory E:/old-c --out D:/_backups/old-drives/old-pc
  python <skill>/scripts/personal-data.py copy E:/old-c --dest D:/_backups/old-drives/old-pc/personal
  python <skill>/scripts/personal-data.py leftovers E:/old-c --dest D:/_backups/old-drives/old-pc/personal \
      --saves D:/_backups/game-saves/old-pc/backup --installs E:/old-c/_games

inventory writes software.json and software.md: what was installed, as names and versions
only, to help reinstall. Program Files and per-profile app folders, Chocolatey and scoop
packages, Steam and GOG installs, and the game install folders you name. On this PC's own
system drive it adds Windows' installed-programs list from the registry.

copy, for every user profile on the drive:
  - the user folders (Desktop, Documents, Pictures, ...) and code folders,
  - personal data that apps keep in AppData: chat histories, mail, unsaved editor tabs,
    notebooks, music libraries and playlists, browser bookmarks and history,
  - profile-root dotfiles and NTUSER.DAT (the old registry, for games that keep saves there).
It keeps the drive-relative paths, so files keep their original dates (robocopy /COPY:DAT),
and then checks every copied file against its original by SHA-1. Running it again copies
only what's new or changed and checks everything again.

It never copies credential stores (.ssh, .gnupg, cloud CLI configs, password databases,
browser saved logins, Windows' credential and key folders, chat clients' plain-text account
files): those go with the drive. leftovers lists the ones it found, by name only.

leftovers walks every file on the drive and sets aside what's in either backup and what's
under Program Files, ProgramData or Windows. What remains is grouped by folder, with counts
of personal-looking file types (documents, images, audio and video, archives, mail and
chat databases, code, CAD), so nothing personal is assumed away. Read it, add what matters
to the lists here or to the game-save archive, and rerun until only software and caches
are left.

Standard library only; robocopy ships with Windows.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

NOT_USERS = {"public", "default", "default user", "all users", "defaultapppool"}
USER_FOLDERS = ["Desktop", "Documents", "Pictures", "Music", "Videos", "Favorites", "Links", "Contacts",
                "Downloads", "Saved Games", "repos", "source", "projects", "OneDrive", "MicrosoftEdgeBackups"]
# Personal data apps keep inside AppData, relative to the profile. Globs allowed.
APP_DATA = [
    "AppData/Roaming/Skype",                          # classic Skype: chat history, received files
    "AppData/Roaming/Microsoft/Skype for Desktop",    # newer Skype; the service shut down in 2025
    "AppData/Roaming/.purple/logs",                   # Pidgin chat logs (accounts.xml stays out)
    "AppData/Roaming/Notepad++/backup",               # unsaved Notepad++ tabs
    "AppData/Roaming/MusicBee", "AppData/Roaming/Winamp", "AppData/Roaming/foobar2000",
    "AppData/Local/Microsoft/OneNote",                # OneNote notebook backups
    "AppData/Local/Microsoft/Outlook",                # .pst/.ost mail
    "AppData/Roaming/Microsoft/Signatures",           # Outlook signatures
    "AppData/Roaming/Microsoft/Sticky Notes",         # Sticky Notes before Windows 10 1607
    "AppData/Local/Packages/Microsoft.MicrosoftStickyNotes_*/LocalState",
    "AppData/Roaming/Thunderbird/Profiles",
    "AppData/Roaming/Code/User/snippets",             # VS Code snippets
]
PROFILE_FILES = [
    ".gitconfig", ".gitconfig.backup", ".bash_history", ".bashrc", ".bash_profile", ".profile", ".vimrc",
    ".zshrc", ".python_history", "NTUSER.DAT",
    "AppData/Roaming/Notepad++/session.xml",
    "AppData/Roaming/Code/User/settings.json", "AppData/Roaming/Code/User/keybindings.json",
    "AppData/Local/Google/Chrome/User Data/*/Bookmarks", "AppData/Local/Google/Chrome/User Data/*/Bookmarks.bak",
    "AppData/Local/Google/Chrome/User Data/*/History",
    "AppData/Local/Microsoft/Edge/User Data/*/Bookmarks", "AppData/Local/Microsoft/Edge/User Data/*/History",
    "AppData/Roaming/Mozilla/Firefox/Profiles/*/places.sqlite",
    "AppData/Roaming/Mozilla/Firefox/Profiles/*/bookmarkbackups/*",
]
# Never copied: secrets. Matched against folder and file names anywhere in a copied tree.
SECRET_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", "credentials", "protect", "vault", "crypto", "tdata"}
SECRET_FILES = {"login data", "login data-journal", "logins.json", "key3.db", "key4.db", "accounts.xml",
                "cookies", "cookies-journal", "web data"}
SECRET_EXTS = {".kdbx", ".kdb", ".pfx", ".p12", ".pem", ".ppk", ".key"}

SOFTWARE_TOP = {"program files", "program files (x86)", "windows", "programdata",
                "$recycle.bin", "system volume information"}
# Software inside the Users tree: ProgramData's old alias, the default profile, and app installs
# that live in a profile. Paths relative to Users/<name>/; "*" means any profile.
SOFTWARE_IN_USERS = {"all users", "default", "default user"}
SOFTWARE_IN_PROFILE = {"appdata/local/programs", ".nuget", ".vscode/extensions", "appdata/local/package cache",
                       "appdata/roaming/code/cachedextensionvsixs", "appdata/local/microsoft/windowsapps"}
# Reported for a decision, never copied. Other secrets (cookies, bundled certificates) are
# skipped quietly: nobody needs to decide about them.
DECIDE_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube"}
DECIDE_FILES = {"login data", "logins.json", "key3.db", "key4.db", "accounts.xml"}
DECIDE_EXTS = {".kdbx", ".kdb", ".pfx", ".p12", ".ppk", ".key"}
CACHE_DIRS = {"cache", "code cache", "gpucache", "temp", "inetcache", "shadercache", "service worker",
              "cachestorage", "webcache", "d3dscache", "blob_storage", "crashdumps", "glcache"}
GROUPS = {
    "documents": {".doc", ".docx", ".odt", ".rtf", ".pdf", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx",
                  ".txt", ".md", ".one", ".onepkg", ".epub", ".mobi"},
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".raw", ".cr2", ".nef", ".psd", ".tif",
               ".tiff", ".webp"},
    "audio/video": {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".mp4", ".mkv", ".avi", ".mov", ".wmv"},
    "archives": {".zip", ".7z", ".rar", ".tar", ".gz", ".iso"},
    "mail/chat/db": {".pst", ".ost", ".eml", ".mbox", ".msg", ".db", ".sqlite", ".sqlite3", ".ldb"},
    "code": {".py", ".js", ".ts", ".cs", ".java", ".cpp", ".c", ".h", ".ipynb", ".sql", ".ps1", ".sh"},
    "cad/design": {".dwg", ".dxf", ".skp", ".pln", ".pla", ".3ds", ".blend", ".max", ".rvt", ".ifc"},
}
EXT_GROUP = {e: g for g, es in GROUPS.items() for e in es}


def key(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def is_secret(p: Path) -> bool:
    return (p.name.lower() in SECRET_FILES or p.suffix.lower() in SECRET_EXTS
            or any(part.lower() in SECRET_DIRS for part in p.parts))


def profiles(drive: Path) -> list[Path]:
    users = drive / "Users"
    return sorted(p for p in users.iterdir() if p.is_dir() and not p.is_symlink()
                  and p.name.lower() not in NOT_USERS) if users.is_dir() else []


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def selection(drive: Path) -> tuple[list[Path], list[Path]]:
    """(folders, files) to copy, as paths on the drive."""
    folders, files = [], []
    for prof in profiles(drive):
        folders += [prof / f for f in USER_FOLDERS if (prof / f).is_dir()]
        for pat in APP_DATA:
            folders += [p for p in prof.glob(pat) if p.is_dir()]
        for pat in PROFILE_FILES:
            files += [p for p in prof.glob(pat) if p.is_file() and not is_secret(p)]
    return folders, files


def robocopy(args: list[str], log: Path) -> None:
    r = subprocess.run(["robocopy", *args, "/COPY:DAT", "/R:1", "/W:1", "/NP", "/XJ", f"/LOG+:{log}"],
                       capture_output=True)
    if r.returncode >= 8:
        sys.exit(f"robocopy failed (exit {r.returncode}) on {args[0]}; see {log}")


def cmd_copy(a) -> None:
    drive, dest = Path(a.drive), Path(a.dest)
    if not (drive / "Users").is_dir():
        sys.exit(f"{drive} has no Users folder; point it at the old drive's root")
    dest.mkdir(parents=True, exist_ok=True)
    log = dest / "robocopy.log"
    folders, files = selection(drive)
    xd = sorted(SECRET_DIRS)
    xf = [f"*{e}" for e in sorted(SECRET_EXTS)] + sorted(SECRET_FILES)
    for src in folders:
        robocopy([str(src), str(dest / src.relative_to(drive)), "/E", "/DCOPY:DAT", "/NDL",
                  "/XD", *xd, "/XF", *xf], log)
    for src in files:
        robocopy([str(src.parent), str(dest / src.parent.relative_to(drive)), src.name], log)
    # Verify: every file in the selection, minus secrets and junction targets, is in dest unchanged.
    n = size = 0
    bad = []
    for src in folders:
        for r, ds, fs in os.walk(src):
            ds[:] = [d for d in ds if d.lower() not in SECRET_DIRS and not os.path.islink(os.path.join(r, d))]
            for f in fs:
                s = Path(r) / f
                if is_secret(s):
                    continue
                n += 1
                size += s.stat().st_size
                d = dest / s.relative_to(drive)
                if not d.is_file() or sha1(s) != sha1(d):
                    bad.append(s)
    for s in files:
        n += 1
        size += s.stat().st_size
        d = dest / s.relative_to(drive)
        if not d.is_file() or sha1(s) != sha1(d):
            bad.append(s)
    print(f"{len(folders)} folders and {len(files)} files selected; {n} files, {size / 1e6:.1f} MB checked in {dest}")
    for b in bad[:10]:
        print(f"  MISSING OR DIFFERENT: {b.relative_to(drive)}")
    sys.exit(1 if bad else 0)


def bucket(rel: Path) -> str:
    parts = rel.parts
    if len(parts) >= 3 and parts[0].lower() == "users":
        if len(parts) >= 5 and parts[2].lower() == "appdata":
            return "/".join(parts[:5])
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def cmd_leftovers(a) -> None:
    drive, dest = Path(a.drive), Path(a.dest)
    covered = set()
    if a.saves:
        for m in Path(a.saves).glob("*/mapping.yaml"):
            for line in m.read_text(encoding="utf-8").splitlines():
                if mm := re.match(r'^\s{6,}"(.+)":$', line):
                    covered.add(key(mm[1]))
    if dest.is_dir():
        for r, _, fs in os.walk(dest):
            for f in fs:
                covered.add(key(drive / (Path(r) / f).relative_to(dest)))
    installs = [key(i) for i in a.installs]
    stats, sizes, total, decide = defaultdict(Counter), Counter(), Counter(), set()

    def software(rel: Path, full: Path) -> bool:
        parts = [x.lower() for x in rel.parts]
        if parts and parts[0] in SOFTWARE_TOP:
            return True
        if len(parts) >= 2 and parts[0] == "users":
            if parts[1] in SOFTWARE_IN_USERS:
                return True
            if "/".join(parts[2:]) in SOFTWARE_IN_PROFILE:
                return True
        return key(full) in installs

    for r, ds, fs in os.walk(drive):
        rel = Path(r).relative_to(drive)
        if software(rel, Path(r)):
            ds[:] = []
            total["software"] += sum(len(f) for _, _, f in os.walk(r))
            continue
        keep = []
        for d in ds:
            if os.path.islink(os.path.join(r, d)):
                continue
            if d.lower() in DECIDE_DIRS:
                decide.add(str(rel / d))
            elif d.lower() not in SECRET_DIRS and d.lower() not in CACHE_DIRS:
                keep.append(d)
        ds[:] = keep
        for f in fs:
            p = Path(r) / f
            if key(p) in covered:
                total["in a backup"] += 1
                continue
            if is_secret(p):
                if p.name.lower() in DECIDE_FILES or p.suffix.lower() in DECIDE_EXTS:
                    decide.add(str(rel / f))
                continue
            total["left"] += 1
            b = bucket(rel / f)
            try:
                sizes[b] += p.stat().st_size
            except OSError:
                pass
            if g := EXT_GROUP.get(p.suffix.lower()):
                stats[b][g] += 1
    print(", ".join(f"{k}: {v}" for k, v in total.items()) + " files")
    print("\nFolders with personal-looking files that neither backup holds (software trees and caches left out):")
    for b in sorted(stats, key=lambda k: -sum(stats[k].values()))[: a.limit]:
        print(f"  {b}  [{sizes[b] / 1e6:.1f} MB]  " + ", ".join(f"{g} {n}" for g, n in stats[b].most_common()))
    if decide:
        print("\nCredential stores, not copied (decide on these yourself):")
        for s in sorted(decide)[:40]:
            print(f"  {s}")


def child_names(p: Path) -> list[str]:
    try:
        return sorted(c.name for c in p.iterdir() if c.is_dir() and not c.name.startswith("."))
    except OSError:
        return []


def vdf_values(text: str, name: str) -> list[str]:
    return re.findall(rf'"{name}"\s+"([^"]*)"', text, re.IGNORECASE)


def registry_programs() -> list[dict]:
    """Windows' installed-programs list (the Uninstall keys), for this PC only."""
    import winreg
    found = []
    for hive, path in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                    vals = {}
                    for v in ("DisplayName", "DisplayVersion", "Publisher", "InstallDate", "SystemComponent"):
                        try:
                            vals[v] = winreg.QueryValueEx(k, v)[0]
                        except OSError:
                            pass
                    if vals.get("DisplayName") and not vals.get("SystemComponent"):
                        found.append({"name": vals["DisplayName"], "version": vals.get("DisplayVersion", ""),
                                      "publisher": vals.get("Publisher", ""), "installed": vals.get("InstallDate", "")})
            except OSError:
                continue
    unique = {(p["name"], p["version"]): p for p in found}
    return sorted(unique.values(), key=lambda p: p["name"].lower())


def cmd_inventory(a) -> None:
    drive, out = Path(a.drive), Path(a.out)
    inv: dict[str, list] = {}
    for pf in ("Program Files", "Program Files (x86)"):
        if (drive / pf).is_dir():
            inv[pf] = [{"name": n, "contains": child_names(drive / pf / n)[:15]}
                       for n in child_names(drive / pf) if n.lower() not in ("common files", "windowsapps")]
    if (drive / "ProgramData/chocolatey/lib").is_dir():
        inv["Chocolatey packages"] = child_names(drive / "ProgramData/chocolatey/lib")
    for prof in profiles(drive):
        if (prof / "scoop/apps").is_dir():
            inv[f"scoop apps ({prof.name})"] = child_names(prof / "scoop/apps")
        if (prof / "AppData/Local/Programs").is_dir():
            inv[f"per-user programs ({prof.name})"] = child_names(prof / "AppData/Local/Programs")
    steam_games = []
    for steam in (drive / "Program Files (x86)/Steam", drive / "Program Files/Steam"):
        libs = [steam]
        lf = steam / "steamapps/libraryfolders.vdf"
        if lf.is_file():
            libs += [Path(p.replace("\\\\", "\\")) for p in vdf_values(lf.read_text(errors="replace"), "path")]
        for lib in libs:
            for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                t = acf.read_text(encoding="utf-8", errors="replace")
                steam_games.append({"name": (vdf_values(t, "name") or ["?"])[0],
                                    "appid": (vdf_values(t, "appid") or ["?"])[0], "library": str(lib)})
    if steam_games:
        inv["Steam games installed"] = sorted({(g["name"], g["appid"]): g for g in steam_games}.values(),
                                              key=lambda g: g["name"].lower())
    for gog in (drive / "Program Files (x86)/GOG Galaxy/Games", drive / "GOG Games"):
        if gog.is_dir():
            inv[f"GOG installs ({gog})"] = child_names(gog)
    for i in a.installs:
        inv[f"game installs ({i})"] = child_names(Path(i))
    system_drive = os.environ.get("SystemDrive", "C:")
    if key(drive) == key(system_drive + "\\") or key(drive) == key(system_drive):
        inv["Windows installed programs"] = registry_programs()
    elif (drive / "Windows/System32/config/SOFTWARE").is_file():
        inv["note"] = ["This drive has its own Windows registry (Windows\\System32\\config\\SOFTWARE). Its "
                       "installed-programs list can be read by loading the hive in an admin shell."]
    out.mkdir(parents=True, exist_ok=True)
    (out / "software.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"# Software on {drive}", "", "Names and versions only, to help reinstall. Nothing here was copied.", ""]
    for section, items in inv.items():
        lines += [f"## {section}", ""]
        for it in items:
            if isinstance(it, dict) and "contains" in it:
                lines.append(f"- **{it['name']}**" + (f" — {', '.join(it['contains'])}" if it["contains"] else ""))
            elif isinstance(it, dict) and "appid" in it:
                lines.append(f"- **{it['name']}** — Steam {it['appid']}")
            elif isinstance(it, dict):
                lines.append(f"- **{it['name']}** — {' '.join(x for x in (it['version'], it['publisher']) if x)}")
            else:
                lines.append(f"- {it}")
        lines.append("")
    (out / "software.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"{sum(len(v) for v in inv.values())} entries in {len(inv)} sections\n{out / 'software.md'}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("copy", help="copy the personal data and verify it")
    s.add_argument("drive", help="the old drive's root (the folder holding Users)")
    s.add_argument("--dest", required=True, help="where the copy goes, e.g. D:/_backups/old-drives/<name>/personal")
    s = sub.add_parser("leftovers", help="what neither backup holds, grouped by folder")
    s.add_argument("drive")
    s.add_argument("--dest", required=True, help="the personal copy made by `copy`")
    s.add_argument("--saves", help="the game-save target's backup folder")
    s.add_argument("--installs", nargs="*", default=[],
                   help="game install folders: software, their saves already taken by game-saves.py")
    s.add_argument("--limit", type=int, default=60, help="folders to list (default 60)")
    s = sub.add_parser("inventory", help="list the software the drive had: names and versions only")
    s.add_argument("drive")
    s.add_argument("--out", required=True, help="folder for software.json and software.md")
    s.add_argument("--installs", nargs="*", default=[], help="game install folders to list")
    a = p.parse_args()
    {"copy": cmd_copy, "leftovers": cmd_leftovers, "inventory": cmd_inventory}[a.cmd](a)


if __name__ == "__main__":
    main()
