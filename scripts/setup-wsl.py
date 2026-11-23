"""Install Ubuntu in WSL as the default distro, with a generic sudo user as the default login.

Windows-side setup only; everything else inside the distro (systemd, Docker, packages) is done
by the separate Linux setup repo. Safe to run again: each step checks first and skips what's
already done.

Steps:
  1. Install the distro if it isn't registered (`wsl --install -d <distro> --no-launch`,
     optionally with --vhd-size), and make it the default distro.
  2. Create the user (default `dev`) in the sudo group, with no usable password.
  3. Allow passwordless sudo for it (/etc/sudoers.d/<user>, validated with visudo).
     A sudo password inside WSL isn't a security boundary: anything running as you on Windows
     can get root with `wsl -u root` without one.
  4. Make it the default login via the distro's DefaultUid in the Windows registry, so
     /etc/wsl.conf is left to the Linux setup, and skip the distro's interactive first-run
     setup (RunOOBE=0), which would otherwise prompt for a user and edit /etc/wsl.conf.
  5. Restart the distro and verify: default user, passwordless sudo, default distro, no
     pending first-run setup.

Usage, from the repo root in a normal (not admin) PowerShell:
  uv run python scripts/setup-wsl.py                 # install / repair, then verify
  uv run python scripts/setup-wsl.py --check         # verify only, change nothing
  uv run python scripts/setup-wsl.py --vhd-size 512GB

Needs WSL itself (`wsl --install --no-distribution` as admin, then reboot, on a fresh machine).
"""

import argparse
import os
import re
import subprocess
import sys
import winreg

LXSS = r"Software\Microsoft\Windows\CurrentVersion\Lxss"
ENV = {**os.environ, "WSL_UTF8": "1"}  # wsl.exe prints UTF-16 otherwise


def wsl(*args, input=None, check=True):
    r = subprocess.run(["wsl.exe", *args], capture_output=True, input=input, env=ENV,
                       encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise SystemExit(f"wsl {' '.join(args)} failed ({r.returncode}):\n{r.stdout}{r.stderr}")
    return r


def in_distro(distro, script, *args, user="root", input=None, check=True):
    """Run a POSIX sh script inside the distro, passing args as $1.. (no Windows-side quoting)."""
    return wsl("-d", distro, "-u", user, "--exec", "sh", "-c", script, "sh", *args,
               input=input, check=check)


def registered():
    r = wsl("--list", "--quiet", check=False)
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def lxss_key(distro):
    """Return (key path, values) for the distro's registry entry, or (None, None)."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LXSS) as root:
        default_guid = _value(root, "DefaultDistribution")
        for i in range(winreg.QueryInfoKey(root)[0]):
            guid = winreg.EnumKey(root, i)
            with winreg.OpenKey(root, guid) as k:
                if _value(k, "DistributionName") == distro:
                    return f"{LXSS}\\{guid}", {"DefaultUid": _value(k, "DefaultUid"),
                                               "RunOOBE": _value(k, "RunOOBE"),
                                               "is_default": guid == default_guid}
    return None, None


def _value(key, name):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def step(msg):
    print(f"- {msg}", flush=True)


def setup(a):
    if a.distro not in registered():
        step(f"installing {a.distro} (download can take a few minutes)")
        extra = ["--vhd-size", a.vhd_size] if a.vhd_size else []
        wsl("--install", "-d", a.distro, "--no-launch", *extra)
        if a.distro not in registered():
            raise SystemExit(f"{a.distro} isn't registered after install; launch it once with "
                             f"`wsl -d {a.distro}`, then run this script again")
    else:
        step(f"{a.distro} already installed")

    key, info = lxss_key(a.distro)
    if not info["is_default"]:
        step(f"making {a.distro} the default distro")
        wsl("--set-default", a.distro)

    if in_distro(a.distro, 'id -u "$1" >/dev/null 2>&1', a.user, check=False).returncode:
        step(f"creating user {a.user}")
        in_distro(a.distro, 'useradd --create-home --shell /bin/bash --groups sudo "$1"', a.user)
    else:
        step(f"user {a.user} exists")
        in_distro(a.distro, 'usermod --append --groups sudo "$1"', a.user)

    step("passwordless sudo")
    in_distro(a.distro, 'f=/etc/sudoers.d/"$1"; cat > "$f.tmp" && visudo -cqf "$f.tmp" '
              '&& chmod 0440 "$f.tmp" && mv "$f.tmp" "$f"',
              a.user, input=f"{a.user} ALL=(ALL) NOPASSWD:ALL\n")

    uid = int(in_distro(a.distro, 'id -u "$1"', a.user).stdout.strip())
    changed = False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        if info["DefaultUid"] != uid:
            step(f"default login -> {a.user} (uid {uid})")
            winreg.SetValueEx(k, "DefaultUid", 0, winreg.REG_DWORD, uid)
            changed = True
        else:
            step(f"default login already {a.user}")
        # Skip the distro's first-run setup (Ubuntu's /usr/lib/wsl/wsl-setup): the user it would
        # prompt for already exists, and it would also append [user] default=... to
        # /etc/wsl.conf and register the Ubuntu font in Windows. WSL clears this flag itself
        # after the first interactive launch; clearing it here makes that launch a plain login.
        if info["RunOOBE"]:
            step("skipping the distro's first-run setup (RunOOBE -> 0)")
            winreg.SetValueEx(k, "RunOOBE", 0, winreg.REG_DWORD, 0)
            changed = True
    if changed:
        wsl("--terminate", a.distro)


def verify(a):
    problems = []
    if a.distro not in registered():
        return [f"{a.distro} isn't installed"]
    _, info = lxss_key(a.distro)
    if not info["is_default"]:
        problems.append(f"{a.distro} isn't the default distro")
    if info["RunOOBE"]:
        problems.append("the distro's first-run setup is still pending (RunOOBE=1)")
    r = wsl("-d", a.distro, "--exec", "sh", "-c",
            'echo "$(id -un) $(id -Gn | tr " " ",")"; sudo -n true && echo sudo-ok', check=False)
    lines = r.stdout.split()
    if not lines or lines[0] != a.user:
        problems.append(f"default login is {lines[0] if lines else '?'}, not {a.user}")
    if "sudo" not in (lines[1].split(",") if len(lines) > 1 else []):
        problems.append(f"{a.user} isn't in the sudo group")
    if "sudo-ok" not in lines:
        problems.append("passwordless sudo doesn't work")
    print(f"{a.distro}: default distro={info['is_default']}, login={lines[0] if lines else '?'}, "
          f"groups={lines[1] if len(lines) > 1 else '?'}, passwordless sudo={'sudo-ok' in lines}")
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--distro", default="Ubuntu-24.04")
    p.add_argument("--user", default="dev")
    p.add_argument("--vhd-size", help="cap the virtual disk on first install, e.g. 512GB")
    p.add_argument("--check", action="store_true", help="only verify, change nothing")
    a = p.parse_args()
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", a.user):
        raise SystemExit("user must be a lowercase Linux name (a-z, 0-9, _ or -, starting with a letter)")
    if wsl("--status", check=False).returncode:
        raise SystemExit("WSL isn't installed: run `wsl --install --no-distribution` as admin, reboot")
    if not a.check:
        setup(a)
    problems = verify(a)
    for problem in problems:
        print(f"PROBLEM: {problem}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
