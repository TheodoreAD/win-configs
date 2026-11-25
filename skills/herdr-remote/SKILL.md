---
name: herdr-remote
description: Set up, check and repair a Herdr desktop-app setup where a Linux machine is the controller and reaches a Windows machine (and that Windows machine's WSL distro) as Herdr machines over SSH. Includes a doctor that checks either side (sshd, key restrictions, key file ACL, firewall, hc versions, the WSL bridge) and a quick status view. Use this whenever the user wants to add, enroll or connect another computer or WSL to Herdr, mentions `hc machine add`, a Windows or WSL machine in Herdr's sidebar, Herdr over SSH, Windows OpenSSH server for Herdr, or asks to run the herdr doctor/status, or a Herdr remote machine won't connect, even if they don't name this skill.
---

# Herdr remote: Linux controller → Windows host + WSL

## The setup, and why it points this way

The Linux machine holds the serious work and is better secured. Windows is the weaker
machine. So Linux runs the Herdr desktop app and holds the only SSH key. Windows runs an
SSH server that accepts that one key from the Linux machine's IP. Nothing on Windows can
open Linux: if Windows is compromised, the attacker gets Windows and nothing more.

Don't propose the other direction (Windows → Linux), agent forwarding, or a key that
opens Linux stored on Windows. Each of those makes Linux only as safe as Windows. If the
user asks for one, explain that cost first.

```
Linux controller (Herdr app, hc, key ~/.ssh/id_ed25519_<windows-host>)
   │  ssh <windows-host> hc connect                       → Herdr machine "<windows-host>"
   │  herdr-via-wsl → ssh <windows-host> wsl.exe … hc-via-b64 → Herdr machine "<windows-host>--wsl"
   ▼
Windows host: OpenSSH server, firewall allows the Linux IP only,
              key restricted: from=<Linux IP>, no forwarding, no pty
   └─ WSL distro (Ubuntu-24.04): no SSH server, no open ports; reached via wsl.exe
```

Herdr here is the **desktop app**: `herdr-app` plus `hc` / `herdr-core`. It is not the
older TUI (`herdr` CLI, `herdr machine add`). Commands for one don't work in the other.
`hc machine add` connects by running `hc connect` over a plain SSH command. That's why
the key can refuse port forwarding and PTYs.

### Names

Everything is named after the Windows machine's hostname, lowercased: `<windows-host>`
throughout these docs. One Linux controller can then serve several Windows machines side
by side, each with its own key and its own restrictions.

- **SSH Host alias and Herdr machine**: `<windows-host>`. `hc machine add` takes the
  machine's name from the alias.
- **Herdr WSL machine**: `<windows-host>--wsl`. The double dash keeps it apart from a
  Windows machine whose own hostname ends in `-wsl`; hostnames practically never contain
  `--`, and Herdr accepts it in machine names.
- **Key**: `~/.ssh/id_ed25519_<windows-host>`, one per Windows machine.
- **Distro**: `Ubuntu-24.04` unless the Windows doctor reports otherwise.

The script follows the same rules:

- **On Windows** it uses its own hostname.
- **On Linux**, without `--host`, it checks every `Host` in `~/.ssh/config` whose key is
  `id_ed25519_<that host>`, and ignores unrelated SSH hosts. With `--host <name>` it
  checks only that one. `--distro` and `--wsl-machine` override the other names.

The Windows `handoff` prompt states the names, so Claude on Linux never has to guess
them. When adding a machine, never touch another machine's `Host` entry or key.

## Doctor, status and key-line

All three are in `scripts/herdr-remote.py`. It's one script for both machines, detects
the OS, uses only the standard library, and is read-only. Run it on Windows with
`python -I <skill>/scripts/herdr-remote.py ...` and on Linux with `python3 ...`.

- **`doctor`**: every check, each line OK/WARN/FAIL/skip, with a fix for every problem.
  Exits 1 if anything failed. On Windows it starts the WSL distro to look inside it;
  `--no-wsl` skips that.
- **`status`**: quick live view.
  - On Windows: sshd state, who is connected right now, the Herdr core, whether WSL is
    running (it doesn't start WSL).
  - On Linux: the Herdr machines, plus a probe of each one.
- **`handoff`** (Windows only): the doctor, turned into a prompt for Claude on the Linux
  controller. It goes to stdout; the list of current failures goes to stderr.
- **`key-line KEY.pub --from <Linux IP> [--windows]`**: run on Linux. It prints the
  restricted `authorized_keys` line, and refuses private keys. With `--windows` it prints a
  complete admin PowerShell block (5.1 or 7) that installs the line on Windows and locks
  the file down, ready to paste.

Some Windows checks only work from an elevated shell, because the key file is readable
only by Administrators. Claude Code's shell isn't elevated, and the `!` prefix doesn't
elevate either. Unelevated, those checks are marked skipped or "locked down (expected)",
never failed. For the full picture, ask the user to run the doctor in an admin terminal
and paste the output.

When the user asks for "doctor" or "status", run the script and summarize. Lead with the
FAILs, then the WARNs, and give the fix for each in plain words. Each fix names the
reference file and step to follow.

## Setting it up

The user may come to you on either machine, partway through, in a new session that
remembers nothing. Don't ask where they are: run `doctor` on the machine you're on (it
detects Windows or Linux), and the first FAIL tells you the phase and step. Then guide the
steps for *this* machine. Discover what you can (this machine's IP, existing keys and
config, `hc machine ls`). Ask only for what lives on the other machine: on Linux, the
Windows IP, account name and host key fingerprint, which the Windows doctor's "For the
Linux side" line shows.

Anything that must cross between the machines should be a single block the user can move
as-is. There are two:

- **Windows → Linux: `herdr-remote.py handoff`**, run on Windows. It runs the doctor and
  prints a ready-to-paste prompt for Claude on Linux: the skill install command, the
  Windows IP, account, host key fingerprint and allowed controller IP, what's done and
  open on Windows, and the steps to work through. Offer it once the Windows host phase is
  done, or whenever the user moves to the Linux machine. Show the prompt in full in one
  code block, not summarized: the user copies it as-is.
- **Linux → Windows: `key-line ... --windows`** (`references/linux-controller.md`, step 4),
  the key-install block.

Work in this order, and run `doctor` on the machine you just changed after each phase:

1. **Windows host**: `references/windows-host.md` (admin steps: sshd, firewall, sshd_config, key file).
2. **Linux controller**: `references/linux-controller.md` (key, `~/.ssh/config`, first connect, `hc machine add <windows-host>`).
3. **WSL as its own machine**: `references/wsl.md` (normal user, bridge, wrapper, `hc machine add --via ...`).

Read only the reference for the phase you're on. When something breaks, use
`references/troubleshooting.md`.

How to work through it with the user:

- **Admin commands** (Windows steps 2–6): give them to the user to run in an admin
  PowerShell 7 window. Don't try to elevate from Claude's shell.
- **State changes need a go-ahead**: installing services, editing `sshd_config`, firewall
  rules, creating a WSL user. Say what will change and get confirmation before running
  anything yourself. Read-only checks need no confirmation.
- **Keep the restrictions in place**: don't drop `from=`, turn passwords back on, or open
  the firewall to make a connection work. These restrictions are the point of the setup.
  If one seems to be the cause, show the user the evidence and the cost, and let them
  decide.
- **Private keys**: never print, copy or move them. Only the `.pub` file goes to Windows,
  and it isn't secret.
- **IPs**: give both machines DHCP reservations. `from=`, the firewall rule and
  `~/.ssh/config` all depend on them, so a changed IP looks like "Permission denied" or
  a timeout.

## Files

- **`scripts/herdr-remote.py`** — doctor, status, handoff and key-line
- **`scripts/wsl-bridge.py`** — install, check or remove the WSL bridge, on Windows. It's the
  one script that changes state, and the change stays inside WSL; repeatable for
  setup/teardown runs.
- **`assets/hc-via-b64`** — the WSL bridge. Goes to `/usr/local/bin/hc-via-b64` inside WSL.
- **`assets/herdr-via-wsl`** — the Linux wrapper used as Herdr's `--via` command. Goes to `~/.local/bin/` on Linux.
- **`references/`** — the setup phases and troubleshooting
