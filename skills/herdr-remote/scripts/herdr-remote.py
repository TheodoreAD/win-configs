#!/usr/bin/env python3
"""Doctor and status checks for a Herdr remote setup.

The setup (see ../SKILL.md): a Linux machine runs the Herdr desktop app and reaches a
Windows machine over SSH as one Herdr machine, and that Windows machine's WSL distro as
another (ssh -> wsl.exe -> a small bridge script).

Run the same script on either machine; it detects the OS:

    herdr-remote.py doctor          every check, with a fix hint for each problem
    herdr-remote.py status          quick live view (connections, machines, versions)
    herdr-remote.py key-line KEY.pub --from 192.168.1.10
                                    print the restricted authorized_keys line for Windows

Read-only: it never changes configuration. On Windows, `doctor` starts the WSL distro to
look inside it (skip with --no-wsl). Some Windows checks need an elevated shell; without
one they are reported as skipped, not failed. Exit code 1 if any check failed.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

OK, WARN, FAIL, INFO, SKIP = "ok", "warn", "fail", "info", "skip"
LABELS = {OK: "  OK ", WARN: " WARN", FAIL: " FAIL", INFO: " info", SKIP: " skip"}

DEFAULT_HOST = "winbox"
DEFAULT_DISTRO = "Ubuntu-24.04"
DEFAULT_WSL_MACHINE = "winbox-wsl"
BRIDGE_PATH = "/usr/local/bin/hc-via-b64"
DEFAULT_WRAPPER = "~/.local/bin/herdr-via-wsl"
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-", "sk-ssh-ed25519", "sk-ecdsa-sha2-")
RESTRICTIONS = ("no-port-forwarding", "no-agent-forwarding", "no-x11-forwarding", "no-pty")

WIN_SSH_DIR = Path(r"C:\ProgramData\ssh")
WIN_ADMIN_KEYS = WIN_SSH_DIR / "administrators_authorized_keys"
SID_ADMINS, SID_SYSTEM = "S-1-5-32-544", "S-1-5-18"


# ----------------------------------------------------------------------------- report


@dataclass
class Check:
    status: str
    name: str
    detail: str = ""
    fix: str = ""


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, status: str, name: str, detail: str = "", fix: str = "") -> None:
        self.checks.append(Check(status, name, detail, fix))

    def failed(self) -> bool:
        return any(c.status == FAIL for c in self.checks)

    def print(self, as_json: bool) -> None:
        if as_json:
            print(json.dumps([asdict(c) for c in self.checks], indent=2))
            return
        for c in self.checks:
            line = f"[{LABELS[c.status]}] {c.name}"
            if c.detail:
                line += f" — {c.detail}"
            print(line)
            if c.fix and c.status in (WARN, FAIL):
                for fix_line in c.fix.splitlines():
                    print(f"         fix: {fix_line}")
        counts = {s: sum(c.status == s for c in self.checks) for s in (OK, WARN, FAIL, SKIP)}
        print(f"\n{counts[OK]} ok, {counts[WARN]} warnings, {counts[FAIL]} failed, {counts[SKIP]} skipped")


# ----------------------------------------------------------------------------- helpers


def run(cmd: list[str], timeout: int = 20, env: dict | None = None) -> tuple[int, str, str]:
    """Run a command without a shell; never lets it read our stdin."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, stdin=subprocess.DEVNULL, env=env,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"


def version_of(text: str) -> str | None:
    m = re.search(r"\d+\.\d+\.\d+", text)
    return m.group(0) if m else None


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_key_line(line: str) -> dict | None:
    """Split an authorized_keys line into options, key type and comment."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # Options come first and may contain quoted spaces; the key type is the first
    # unquoted token that starts with a known type.
    in_quote, start, tokens = False, 0, []
    for i, ch in enumerate(line + " "):
        if ch == '"':
            in_quote = not in_quote
        elif ch == " " and not in_quote:
            if i > start:
                tokens.append((start, line[start:i]))
            start = i + 1
    for idx, (pos, tok) in enumerate(tokens):
        if tok.startswith(KEY_TYPES):
            options = line[:pos].strip()
            comment = " ".join(t for _, t in tokens[idx + 2:])
            from_ips = re.findall(r'from="([^"]*)"', options)
            return {
                "options": options.lower(),
                "type": tok,
                "comment": comment,
                "from": [ip for group in from_ips for ip in group.split(",") if ip],
            }
    return None


def key_restriction_issues(key: dict) -> list[str]:
    issues = [r for r in RESTRICTIONS if r not in key["options"]]
    if not key["from"]:
        issues.insert(0, 'from="<controller IP>"')
    return issues


# ----------------------------------------------------------------------------- Windows


def ps_json(script: str, timeout: int = 60):
    """Run a PowerShell snippet and parse its output as JSON (None if empty)."""
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        raise RuntimeError("no PowerShell found")
    code, out, err = run(
        [exe, "-NoProfile", "-NonInteractive", "-Command",
         # exit 0: an empty, quietly-failed lookup (-ErrorAction SilentlyContinue) is "no results",
         # while a real error still throws (ErrorActionPreference Stop) and exits 1 first.
         f"$ErrorActionPreference='Stop'; {script} | ConvertTo-Json -Depth 4 -Compress; exit 0"],
        timeout,
    )
    if code:
        raise RuntimeError((err or out).splitlines()[0] if (err or out) else f"exit {code}")
    return json.loads(out) if out else None


def win_elevated() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def win_admin_member() -> bool:
    # whoami lists Administrators even when UAC makes it "deny only" in this shell.
    code, out, _ = run(["whoami", "/groups", "/fo", "csv"])
    return code == 0 and SID_ADMINS in out


def win_user_path_dirs() -> list[str]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, "Path")
        return [os.path.expandvars(p).rstrip("\\").lower() for p in value.split(";") if p]
    except OSError:
        return []


def parse_sshd_config(text: str) -> tuple[dict, list[dict]]:
    """Global options (first value wins, like sshd) and Match blocks."""
    global_opts: dict[str, str] = {}
    allow_users: list[str] = []
    blocks: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        key, value = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")
        if key == "match":
            current = {"match": value, "opts": {}}
            blocks.append(current)
            continue
        if current is None and key == "allowusers":
            allow_users.extend(value.split())
            continue
        target = current["opts"] if current else global_opts
        target.setdefault(key, value)
    global_opts["allowusers"] = " ".join(allow_users)
    return global_opts, blocks


def netsh_inbound_rules() -> list[dict]:
    """All inbound firewall rules via netsh (works without elevation, unlike Get-NetFirewallPortFilter)."""
    code, out, _ = run(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in", "verbose"], 60)
    if code:
        return []
    rules, cur = [], None
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = (s.strip() for s in line.split(":", 1))
        if k == "Rule Name":
            cur = {"name": v}
            rules.append(cur)
        elif cur is not None:
            cur[k.lower()] = v
    return rules


def rule_covers_ssh(rule: dict) -> bool:
    if rule.get("enabled") != "Yes" or rule.get("action") != "Allow":
        return False
    program = rule.get("program", "").lower()
    if program.endswith("sshd.exe"):
        return True
    if rule.get("protocol") not in ("TCP", "Any"):
        return False
    for part in rule.get("localport", "").split(","):
        part = part.strip()
        if part == "22":
            return True
        if "-" in part:
            lo, _, hi = part.partition("-")
            if lo.isdigit() and hi.isdigit() and int(lo) <= 22 <= int(hi):
                return True
    return False


def windows_doctor(r: Report, args) -> None:
    user = os.environ.get("USERNAME", "")
    elevated, admin_member = win_elevated(), win_admin_member()
    r.add(INFO, "Account",
          f"{user}; Administrators member: {'yes' if admin_member else 'no'}; "
          f"this shell elevated: {'yes' if elevated else 'no'}")
    if not elevated:
        r.add(INFO, "Not elevated",
              "the key file's contents can only be checked from an elevated shell; "
              "rerun as Administrator for the full picture")

    # --- OpenSSH server
    try:
        svc = ps_json("Get-Service | Where-Object Name -eq 'sshd' | "
                      "Select-Object @{n='Status';e={\"$($_.Status)\"}},@{n='StartType';e={\"$($_.StartType)\"}}")
    except RuntimeError as e:
        svc = None
        r.add(SKIP, "OpenSSH server service", str(e))
    if svc is None:
        r.add(FAIL, "OpenSSH server installed", "no sshd service",
              "admin pwsh: Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 "
              "(references/windows-host.md, step 2)")
    else:
        status_ok = svc["Status"] == "Running"
        r.add(OK if status_ok else FAIL, "sshd running", svc["Status"],
              "admin pwsh: Start-Service sshd")
        r.add(OK if svc["StartType"] == "Automatic" else WARN, "sshd starts automatically", svc["StartType"],
              "admin pwsh: Set-Service sshd -StartupType Automatic")
        try:
            listen = as_list(ps_json("Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue "
                                     "| Select-Object -ExpandProperty LocalAddress"))
        except RuntimeError:
            listen = []
        r.add(OK if listen else FAIL, "Port 22 listening", ", ".join(listen) or "nothing listens",
              "start sshd; if it won't start, check the OpenSSH/Operational event log")

    # --- sshd_config
    config_path = WIN_SSH_DIR / "sshd_config"
    admin_block = None
    try:
        glob, blocks = parse_sshd_config(config_path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        glob, blocks = None, []
        if svc is not None:
            r.add(WARN, "sshd_config", f"{config_path} missing (sshd creates it on first start)")
    except PermissionError:
        glob, blocks = None, []
        r.add(SKIP, "sshd_config", "not readable from this shell")
    if glob is not None:
        pw = glob.get("passwordauthentication", "yes").lower()
        r.add(OK if pw == "no" else FAIL, "Password logins off", f"PasswordAuthentication {pw}",
              "set `PasswordAuthentication no` above the Match block in sshd_config, then Restart-Service sshd")
        allowed = glob.get("allowusers", "").split()
        names = {a.split("@")[0] for a in allowed}
        if not allowed:
            r.add(WARN, "AllowUsers", "not set: any local account with a key can log in",
                  f"add `AllowUsers {user.lower()}` above the Match block")
        elif user.lower() in names:
            r.add(OK, "AllowUsers", " ".join(allowed))
        elif user.lower() in {n.lower() for n in names}:
            r.add(FAIL, "AllowUsers", f"{' '.join(allowed)} (Windows OpenSSH needs it lowercase)",
                  f"write `AllowUsers {user.lower()}`")
        else:
            r.add(FAIL, "AllowUsers", f"{' '.join(allowed)} doesn't include {user.lower()}",
                  f"add {user.lower()} to AllowUsers")
        if glob.get("disableforwarding", "no").lower() == "yes":
            r.add(OK, "Forwarding off", "DisableForwarding yes")
        else:
            for opt, name in (("allowtcpforwarding", "TCP forwarding off"),
                              ("allowagentforwarding", "Agent forwarding off")):
                val = glob.get(opt, "yes").lower()
                r.add(OK if val == "no" else WARN, name, f"{opt} {val}",
                      "set `DisableForwarding yes` above the Match block (the key restriction covers it too)")
        admin_block = next((b for b in blocks if "administrators" in b["match"].lower()
                            and "authorizedkeysfile" in b["opts"]), None)
        if admin_member:
            r.add(OK if admin_block else WARN, "Admin key file in use",
                  "Match Group administrators -> administrators_authorized_keys" if admin_block
                  else "no Match Group administrators block: keys are read from ~/.ssh/authorized_keys")

    # --- authorized key file
    key_ips: list[str] = []
    if admin_member and (admin_block or glob is None):
        key_file, allowed_sids = WIN_ADMIN_KEYS, {SID_ADMINS, SID_SYSTEM}
    else:
        key_file = Path.home() / ".ssh" / "authorized_keys"
        allowed_sids = {SID_ADMINS, SID_SYSTEM}
        code, out, _ = run(["whoami", "/user", "/fo", "csv", "/nh"])
        if code == 0 and out:
            allowed_sids.add(out.split(",")[-1].strip('"'))
    if not key_file.exists():
        r.add(FAIL, "Authorized key installed", f"{key_file} missing",
              "references/windows-host.md, step 5")
    else:
        try:
            text = key_file.read_text(encoding="utf-8-sig", errors="replace")
        except PermissionError:
            text = None
        if text is None:
            r.add(OK, "Key file locked down", f"{key_file.name} not readable from an unelevated shell "
                  "(expected); run elevated to inspect the keys")
        elif key_file == WIN_ADMIN_KEYS and not elevated:
            r.add(FAIL, "Key file locked down", "readable without elevation: sshd ignores the file",
                  f'admin pwsh: icacls.exe {key_file} /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"')
            text = None
        if text is not None:
            keys = [k for k in (parse_key_line(l) for l in text.splitlines()) if k]
            r.add(OK if keys else FAIL, "Authorized keys", f"{len(keys)} key(s) in {key_file.name}",
                  "references/windows-host.md, step 5")
            for k in keys:
                issues = key_restriction_issues(k)
                label = f"Key '{k['comment'] or k['type']}'"
                r.add(OK if not issues else WARN, label,
                      f"from={','.join(k['from']) or 'any'}; " + ("restricted" if not issues else
                                                                    "missing: " + ", ".join(issues)),
                      "regenerate the line with `herdr-remote.py key-line` on Linux and replace it")
                key_ips.extend(k["from"])
        try:
            sids = as_list(ps_json(
                f"(Get-Acl -LiteralPath '{key_file}').Access | Where-Object AccessControlType -eq 'Allow' | "
                "ForEach-Object { try { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } "
                "catch { \"$($_.IdentityReference)\" } }"))
            extra = sorted(set(sids) - allowed_sids)
            r.add(OK if not extra else FAIL, "Key file permissions",
                  "only Administrators/SYSTEM" + (" and you" if key_file != WIN_ADMIN_KEYS else "")
                  if not extra else f"also granted to {', '.join(extra)}: sshd ignores the file",
                  f'admin pwsh: icacls.exe {key_file} /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"')
        except RuntimeError:
            if text is not None or elevated:
                r.add(SKIP, "Key file permissions", "couldn't read the ACL")

    # --- firewall
    rules = [x for x in netsh_inbound_rules() if rule_covers_ssh(x)]
    if not rules:
        r.add(FAIL if svc else INFO, "Firewall allows SSH", "no enabled inbound allow rule for port 22",
              "admin pwsh: New-NetFirewallRule -Name OpenSSH-Server-In-TCP -DisplayName 'OpenSSH Server (sshd)' "
              "-Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -Profile Any -RemoteAddress <controller IP>")
    try:
        lan_profiles = {p for p in as_list(ps_json(
            "Get-NetConnectionProfile | Where-Object { $_.InterfaceAlias -notmatch 'vEthernet|VPN|Nord|Tailscale|ZeroTier' } "
            "| ForEach-Object { \"$($_.NetworkCategory)\" }")) if p}
    except RuntimeError:
        lan_profiles = set()
    fw_ips: list[str] = []
    for rule in rules:
        remote = rule.get("remoteip", "Any")
        profiles = rule.get("profiles", "?")
        if remote in ("Any", ""):
            r.add(FAIL, f"Firewall rule '{rule['name']}'", f"open to any address ({profiles})",
                  f"admin pwsh: Set-NetFirewallRule -DisplayName '{rule['name']}' -RemoteAddress <controller IP>")
            continue
        # netsh prints single addresses as "a.b.c.d/32" or as a range "a.b.c.d-a.b.c.d"
        addrs = []
        for part in remote.split(","):
            part = part.strip().split("/")[0]
            lo, _, hi = part.partition("-")
            addrs.append(lo if not hi or hi == lo else part)
        r.add(OK, f"Firewall rule '{rule['name']}'", f"only from {', '.join(addrs)} ({profiles})")
        fw_ips.extend(addrs)
        # DomainAuthenticated maps to the Domain profile
        covered = {"Domain" if p == "DomainAuthenticated" else p for p in lan_profiles}
        if profiles not in ("Any", "?") and not covered <= set(profiles.split(",")):
            r.add(WARN, f"Rule '{rule['name']}' covers the LAN profile",
                  f"LAN is {', '.join(sorted(lan_profiles))}, rule applies to {profiles}: it won't match",
                  f"admin pwsh: Set-NetFirewallRule -DisplayName '{rule['name']}' -Profile Any")
    if key_ips and fw_ips and set(key_ips) != set(fw_ips):
        r.add(WARN, "Firewall and key agree", f"firewall {','.join(fw_ips)} vs key from= {','.join(key_ips)}",
              "both should name the Linux controller's (reserved) LAN IP")

    # --- addresses and host key, for the Linux side's ~/.ssh/config and first connect
    try:
        addrs = as_list(ps_json("Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -in 'Dhcp','Manual' } "
                                "| ForEach-Object { \"$($_.IPAddress) ($($_.InterfaceAlias), $($_.PrefixOrigin))\" }"))
        r.add(INFO, "This machine's IPv4", "; ".join(addrs) or "none",)
    except RuntimeError:
        pass
    # The host key files are admin-only; asking the running sshd over loopback works unelevated.
    fingerprints = []
    if svc is not None:
        code, out, _ = run(["ssh-keyscan", "-t", "ed25519", "127.0.0.1"], 15)
        if code == 0 and out:
            import tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".pub", delete=False) as tmp:
                tmp.write(out + "\n")
            code, fp, _ = run(["ssh-keygen", "-lf", tmp.name])
            os.unlink(tmp.name)
            if code == 0:
                fingerprints.append(fp)
                r.add(INFO, "Host key", fp.replace("127.0.0.1 ", "") + "  (compare on the first `ssh` from Linux)")
    try:
        lan_ips = as_list(ps_json(
            "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -in 'Dhcp','Manual' -and "
            "$_.InterfaceAlias -notmatch 'vEthernet|VPN|Nord|Tailscale|ZeroTier|Loopback' } "
            "| ForEach-Object { $_.IPAddress }"))
    except RuntimeError:
        lan_ips = []
    ed25519 = next((f.split()[1] for f in fingerprints if "ED25519" in f), None)
    r.add(INFO, "For the Linux side",
          f"HostName {' or '.join(lan_ips) or '<this PC LAN IP>'}, User {user}"
          + (f", host key {ed25519}" if ed25519 else ", host key: start sshd first")
          + "  (Claude on Linux asks for these; read them off here)")

    # --- Herdr core
    hc = shutil.which("hc")
    if not hc:
        r.add(FAIL, "hc on PATH", "not found", "install the Herdr desktop app (it installs herdr-core)")
    else:
        code, out, _ = run([hc, "--version"])
        r.add(OK, "hc on PATH", f"{out} ({hc})")
        hc_dir = str(Path(hc).parent).rstrip("\\").lower()
        if hc_dir not in win_user_path_dirs():
            r.add(WARN, "hc on the user PATH", f"{Path(hc).parent} not in the registry user PATH; "
                  "SSH sessions may not find hc", "add it to the user PATH (System > Environment Variables)")
        code, out, err = run([hc, "server", "status", "--json"])
        try:
            st = json.loads(out)
            r.add(OK, "Herdr core running", f"{st.get('version')} pid {st.get('pid')}, {st.get('live')} live terminal(s)")
        except (ValueError, TypeError):
            r.add(WARN, "Herdr core running", err or out or "no answer",
                  "start the Herdr app (or `hc server start`) so remote spaces have a core to attach to")

    # --- WSL
    if not args.no_wsl:
        windows_wsl_checks(r, args.distro)


def windows_wsl_checks(r: Report, distro: str) -> None:
    env = dict(os.environ, WSL_UTF8="1")
    code, out, err = run(["wsl.exe", "-l", "-q"], env=env)
    distros = [d.strip().strip("\x00") for d in out.splitlines() if d.strip()]
    if code or distro not in distros:
        r.add(FAIL, f"WSL distro {distro}", f"not found (have: {', '.join(distros) or 'none'})",
              "pass --distro with the right name, or install it")
        return
    r.add(OK, f"WSL distro {distro}", "installed")
    probe = ("echo user=$(id -un); PATH=$HOME/.local/bin:$PATH; "
             f"if [ -x {BRIDGE_PATH} ]; then echo bridge=yes; else echo bridge=no; fi; "
             "if command -v hc >/dev/null 2>&1; then echo hc=$(hc --version); else echo hc=none; fi")
    code, out, err = run(["wsl.exe", "-d", distro, "-e", "sh", "-c", probe], 60, env=env)
    facts = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    wsl_user = facts.get("user", "?")
    r.add(OK if wsl_user not in ("root", "?") else WARN, "WSL default user", wsl_user,
          "Herdr terminals in WSL would run as root: create a normal user and make it the default "
          "(references/wsl.md, step 0)")
    if facts.get("bridge") == "yes":
        b64 = base64.b64encode(b"echo bridge-ok").decode()
        c2, o2, e2 = run(["wsl.exe", "-d", distro, "-e", BRIDGE_PATH, b64], 30, env=env)
        r.add(OK if "bridge-ok" in o2 else FAIL, "WSL bridge works", o2 or e2,
              f"reinstall it: references/wsl.md, step 1")
    else:
        r.add(FAIL, "WSL bridge installed", f"{BRIDGE_PATH} missing" if code == 0 else (err or "wsl.exe failed"),
              "references/wsl.md, step 1")
    hc_ver = facts.get("hc", "none")
    r.add(OK if hc_ver != "none" else WARN, "hc inside WSL", hc_ver,
          "the Linux controller installs it on `hc machine add ... --name winbox-wsl` (answer yes)")


def windows_status(r: Report, args) -> None:
    try:
        svc = ps_json("Get-Service | Where-Object Name -eq 'sshd' | Select-Object @{n='Status';e={\"$($_.Status)\"}}")
        r.add(OK if svc and svc["Status"] == "Running" else FAIL, "sshd", svc["Status"] if svc else "not installed")
        conns = as_list(ps_json("Get-NetTCPConnection -LocalPort 22 -State Established -ErrorAction SilentlyContinue "
                                "| Select-Object -ExpandProperty RemoteAddress"))
        r.add(INFO, "SSH connections now", ", ".join(sorted(set(conns))) or "none")
    except RuntimeError as e:
        r.add(SKIP, "sshd", str(e))
    hc = shutil.which("hc")
    if hc:
        code, out, err = run([hc, "server", "status", "--json"])
        try:
            st = json.loads(out)
            r.add(OK, "Herdr core", f"{st.get('version')}, {st.get('live')} live terminal(s), up "
                  f"{int(st.get('uptime_ms', 0)) // 3_600_000} h")
        except (ValueError, TypeError):
            r.add(WARN, "Herdr core", err or "not running")
    env = dict(os.environ, WSL_UTF8="1")
    code, out, _ = run(["wsl.exe", "-l", "-v"], env=env)  # doesn't start the distro
    line = next((l for l in out.splitlines() if args.distro in l), "")
    r.add(INFO, f"WSL {args.distro}", " ".join(line.replace("*", "").split()[1:2]) or "not found")


# ----------------------------------------------------------------------------- Linux


def ssh_settings(host: str) -> dict[str, list[str]]:
    code, out, _ = run(["ssh", "-G", host])
    settings: dict[str, list[str]] = {}
    if code == 0:
        for line in out.splitlines():
            k, _, v = line.partition(" ")
            settings.setdefault(k.lower(), []).append(v)
    return settings


def ssh_batch(host: str, remote: list[str], extra: list[str] | None = None, timeout: int = 30):
    return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", *(extra or []), host, *remote], timeout)


def explain_ssh_error(err: str) -> str:
    e = err.lower()
    if "permission denied" in e:
        return ("key refused: not installed on Windows yet (linux-controller.md, step 4), or "
                "from=/AllowUsers don't match this machine's IP (run doctor on Windows)")
    if "host key verification failed" in e:
        return "first connect interactively (`ssh winbox hc --version`) and compare the host key with Windows doctor"
    if "timed out" in e or "no route" in e or "refused" in e:
        return "Windows asleep, sshd stopped, IP changed or firewall RemoteAddress wrong"
    if "not recognized" in e:
        return "hc not on the Windows user PATH for SSH sessions (run doctor on Windows)"
    return "see references/troubleshooting.md"


def linux_hc_machines() -> list[dict] | None:
    code, out, _ = run(["hc", "machine", "ls", "--json"])
    if code:
        return None
    try:
        return json.loads(out).get("machines", [])
    except (ValueError, AttributeError):
        return None


def machine_name(m: dict) -> str:
    return str(m.get("name") or m.get("id") or "?")


def linux_doctor(r: Report, args) -> None:
    host, distro = args.host, args.distro
    hc = shutil.which("hc")
    local_ver = None
    if hc:
        code, out, _ = run([hc, "--version"])
        local_ver = version_of(out)
        r.add(OK, "hc on PATH", f"{out} ({hc})")
    else:
        r.add(FAIL, "hc on PATH", "not found", "install the Herdr desktop app (references/linux-controller.md, step 1)")

    code, out, _ = run(["ip", "-4", "route", "get", "1.1.1.1"])
    m = re.search(r"\bsrc (\S+)", out)
    if m:
        r.add(INFO, "This machine's LAN IP", f"{m.group(1)}  (the --from value for key-line; reserve it on the router)")

    s = ssh_settings(host)
    hostname = (s.get("hostname") or [host])[0]
    if not s or hostname == host:
        default_key = Path.home() / ".ssh" / "id_ed25519_winbox"
        if not default_key.exists():
            r.add(FAIL, "Key file", f"{default_key} missing", "references/linux-controller.md, step 2")
        r.add(FAIL, f"~/.ssh/config Host {host}", "no entry with a HostName",
              "references/linux-controller.md, step 3 (needs the Windows IP and account name "
              "from the Windows doctor's 'For the Linux side' line)")
        return
    user = (s.get("user") or ["?"])[0]
    port = int((s.get("port") or ["22"])[0])
    r.add(OK, f"~/.ssh/config Host {host}", f"{user}@{hostname}:{port}")
    fwd = (s.get("forwardagent") or ["no"])[0]
    r.add(OK if fwd == "no" else FAIL, "ForwardAgent off", fwd,
          f"set `ForwardAgent no` in Host {host}: never hand Windows your agent")
    r.add(OK if (s.get("identitiesonly") or ["no"])[0] == "yes" else WARN, "IdentitiesOnly",
          (s.get("identitiesonly") or ["no"])[0], f"set `IdentitiesOnly yes` in Host {host}")

    keys = [Path(os.path.expanduser(p)) for p in s.get("identityfile", [])]
    key = next((k for k in keys if k.exists()), None)
    if not key:
        r.add(FAIL, "Key file", f"none of {', '.join(map(str, keys)) or 'no IdentityFile'} exists",
              "references/linux-controller.md, step 2")
    else:
        mode = stat.S_IMODE(key.stat().st_mode)
        r.add(OK if mode & 0o077 == 0 else FAIL, "Key file", f"{key} ({oct(mode)})", f"chmod 600 {key}")
        code, _, _ = run(["ssh-keygen", "-y", "-P", "", "-f", str(key)])
        if code == 0:
            r.add(WARN, "Key passphrase", "none: anyone who can read the file gets into Windows",
                  f"ssh-keygen -p -f {key}, then keep it in your desktop's ssh-agent")
        else:
            code, out, _ = run(["ssh-add", "-l"])
            code_fp, fp, _ = run(["ssh-keygen", "-lf", str(key)])
            fp_hash = fp.split()[1] if code_fp == 0 and len(fp.split()) > 1 else ""
            loaded = bool(fp_hash) and fp_hash in out
            r.add(OK if loaded else WARN, "Key in ssh-agent", "loaded" if loaded else "not loaded",
                  f"ssh-add {key}  (Herdr connects in the background and can't ask for the passphrase)")

    try:
        with socket.create_connection((hostname, port), timeout=4):
            r.add(OK, "Windows reachable", f"{hostname}:{port}")
    except OSError as e:
        r.add(FAIL, "Windows reachable", f"{hostname}:{port}: {e}", explain_ssh_error(str(e)))
        return

    code, out, err = ssh_batch(host, ["hc", "--version"])
    if code == 0:
        remote_ver = version_of(out)
        r.add(OK, "SSH login + hc on Windows", out)
        if local_ver and remote_ver and local_ver != remote_ver:
            r.add(WARN, "hc versions match", f"here {local_ver}, Windows {remote_ver}", f"hc machine update {host}")
    else:
        r.add(FAIL, "SSH login + hc on Windows", (err or out).splitlines()[-1] if (err or out) else f"exit {code}",
              explain_ssh_error(err or out))

    # The key should refuse port forwarding; -R is refused at setup, so this is a clean test.
    code, out, err = ssh_batch(host, ["exit"], ["-o", "ExitOnForwardFailure=yes", "-R", "127.0.0.1:0:127.0.0.1:9"])
    if code == 0:
        r.add(WARN, "Port forwarding refused", "Windows accepted a remote forward",
              "add no-port-forwarding to the key line and `AllowTcpForwarding no` to sshd_config")
    elif "forward" in (err + out).lower():
        r.add(OK, "Port forwarding refused", "Windows refused a test forward")
    else:
        r.add(SKIP, "Port forwarding refused", (err or out or f"exit {code}").splitlines()[-1])

    wrapper = Path(os.path.expanduser(args.wrapper))
    if not args.no_wsl:
        if not (wrapper.exists() and os.access(wrapper, os.X_OK)):
            r.add(FAIL, "WSL wrapper", f"{wrapper} missing or not executable", "references/wsl.md, step 2")
        else:
            code, out, err = run([str(wrapper), host, distro,
                                  "echo bridge-ok; if command -v hc >/dev/null; then hc --version; else echo hc=none; fi"], 60)
            if "bridge-ok" not in out:
                r.add(FAIL, "WSL via Windows", (err or out or f"exit {code}").splitlines()[-1],
                      "run doctor on Windows (bridge, distro name), then references/troubleshooting.md")
            else:
                hc_line = out.splitlines()[-1]
                r.add(OK, "WSL via Windows", f"bridge answers; {hc_line}")
                if "hc=none" in hc_line:
                    r.add(WARN, "hc inside WSL", "not installed yet",
                          "hc machine add ... --name winbox-wsl installs it (references/wsl.md, step 4)")
                elif local_ver and version_of(hc_line) != local_ver:
                    r.add(WARN, "hc versions match", f"here {local_ver}, WSL {version_of(hc_line)}",
                          f"hc machine update {args.wsl_machine}")

    machines = linux_hc_machines()
    if machines is None:
        r.add(SKIP, "Herdr machines", "`hc machine ls` failed")
    else:
        names = {machine_name(m) for m in machines}
        wanted = [host] + ([] if args.no_wsl else [args.wsl_machine])
        for name in wanted:
            r.add(OK if name in names else FAIL, f"Herdr machine '{name}'", "added" if name in names else "not added",
                  f"hc machine add {host}" if name == host else
                  f'hc machine add --via "{wrapper} {host} {distro}" --name {args.wsl_machine}')
        for m in machines:
            if machine_name(m) not in wanted:
                r.add(INFO, f"Other machine '{machine_name(m)}'", json.dumps(m)[:200])


def linux_status(r: Report, args) -> None:
    machines = linux_hc_machines()
    if machines is None:
        r.add(FAIL, "Herdr machines", "`hc machine ls` failed (is the Herdr app installed?)")
        return
    if not machines:
        r.add(WARN, "Herdr machines", "none added")
    for m in machines:
        r.add(INFO, f"Machine '{machine_name(m)}'", json.dumps(m)[:200])
    code, out, err = ssh_batch(args.host, ["hc", "server", "status", "--json"], timeout=15)
    try:
        st = json.loads(out)
        r.add(OK, f"{args.host} core", f"{st.get('version')}, {st.get('live')} live terminal(s)")
    except (ValueError, TypeError):
        r.add(FAIL, f"{args.host} core", (err or "no answer").splitlines()[-1], explain_ssh_error(err))
    if not args.no_wsl:
        wrapper = os.path.expanduser(args.wrapper)
        code, out, err = run([wrapper, args.host, args.distro, "hc --version || echo hc=none"], 60)
        r.add(OK if code == 0 and "hc=none" not in out else WARN, f"{args.wsl_machine}",
              (out or err or f"exit {code}").splitlines()[-1])


# ----------------------------------------------------------------------------- key-line


def key_line(args) -> int:
    path = Path(os.path.expanduser(args.pubkey))
    text = path.read_text(encoding="utf-8").strip()
    if "PRIVATE KEY" in text:
        print(f"{path} is a private key. Pass the .pub file; never copy the private key anywhere.", file=sys.stderr)
        return 2
    if not text.startswith(KEY_TYPES) or "\n" in text:
        print(f"{path} doesn't look like a single OpenSSH public key", file=sys.stderr)
        return 2
    ips = []
    for ip in args.from_ips:
        try:
            ips.append(str(ipaddress.ip_network(ip, strict=False)) if "/" in ip else str(ipaddress.ip_address(ip)))
        except ValueError:
            print(f"not an IP address or network: {ip}", file=sys.stderr)
            return 2
    line = f'from="{",".join(ips)}",{",".join(RESTRICTIONS)} {text}'
    if not args.windows:
        print(line)
        return 0
    # A complete block for an admin PowerShell window on Windows (5.1 or 7). Single quotes
    # inside the key comment would end the PowerShell string, so double them.
    ps_line = line.replace("'", "''")
    blob = text.split()[1]  # the base64 key itself, to spot an already-installed key
    print(f"""# Paste into an ADMIN PowerShell window on Windows (Windows PowerShell 5.1 or PowerShell 7).
# Installs the Linux controller's public key, restricted to {', '.join(ips)}, for an
# account in Administrators (sshd reads only this file for admins), then locks the file down.
$f = 'C:\\ProgramData\\ssh\\administrators_authorized_keys'
$line = '{ps_line}'
if ((Test-Path $f) -and (Select-String -Path $f -SimpleMatch '{blob}' -Quiet)) {{
    Write-Host 'This key is already installed.'
}} else {{
    [IO.File]::AppendAllText($f, $line + "`n", (New-Object Text.UTF8Encoding $false))
}}
icacls.exe $f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'
Write-Host 'Done if icacls says: Successfully processed 1 files.'""")
    return 0


# ----------------------------------------------------------------------------- main


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("doctor", "run every check"), ("status", "quick live view")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--host", default=DEFAULT_HOST, help=f"SSH Host alias for Windows (default {DEFAULT_HOST})")
        sp.add_argument("--distro", default=DEFAULT_DISTRO, help=f"WSL distro (default {DEFAULT_DISTRO})")
        sp.add_argument("--wsl-machine", default=DEFAULT_WSL_MACHINE,
                        help=f"Herdr name of the WSL machine (default {DEFAULT_WSL_MACHINE})")
        sp.add_argument("--wrapper", default=DEFAULT_WRAPPER, help=f"Linux WSL wrapper (default {DEFAULT_WRAPPER})")
        sp.add_argument("--no-wsl", action="store_true", help="skip WSL checks")
        sp.add_argument("--json", action="store_true", help="JSON output")
    kp = sub.add_parser("key-line", help="print the restricted authorized_keys line (run on Linux)")
    kp.add_argument("pubkey", help="the .pub file, e.g. ~/.ssh/id_ed25519_winbox.pub")
    kp.add_argument("--from", dest="from_ips", nargs="+", required=True, metavar="IP",
                    help="the Linux controller's LAN IP(s)")
    kp.add_argument("--windows", action="store_true",
                    help="print a complete admin PowerShell block that installs the line on Windows")
    args = p.parse_args()

    if args.cmd == "key-line":
        return key_line(args)

    system = platform.system()
    r = Report()
    if system == "Windows":
        r.add(INFO, "Role", "Windows host (reached by the Linux controller)")
        (windows_doctor if args.cmd == "doctor" else windows_status)(r, args)
    elif system == "Linux" and "microsoft" in platform.release().lower():
        print("This is WSL. Run the script from Windows (it checks WSL too) or from the Linux controller.",
              file=sys.stderr)
        return 2
    elif system == "Linux":
        r.add(INFO, "Role", "Linux controller")
        (linux_doctor if args.cmd == "doctor" else linux_status)(r, args)
    else:
        print(f"Unsupported OS: {system}", file=sys.stderr)
        return 2
    r.print(args.json)
    return 1 if r.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
