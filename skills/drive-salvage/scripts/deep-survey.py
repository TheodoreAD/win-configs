"""Deep read-only survey of a drive: personal data that the profile copy and the leftover scan
both treat as something else. Run it after `personal-data.py leftovers`, read every section, and
add what matters with `copy --extra` or custom games.

  python <skill>/scripts/deep-survey.py E:/ D:/_backups/old-drives/<name>/personal \
      D:/_backups/game-saves/<target>/backup D:/_backups/old-drives/<name>/deep-survey.md

Sections:
- the Recycle Bin: each deleted item's original path, size and deletion date (from its $I file)
- every top-level folder, and those in Windows.old, with personal-looking file counts
- ProgramData folders holding documents, images, media or archives
- game installs: screenshot and mod folders, and files changed 30+ days after the install's
  median date that no backup holds (saves, state and content added later, not the game itself)
- Steam's data: userdata, screenshots, Workshop items
- portable tool folders: their settings files, newest first
- every top-level item in each profile that the copy holds only partly, or not at all

Standard library only. Reads, never writes, except the report.
"""
import os
import re
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
drive, copy_dir, saves_dir, report = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
norm = lambda p: os.path.normcase(os.path.normpath(str(p)))
GROUPS = {
    "docs": {".doc", ".docx", ".odt", ".rtf", ".pdf", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".txt", ".md",
             ".one", ".epub", ".mobi"},
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".raw", ".cr2", ".nef", ".psd", ".tif", ".tiff", ".webp"},
    "audio/video": {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".mp4", ".mkv", ".avi", ".mov", ".wmv"},
    "archives": {".zip", ".7z", ".rar", ".tar", ".gz", ".iso"},
    "code": {".py", ".js", ".ts", ".cs", ".java", ".cpp", ".ipynb", ".sql", ".ps1", ".sh"},
}
EXT = {e: g for g, es in GROUPS.items() for e in es}
out = []
day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))

covered = set()
for r, _, fs in os.walk(copy_dir):
    for f in fs:
        covered.add(norm(drive / (Path(r) / f).relative_to(copy_dir)))
for m in saves_dir.glob("*/mapping.yaml"):
    for line in m.read_text(encoding="utf-8").splitlines():
        if mm := re.match(r'^\s{6,}"(.+)":$', line):
            covered.add(norm(mm[1]))


def stats(p: Path):
    n = size = 0
    types = Counter()
    newest = 0
    for r, ds, fs in os.walk(p):
        ds[:] = [d for d in ds if not os.path.islink(os.path.join(r, d))]
        for f in fs:
            fp = os.path.join(r, f)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            n += 1
            size += st.st_size
            newest = max(newest, st.st_mtime)
            if g := EXT.get(os.path.splitext(f)[1].lower()):
                types[g] += 1
    return n, size, types, newest


def line(label, p):
    n, size, types, newest = stats(p)
    return (f"- **{label}**: {n} files, {size / 1e9:.2f} GB, newest {day(newest) if newest else '-'}"
            + (f"; {', '.join(f'{k} {v}' for k, v in types.most_common())}" if types else ""))


# 1. Recycle Bin: $I files hold the original path, size and deletion time.
out += ["## Recycle Bin", ""]
rb = drive / "$RECYCLE.BIN"
items = []
for sid in rb.iterdir() if rb.is_dir() else []:
    try:
        entries = list(sid.iterdir())
    except OSError as e:
        out.append(f"- unreadable: {sid.name} ({e.strerror})")
        continue
    for i in entries:
        if i.name.upper().startswith("$I"):
            b = i.read_bytes()
            ver, size, ft = struct.unpack_from("<qqq", b, 0)
            if ver == 2:
                nlen = struct.unpack_from("<i", b, 24)[0]
                name = b[28:28 + 2 * nlen].decode("utf-16-le", errors="replace").rstrip("\0")
            else:
                name = b[24:24 + 520].decode("utf-16-le", errors="replace").split("\0")[0]
            when = time.strftime("%Y-%m-%d", time.gmtime(ft / 1e7 - 11644473600)) if ft else "-"
            data = sid / ("$R" + i.name[2:])
            n, dsize, types, _ = stats(data) if data.is_dir() else (1, data.stat().st_size if data.exists() else 0, Counter(), 0)
            items.append((when, name, size, data.exists(), n, types))
items.sort(reverse=True)
out.append(f"{len(items)} deleted items")
for when, name, size, exists, n, types in items[:60]:
    out.append(f"- {when}  `{name}`  {size / 1e6:.1f} MB{'' if exists else ' (data gone)'}"
               + (f", {n} files" if n > 1 else "") + (f"; {', '.join(f'{k} {v}' for k, v in types.most_common())}" if types else ""))

# 2. Top-level folders outside Users.
out += ["", "## Top-level folders", ""]
for p in sorted(drive.iterdir(), key=lambda p: p.name.lower()):
    if p.is_dir() and p.name.lower() not in ("users", "$recycle.bin", "system volume information", "windows",
                                              "documents and settings", "recovery", "config.msi", "$winreagent"):
        out.append(line(p.name, p))
if (drive / "Windows.old").is_dir():
    out += ["", "Inside Windows.old:"]
    for p in sorted((drive / "Windows.old").iterdir(), key=lambda p: p.name.lower()):
        if p.is_dir() and p.name.lower() not in ("windows", "$windows.~bt"):
            out.append(line(p.name, p))

# 3. ProgramData children with personal-looking content.
out += ["", "## ProgramData (folders with personal-looking files)", ""]
for base in (drive / "ProgramData", drive / "Windows.old" / "ProgramData"):
    for p in sorted(base.iterdir(), key=lambda p: p.name.lower()) if base.is_dir() else []:
        if p.is_dir() and not p.is_symlink() and p.name.lower() not in ("microsoft", "package cache", "packages", "nvidia", "nvidia corporation", "intel", "regid.1991-06.com.microsoft"):
            n, size, types, newest = stats(p)
            if types.get("docs", 0) + types.get("images", 0) + types.get("audio/video", 0) + types.get("archives", 0) > 0:
                out.append(f"- **{base.parent.name}/ProgramData/{p.name}**: {n} files, {size / 1e6:.0f} MB, newest {day(newest) if newest else '-'}; "
                           + ", ".join(f"{k} {v}" for k, v in types.most_common()))

# 4. Game installs: screenshots, mods, files changed long after install.
out += ["", "## Game installs: user content", ""]
for root in (drive / "games", drive / "_games"):
    for g in sorted(root.iterdir(), key=lambda p: p.name.lower()) if root.is_dir() else []:
        if not g.is_dir():
            continue
        mt, shots, mods = [], [], []
        later = []
        files = []
        for r, ds, fs in os.walk(g):
            ds[:] = [d for d in ds if not os.path.islink(os.path.join(r, d))]
            for d in ds:
                dl = d.lower()
                if "screenshot" in dl or dl in ("screens", "captures", "photos"):
                    shots.append(os.path.relpath(os.path.join(r, d), g))
                if dl in ("mods", "mod", "workshop", "bepinex", "usermods", "custom", "usermaps", "maps_user"):
                    mods.append(os.path.relpath(os.path.join(r, d), g))
            for f in fs:
                fp = os.path.join(r, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                files.append((st.st_mtime, fp, st.st_size))
        if not files:
            continue
        times = sorted(t for t, _, _ in files)
        installed = times[len(times) // 2]  # most of an install shares its install date
        for t, fp, size in files:
            if t > installed + 30 * 86400 and norm(fp) not in covered:
                ext = os.path.splitext(fp)[1].lower()
                if ext not in (".log", ".dmp", ".tmp", ".dll", ".exe") and "cache" not in fp.lower() and "logs" not in fp.lower():
                    later.append((t, fp, size))
        shot_files = sum(stats(g / s)[0] for s in shots)
        if shots and shot_files or mods or later:
            out.append(f"- **{root.name}/{g.name}** (installed ~{day(installed)})")
            if shots and shot_files:
                out.append(f"  - screenshots: {', '.join(shots[:3])} ({shot_files} files)")
            if mods:
                out.append(f"  - mod folders: {', '.join(mods[:4])}")
            if later:
                later.sort(reverse=True)
                kinds = Counter(os.path.splitext(fp)[1].lower() or "(none)" for _, fp, _ in later)
                out.append(f"  - {len(later)} files changed later, not in a backup, newest {day(later[0][0])}: "
                           + ", ".join(f"{k} {v}" for k, v in kinds.most_common(6))
                           + f"; e.g. {os.path.relpath(later[0][1], g)}")

# 5. Steam data: screenshots, workshop, userdata.
out += ["", "## Steam", ""]
for steam in (drive / "Program Files (x86)" / "Steam", drive / "Windows.old" / "Program Files (x86)" / "Steam"):
    if not steam.is_dir():
        continue
    for u in (steam / "userdata").iterdir() if (steam / "userdata").is_dir() else []:
        shots = list((u / "760" / "remote").glob("*/screenshots")) if (u / "760").is_dir() else []
        nshots = sum(stats(s)[0] for s in shots)
        out.append(f"- **{steam.relative_to(drive)} userdata/{u.name}**: {line('all', u)[8:]}; screenshots: {nshots} files in {len(shots)} games")
    ws = steam / "steamapps" / "workshop" / "content"
    if ws.is_dir():
        out.append(f"- **Workshop items**: {sum(1 for a in ws.iterdir() for _ in a.iterdir())} in {sum(1 for _ in ws.iterdir())} games, "
                   f"{stats(ws)[1] / 1e9:.1f} GB (re-downloadable while subscribed)")

# 6. Portable tools: user settings.
out += ["", "## Portable tools: settings files", ""]
for p in [drive / "portable", drive / "PortableApps"] + [q / "TCUP" for q in (drive / "Users").iterdir() if q.is_dir()]:
    if p.is_dir():
        cfg = [os.path.join(r, f) for r, _, fs in os.walk(p) for f in fs
               if os.path.splitext(f)[1].lower() in (".ini", ".cfg", ".xml", ".json", ".txt") and os.path.getsize(os.path.join(r, f)) < 2e6]
        recent = sorted(cfg, key=os.path.getmtime, reverse=True)[:8]
        out.append(f"- **{p.relative_to(drive)}**: {len(cfg)} settings-like files; newest: "
                   + "; ".join(f"{os.path.relpath(c, p)} ({day(os.path.getmtime(c))})" for c in recent))

# 7. Profile: every top-level item and how much of it is in the copy.
out += ["", "## Profiles: top-level items not fully copied", ""]
for prof in (drive / "Users").iterdir():
    if not prof.is_dir() or prof.name.lower() in ("public", "default", "default user", "all users", "defaultuser0"):
        continue
    for p in sorted(prof.iterdir(), key=lambda p: p.name.lower()):
        if p.name.lower() in ("appdata",) or p.is_symlink():
            continue
        try:
            attrs = p.stat(follow_symlinks=False).st_file_attributes
        except OSError:
            continue
        if attrs & 0x400:
            continue
        n, size, types, newest = stats(p) if p.is_dir() else (1, p.stat().st_size, Counter(), p.stat().st_mtime)
        have = sum(1 for r, _, fs in os.walk(p) for f in fs if norm(os.path.join(r, f)) in covered) if p.is_dir() else int(norm(p) in covered)
        if n and have < n:
            out.append(f"- **{prof.name}/{p.name}**: {have}/{n} copied, {size / 1e6:.0f} MB, newest {day(newest) if newest else '-'}"
                       + (f"; {', '.join(f'{k} {v}' for k, v in types.most_common())}" if types else ""))

report.write_text("# Deep survey of " + str(drive) + "\n\n" + "\n".join(out) + "\n", encoding="utf-8")
print(f"wrote {report} ({len(out)} lines)")
