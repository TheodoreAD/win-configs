# Phase 3: WSL as its own Herdr machine

Linux reaches WSL as `ssh <windows-host>` → `wsl.exe` → a small bridge script. WSL gets no SSH
server and no open ports. The `<windows-host>` key already gives a shell as the Windows user, who
can run `wsl.exe` anyway, so this grants nothing new.

### Why there's a bridge

Herdr's `--via` appends a shell line to the command. Windows sshd hands commands to
`cmd.exe`, which reinterprets quotes, `|` and `<`, so the line would arrive broken. The
Linux wrapper, `herdr-via-wsl`, base64-encodes the line. Base64 contains no characters
`cmd.exe` cares about. Inside WSL, `hc-via-b64` decodes the line and `eval`s it, which
keeps stdin and stdout connected for hc's protocol.

## 0. A normal default user in WSL

If `doctor` says `WSL default user — root`, fix this first. Otherwise every Herdr terminal
in WSL runs as root.

If the `power-user-linux-setup` repo is checked out on Windows, its `wsl-distro` tasks do it
all. Run them from that repo's root, in a normal (not admin) PowerShell:

```powershell
uv run invoke wsl-distro.check      # what's missing, changes nothing
uv run invoke wsl-distro.install    # creates user dev with passwordless sudo, makes it the default
```

They take `--name` and `--user` if the names differ. It sets the default user in the
Windows registry and leaves `/etc/wsl.conf` alone. Then go on to step 1.

Without the repo, do it by hand. Run this in PowerShell on Windows:

```powershell
wsl -d Ubuntu-24.04 -u root
```

Then, inside WSL, as root:

```bash
adduser <name>                                   # sets the sudo password
usermod -aG sudo <name>                          # add docker too if you use it: docker group = root-equivalent
printf '\n[user]\ndefault=<name>\n' >> /etc/wsl.conf   # append; don't overwrite (it holds [boot] systemd=true)
exit
```

Back in PowerShell:

```powershell
wsl --terminate Ubuntu-24.04
wsl -d Ubuntu-24.04 -e whoami    # should print <name>
```

Writing `/etc/wsl.conf` with `echo ... | sudo tee /etc/wsl.conf` replaces the whole file.
That's a common way the `[user]` line gets lost.

## 1. Install the bridge in WSL

Run this on Windows, in a normal (not admin) shell. It writes the file as WSL's root
through `wsl -u root`, which needs no Windows elevation:

```powershell
python -I <skill>\scripts\wsl-bridge.py install   # copies assets/hc-via-b64 in, then tests it as the default user
python -I <skill>\scripts\wsl-bridge.py check     # installed, same as the skill's copy, answers?
python -I <skill>\scripts\wsl-bridge.py remove    # teardown; touches nothing else in WSL
```

Each takes `--distro`. Repeating one is safe: `install` skips an identical file and `remove`
skips a missing one. Reinstalling the distro removes the bridge, so run `install` again
afterwards. The script writes the file with LF line endings, even from a CRLF checkout.

## 2. Install the wrapper on Linux

The skill installed on Linux ships it, so install it from there. Nothing to copy by hand:

```bash
install -D -m 755 <skill>/assets/herdr-via-wsl ~/.local/bin/herdr-via-wsl
```

## 3. Test the path by hand

```bash
~/.local/bin/herdr-via-wsl <windows-host> Ubuntu-24.04 'id -un; uname -r; command -v hc || echo no-hc-yet'
```

You should see the WSL user, a `microsoft` kernel, and `no-hc-yet` the first time.

## 4. Add it to Herdr

```bash
hc machine add --via "$HOME/.local/bin/herdr-via-wsl <windows-host> Ubuntu-24.04" --name <windows-host>--wsl --install
```

`--install` copies the Linux `hc` into WSL's `~/.local/bin`, and the bridge puts that folder on
PATH. Without the flag, `hc` asks first in a terminal. Claude's shell is not a terminal, so pass
the flag rather than wait for a question that never comes. It printed `… now has hc 0.1.22` the
first time this ran, on 2026-11-27.

## 5. WSL's lifetime

`wsl.exe` starts the distro on demand, so connecting wakes it. WSL may shut an idle
distro down after the last connection closes, and that ends its terminals. Check after a
disconnect:

```powershell
wsl -l -v
```

If the distro shows Stopped and terminals are lost, see `troubleshooting.md` ("WSL
terminals gone after reconnect").

## 6. Check

On Linux:

```bash
python3 <skill>/scripts/herdr-remote.py doctor --host <windows-host>
```

On Windows:

```powershell
python -I <skill>\scripts\herdr-remote.py doctor
```

The Windows run checks the user, the bridge, and `hc` inside WSL.
