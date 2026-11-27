"""Write the backup archive's front page: every salvaged drive, every game-save target, and one
list of all games across them. Reads only the result files the other two scripts write.

  python <skill>/scripts/overview.py            # $GAME_SAVES_HOME, its sibling old-drives/, README.md beside them

Writes <backups>/README.md and <backups>/games-overview.json. Rerun after any salvage step.
Standard library only.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saves", default=os.environ.get("GAME_SAVES_HOME"), help="the game-save archive")
    p.add_argument("--drives", help="the salvaged drives' folder (default: old-drives beside the save archive)")
    p.add_argument("--out", help="where README.md goes (default: the save archive's parent)")
    a = p.parse_args()
    if not a.saves:
        sys.exit("set GAME_SAVES_HOME or pass --saves")
    saves = Path(a.saves)
    drives = Path(a.drives) if a.drives else saves.parent / "old-drives"
    out = Path(a.out) if a.out else saves.parent

    lines = ["# Backups", "", f"Written {time.strftime('%Y-%m-%d %H:%M')} by drive-salvage's `overview.py`; "
             "rerun it after any salvage step.", ""]

    def link(p: Path) -> str:
        """A relative link from README.md, so the page keeps working if the folder moves."""
        rel = os.path.relpath(p, out).replace("\\", "/")
        return f"[`{rel}`](<{rel}>)"

    # --- map of every metadata file and folder, with what it's for
    lines += ["## Where everything is", ""]
    lines += ["- **This page**: `README.md`, and every game across all archives as data: "
              + link(out / "games-overview.json")]
    lines += [f"- **Game-save archive**: {link(saves)}",
              f"  - {link(saves / 'custom-games.json')} — games Ludusavi doesn't know, folders that aren't saves, "
              "and how games were acquired where the evidence was wrong. The one file edited by hand"]
    for t in sorted(x for x in saves.iterdir() if (x / "target.json").is_file()):
        lines.append(f"  - **{t.name}**")
        lines += [f"    - {link(t / n)} — {what}" for n, what in (
            ("games.md", "per game: when and how it was played"), ("games.json", "the same, as data"),
            ("verify.json", "the last hash check"), ("target.json", "what the target is"),
            ("backup", "Ludusavi's backups; each game's mapping.yaml lists its files and hashes"))
            if (t / n).exists()]
    lines.append(f"- **Salvaged drives**: {link(drives)}")
    for d in sorted(x for x in drives.iterdir() if x.is_dir()) if drives.is_dir() else []:
        lines.append(f"  - **{d.name}**")
        lines += [f"    - {link(d / n)} — {what}" for n, what in (
            ("salvage.md", "the report: start here"), ("decisions.md", "judgment calls, written by hand"),
            ("software.md", "what was installed"), ("manifest.json", "every copied file with its SHA-1"),
            ("copy.json", "copy and re-check results"), ("leftovers.json", "what was left on the drive"),
            ("deep-survey.md", "the closer look: installs, Recycle Bin, portable tools, partly copied items"),
            ("personal", "the copied files, at their original paths")) if (d / n).exists()]
    lines.append("")

    # --- salvaged drives
    lines += ["## Salvaged drives", "", "| **Drive** | **Source** | **Personal files** | **Software list** | **Report** |",
              "|---|---|---|---|---|"]
    for d in sorted(x for x in drives.iterdir() if x.is_dir()) if drives.is_dir() else []:
        copy = read_json(d / "copy.json") or {}
        check = copy.get("lastCheck")
        state = ("verified" if copy.get("verified") else "PROBLEMS") if copy else "-"
        if check:
            state += f", re-checked {check['when'][:10]}" + ("" if check["ok"] else " with PROBLEMS")
        files = f"{copy['files']} ({copy['bytes'] / 1e9:.2f} GB), {state}" if copy else "nothing copied, see decisions.md"
        source = f"`{copy['drive']}`" if copy else "-"
        lines.append(f"| **{d.name}** | {source} | {files} | "
                     f"{'`software.md`' if (d / 'software.md').exists() else '-'} | "
                     f"{'`salvage.md`' if (d / 'salvage.md').exists() else '-'} |")
    lines += ["", f"Folder: `{drives}`. Each drive's `salvage.md` says what the drive was, what was saved and "
              "checked, and what was left on purpose.", ""]

    # --- game-save targets
    lines += ["## Game-save targets", "", "| **Target** | **Root** | **Games** | **Last verified** |", "|---|---|---|---|"]
    merged: dict[str, dict] = {}
    for t in sorted(x for x in saves.iterdir() if (x / "target.json").is_file()):
        tj, v, g = read_json(t / "target.json"), read_json(t / "verify.json"), read_json(t / "games.json")
        games = (g or {}).get("games", {})
        ver = f"{v['when'][:10]}: {v['safe']}/{v['total']} safe" if v else "not yet"
        lines.append(f"| **{t.name}** | `{tj['scope']}` ({tj['kind']}) | {len(games) if g else 'not indexed'} | {ver} |")
        for name, e in games.items():
            m = merged.setdefault(name, {"name": name, "archives": {}, "acquired": set(), "steamHours": 0})
            m["archives"][t.name] = {"firstSave": e.get("firstSave"), "lastSave": e.get("lastSave"),
                                     "saveFiles": e.get("saveFiles", 0)}
            if e.get("acquired") and e["acquired"] != "unknown":
                m["acquired"].add(e["acquired"])
            for k in ("steam", "steamAccount"):
                if e.get(k, {}).get("playtimeHours"):
                    m["steamHours"] = max(m["steamHours"], e[k]["playtimeHours"])
    lines += ["", f"Folder: `{saves}`. Each target's `games.md` has the detail per game.", ""]

    # --- all games
    rows = []
    for m in merged.values():
        last = [(x["lastSave"], t) for t, x in m["archives"].items() if x["lastSave"]]
        newest = max(last) if last else (None, None)
        m["newestSave"], m["newestIn"] = newest
        m["acquired"] = sorted(m["acquired"]) or ["unknown"]
        rows.append(m)
    rows.sort(key=lambda m: (m["newestSave"] or "", m["name"].lower()), reverse=True)
    lines += [f"## All games ({len(rows)})", "", "Newest save first. The newest copy is the one to restore.", "",
              "| **Game** | **Newest save** | **Archives (last save)** | **Acquired** |", "|---|---|---|---|"]
    for m in rows:
        arch = ", ".join(f"{t} ({x['lastSave'] or '-'})" for t, x in sorted(m["archives"].items()))
        hours = f", {m['steamHours']} h on Steam" if m["steamHours"] else ""
        lines.append(f"| **{m['name']}** | {m['newestSave'] or '-'} in {m['newestIn'] or '-'} | {arch} | "
                     f"{'; '.join(m['acquired'])}{hours} |")
    out.mkdir(parents=True, exist_ok=True)
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (out / "games-overview.json").write_text(json.dumps({"games": rows}, indent=1, ensure_ascii=False, default=list)
                                             + "\n", encoding="utf-8", newline="\n")
    print(f"{out / 'README.md'}: {len(rows)} games across "
          f"{sum(1 for x in saves.iterdir() if (x / 'target.json').is_file())} targets")


if __name__ == "__main__":
    main()
