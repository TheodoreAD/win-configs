# Phase 2: Linux controller

Below, `<WINDOWS_IP>` is the Windows machine's reserved LAN IP, `<LINUX_IP>` is this
machine's, and `<WINDOWS_USER>` is the Windows account name (`$env:USERNAME` there).

## 1. Herdr desktop app

Install it from [herdr.dev](https://herdr.dev/) and start it once. Check that `hc --version` works
in a terminal. Remote machines are added with `hc machine add`. In the app, Settings →
Machines → Add machine does the same for named `~/.ssh/config` hosts.

## 2. A key used only for this

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_winbox -C "herdr linux->winbox"
```

Set a passphrase, then load the key into your desktop's ssh-agent (`ssh-add
~/.ssh/id_ed25519_winbox`; GNOME Keyring and KDE Wallet can unlock it at login). Herdr
connects in the background and can't type a passphrase. Without a passphrase, anyone who
can read the file gets into Windows. That's acceptable only because the key opens nothing
but the weaker machine, and only from this IP.

## 3. The restricted key line for Windows

```bash
python3 <skill>/scripts/herdr-remote.py key-line ~/.ssh/id_ed25519_winbox.pub --from <LINUX_IP>
```

Send that one line to Windows by any route: paste, USB, a note. A public key isn't secret.
Install it with `references/windows-host.md` step 5.

## 4. `~/.ssh/config`

```
Host winbox
    HostName <WINDOWS_IP>
    User <WINDOWS_USER>
    IdentityFile ~/.ssh/id_ed25519_winbox
    IdentitiesOnly yes
    ForwardAgent no
    ForwardX11 no
```

Put it above any `Host *` block: SSH uses the first value it finds for each setting.

## 5. First connect

```bash
ssh winbox hc --version
```

SSH asks you to confirm the host key. Compare the fingerprint with the one Windows
`doctor` printed, or `references/windows-host.md` step 6, and answer `yes` only if they
match. You should then see `hc x.y.z`, with no password prompt.

## 6. Add the machine to Herdr

```bash
hc machine add winbox
```

- **Older `hc` on Windows**: if Windows has an older `hc` than this machine, run
  `hc machine update winbox` later. It copies this `hc` there; its terminals keep running.
- **Disconnects**: Windows terminals live in the Windows core, so they survive a
  disconnect.

## 7. Check

```bash
python3 <skill>/scripts/herdr-remote.py doctor --no-wsl   # drop --no-wsl after phase 3
```

The doctor also tries a remote port forward. It should say "refused", which proves the
`no-port-forwarding` restriction is active.
