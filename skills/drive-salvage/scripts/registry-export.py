"""Export the registry part of a salvaged profile: game keys, and the whole Software branch.

Ludusavi can't read an old drive's registry, and some games keep settings or saves there
(Unity games' PlayerPrefs, for one). The profile copy holds the user's NTUSER.DAT; this
loads a temporary copy of it, never the original, exports, and unloads it. Run in an admin
shell (reg load needs it):

  python <skill>/scripts/registry-export.py D:/_backups/old-drives/<name>/personal/Users/<user>/NTUSER.DAT \
      --games D:/_backups/game-saves/<target>/games.json --out D:/_backups/game-saves/<target>/registry \
      --software D:/_backups/old-drives/<name>/registry-software.reg

- every HKEY_CURRENT_USER key the index lists for a game (registryKeys) goes to <out>/<game>.reg
- with --software, the whole HKEY_CURRENT_USER\\Software branch goes to one .reg file
- registry.json in <out> records which keys existed and were exported

HKEY_LOCAL_MACHINE keys live in the old Windows folder's SOFTWARE hive, not the profile, and
are reported as skipped. Standard library only; uses reg.exe.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def reg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["reg", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .")[:120]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hive", help="the copied NTUSER.DAT")
    p.add_argument("--games", help="the target's games.json, for the registry keys games use")
    p.add_argument("--out", required=True, help="folder for the per-game .reg files and registry.json")
    p.add_argument("--software", help="also export HKCU\\Software in full to this .reg file")
    a = p.parse_args()
    hive, out = Path(a.hive), Path(a.out)
    if not hive.is_file():
        sys.exit(f"no hive at {hive}")
    out.mkdir(parents=True, exist_ok=True)
    mount = f"HKU\\salvage_{int(time.time())}"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "NTUSER.DAT"
        shutil.copy2(hive, copy)  # loading writes hive logs; keep them off the archive's copy
        r = reg("load", mount, str(copy))
        if r.returncode:
            sys.exit(f"reg load failed (needs an admin shell): {r.stderr.strip() or r.stdout.strip()}")
        try:
            result = {"hive": str(hive), "when": time.strftime("%Y-%m-%d %H:%M:%S"), "games": {}, "skipped": []}
            games = (json.loads(Path(a.games).read_text(encoding="utf-8"))["games"] if a.games else {})
            for name, g in sorted(games.items()):
                for k in g.get("registryKeys", []):
                    path = k.replace("/", "\\")
                    if not path.upper().startswith("HKEY_CURRENT_USER\\"):
                        result["skipped"].append(f"{name}: {k} (not in the profile's hive)")
                        continue
                    sub = mount + path[len("HKEY_CURRENT_USER"):]
                    if reg("query", sub).returncode:
                        continue  # the game never wrote it on this profile
                    target = out / f"{safe(name)}.reg"
                    n = 1
                    while target.exists() and str(target) not in result["games"].get(name, []):
                        n += 1
                        target = out / f"{safe(name)} ({n}).reg"
                    er = reg("export", sub, str(target), "/y")
                    if er.returncode == 0:
                        result["games"].setdefault(name, []).append(str(target))
                        print(f"  {name}: {k}")
            if a.software:
                sw = Path(a.software)
                sw.parent.mkdir(parents=True, exist_ok=True)
                er = reg("export", mount + "\\Software", str(sw), "/y")
                result["software"] = str(sw) if er.returncode == 0 else f"failed: {er.stderr.strip()}"
                print(f"  HKCU\\Software: {result['software']}")
            (out / "registry.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{sum(len(v) for v in result['games'].values())} game keys exported for {len(result['games'])} games; "
                  f"{len(result['skipped'])} HKLM keys skipped\n{out / 'registry.json'}")
        finally:
            reg("unload", mount)


if __name__ == "__main__":
    main()
