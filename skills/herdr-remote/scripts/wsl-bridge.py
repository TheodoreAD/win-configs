"""Install, check or remove the herdr-remote WSL bridge (/usr/local/bin/hc-via-b64).

Runs on the Windows host, in a normal (not admin) shell: it writes the file as WSL's root
with `wsl -u root`, which needs no Windows elevation. Standard library only.

  python -I wsl-bridge.py install    # copy assets/hc-via-b64 in (LF, mode 755), then test it
  python -I wsl-bridge.py check      # installed? same as the skill's copy? does it answer?
  python -I wsl-bridge.py remove     # delete it; nothing else in WSL is touched

All three take --distro (default Ubuntu-24.04). Safe to repeat: install skips an identical
file, remove skips a missing one. The test runs as the distro's default user, the way the
Linux controller reaches it. See references/wsl.md, step 1.
"""

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

BRIDGE_PATH = "/usr/local/bin/hc-via-b64"
ASSET = Path(__file__).resolve().parent.parent / "assets" / "hc-via-b64"
ENV = {**os.environ, "WSL_UTF8": "1"}  # wsl.exe prints UTF-16 otherwise


def wsl(distro: str, *args: str, root: bool = False, stdin: bytes | None = None) -> tuple[int, str]:
    cmd = ["wsl.exe", "-d", distro, *(["-u", "root"] if root else []), "-e", *args]
    r = subprocess.run(cmd, input=stdin, capture_output=True, env=ENV, timeout=120)
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace").replace("\x00", "").strip()
    return r.returncode, out


def distros() -> list[str]:
    r = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, env=ENV, timeout=60)
    text = r.stdout.decode("utf-8", errors="replace").replace("\x00", "")
    return [line.strip() for line in text.splitlines() if line.strip()]


def wanted() -> bytes:
    return ASSET.read_bytes().replace(b"\r\n", b"\n")  # sh breaks on CRLF


def installed(distro: str) -> bytes | None:
    r = subprocess.run(["wsl.exe", "-d", distro, "-u", "root", "-e", "sh", "-c",
                        f'[ -f {BRIDGE_PATH} ] && cat {BRIDGE_PATH} || exit 3'],
                       capture_output=True, env=ENV, timeout=120)
    return r.stdout if r.returncode == 0 else None


def answers(distro: str) -> tuple[bool, str]:
    """Run a line through the bridge as the default user, as Herdr would."""
    line = 'echo "bridge-ok user=$(id -un)" | cat'  # a quote and a pipe, which cmd.exe would mangle
    code, out = wsl(distro, BRIDGE_PATH, base64.b64encode(line.encode()).decode())
    return code == 0 and "bridge-ok" in out, out


def check(distro: str) -> int:
    current = installed(distro)
    if current is None:
        print(f"not installed: {BRIDGE_PATH} missing in {distro}")
        return 1
    same = current == wanted()
    ok, out = answers(distro)
    print(f"installed: {BRIDGE_PATH} in {distro}, "
          + ("same as the skill's copy" if same else "DIFFERS from the skill's copy (run install)"))
    print(f"test: {out or 'no output'}")
    return 0 if same and ok else 1


def install(distro: str) -> int:
    data = wanted()
    if installed(distro) == data:
        print(f"already installed and up to date in {distro}")
    else:
        # Write to a temp name and rename, so a half-written bridge is never on PATH.
        code, out = wsl(distro, "sh", "-c",
                        f"umask 022 && cat > {BRIDGE_PATH}.tmp && chmod 755 {BRIDGE_PATH}.tmp "
                        f"&& mv -f {BRIDGE_PATH}.tmp {BRIDGE_PATH}", root=True, stdin=data)
        if code != 0:
            print(f"install failed: {out or f'exit {code}'}", file=sys.stderr)
            return 1
        print(f"installed {BRIDGE_PATH} in {distro}")
    ok, out = answers(distro)
    print(f"test: {out or 'no output'}")
    return 0 if ok else 1


def remove(distro: str) -> int:
    if installed(distro) is None:
        print(f"nothing to remove: {BRIDGE_PATH} not in {distro}")
        return 0
    code, out = wsl(distro, "rm", "-f", BRIDGE_PATH, root=True)
    if code != 0:
        print(f"remove failed: {out or f'exit {code}'}", file=sys.stderr)
        return 1
    print(f"removed {BRIDGE_PATH} from {distro}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["install", "check", "remove"])
    p.add_argument("--distro", default="Ubuntu-24.04", help="WSL distro (default Ubuntu-24.04)")
    args = p.parse_args()
    if sys.platform != "win32":
        print("Run this on the Windows host; it reaches WSL through wsl.exe.", file=sys.stderr)
        return 2
    if args.distro not in distros():
        print(f"WSL distro {args.distro!r} not found; have: {', '.join(distros()) or 'none'}", file=sys.stderr)
        return 2
    return {"install": install, "check": check, "remove": remove}[args.action](args.distro)


if __name__ == "__main__":
    sys.exit(main())
