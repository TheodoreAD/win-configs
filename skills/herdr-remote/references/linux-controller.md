# Phase 2: Linux controller

Claude runs these steps on the Linux machine itself, and asks before each one that changes
something. The user pastes the handoff prompt from Windows, and carries one block of text
back to Windows (step 4). Repeat this phase for each Windows machine. Each one gets its
own `<windows-host>` name, key and `Host` entry; never change another machine's.

## 0. Gather the facts

The handoff prompt (`herdr-remote.py handoff`, run on Windows) gives:

- **`<windows-host>`**: the Windows hostname, lowercased. It's the name for everything below.
- **`<WINDOWS_IP>`**: the Windows LAN IP.
- **`<WINDOWS_USER>`**: the Windows account name.
- **Host key fingerprint**: needed in step 5, to verify the first connect.
- **Allowed controller IP**: Windows only accepts SSH from this address.

Without a handoff prompt, ask the user for those. They're all on the Windows doctor's
"For the Linux side" line.

Discover the rest here:

```bash
ip -4 route get 1.1.1.1 | awk '{for(i=1;i<NF;i++) if($i=="src") print $(i+1)}'   # this machine's LAN IP
ls ~/.ssh/id_ed25519_<windows-host>* 2>/dev/null       # key already made?
ssh -G <windows-host> | grep -Ei '^(hostname|user|identityfile) '   # config entry already there?
command -v hc && hc --version && hc machine ls       # Herdr installed? machines?
```

`ssh -G` prints `hostname <windows-host>` when there's no entry yet. This machine's LAN IP
must equal the allowed controller IP from the handoff prompt. If it doesn't, stop: the
Windows side's firewall, `AllowUsers` and key `from=` need that IP.

## 1. Herdr desktop app

If `hc` is missing, install the app from [herdr.dev](https://herdr.dev/) and start it once.
`hc --version` should then work in a terminal.

## 2. A key used only for this

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<windows-host> -C "herdr linux-><windows-host>"
```

`ssh-keygen` asks for a passphrase, so the user types it in their own terminal. Suggest
the `!` prefix in Claude Code, or a separate terminal.

Then load the key into the desktop's ssh-agent with `ssh-add ~/.ssh/id_ed25519_<windows-host>`.
GNOME Keyring and KDE Wallet can unlock it at login. Herdr connects in the background and
can't type a passphrase.

Without a passphrase, anyone who can read the file gets into Windows. That's acceptable
only because the key opens nothing but the weaker machine, and only from this IP. Never
print, copy or move the private key; only the `.pub` goes to Windows.

## 3. `~/.ssh/config`

Add this, above any `Host *` block, because SSH uses the first value it finds:

```
Host <windows-host>
    HostName <WINDOWS_IP>
    User <WINDOWS_USER>
    IdentityFile ~/.ssh/id_ed25519_<windows-host>
    IdentitiesOnly yes
    ForwardAgent no
    ForwardX11 no
```

## 4. The one thing to carry to Windows

```bash
python3 <skill>/scripts/herdr-remote.py key-line ~/.ssh/id_ed25519_<windows-host>.pub --from <LINUX_IP> --windows
```

This prints a complete block for an **admin PowerShell window on Windows**, with the
restricted key already inside it. Save it to a file the user can move easily:

```bash
python3 <skill>/scripts/herdr-remote.py key-line ~/.ssh/id_ed25519_<windows-host>.pub --from <LINUX_IP> --windows > ~/<windows-host>-install-key.ps1.txt
```

The user moves it to Windows by any route (a note, a chat to themselves, a USB stick). It
only holds a public key, which isn't secret. On Windows they paste it into an admin
PowerShell window (5.1 or 7). It works if `icacls` says `Successfully processed 1 files`.
If Claude runs on Windows too, it can check the result there with `doctor`.

## 5. First connect

```bash
ssh-keyscan -t ed25519 <WINDOWS_IP> 2>/dev/null | ssh-keygen -lf -
```

Ask the user to compare this fingerprint with the "host key" in the Windows doctor's "For
the Linux side" line. Only if they match:

```bash
ssh <windows-host> hc --version
```

Answer `yes` to the host key prompt. It should print `hc x.y.z`, with no password prompt.
If it fails, read `troubleshooting.md` before changing anything.

## 6. Add the machine to Herdr

```bash
hc machine add <windows-host>
```

- **Older `hc` on Windows**: if Windows has an older `hc` than this machine, run
  `hc machine update <windows-host>`. It copies this `hc` there; its terminals keep running.
- **Disconnects**: Windows terminals live in the Windows core, so they survive a
  disconnect.

## 7. Check

```bash
python3 <skill>/scripts/herdr-remote.py doctor --host <windows-host> --no-wsl   # drop --no-wsl after phase 3
python3 <skill>/scripts/herdr-remote.py doctor                                  # every Windows machine set up here
```

The doctor also tries a remote port forward. It should say "refused", which proves the
`no-port-forwarding` restriction is active.
