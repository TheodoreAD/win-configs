# Phase 1: Windows host

Steps 2–6 change system settings and need an **admin PowerShell 7** window (Start → pwsh →
Run as administrator). Below, `<LINUX_IP>` is the Linux controller's LAN IP.

## 1. Fixed IPs

Give both machines a DHCP reservation on the router. `doctor` on Windows lists this
machine's addresses; the LAN one has origin `Dhcp`. Use that one for `HostName` on Linux.
Don't use the vEthernet (WSL, Default Switch) or VPN addresses.

## 2. Install the OpenSSH server, and narrow the firewall before it first starts

The install creates the rule `OpenSSH-Server-In-TCP`, open to any address. Narrow it
before sshd ever listens:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -RemoteAddress <LINUX_IP> -Profile Any
Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory
```

- **`-Profile Any`**: the rule then applies whichever profile the LAN has. Windows often
  marks a wired LAN as **Public**, and a rule limited to Private would silently not apply.
  `RemoteAddress` is what keeps it tight.
- **Other port-22 rules**: `doctor` fails any other enabled inbound rule that allows port 22
  from any address.

## 3. Start sshd

```powershell
Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd
```

The first start creates `C:\ProgramData\ssh\` with `sshd_config` and the host keys.

## 4. sshd_config

Edit `C:\ProgramData\ssh\sshd_config` as admin (`notepad C:\ProgramData\ssh\sshd_config`).
Put these lines **above** the `Match Group administrators` block at the end of the file.
Anything below a `Match` line only applies inside that block.

```
PasswordAuthentication no
AllowUsers <windows user, lowercase>@<LINUX_IP>
DisableForwarding yes
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
GatewayPorts no
```

- **`AllowUsers`**: Windows OpenSSH wants the name in lowercase. Use
  `$env:USERNAME.ToLower()`, e.g. `my-user` for a Windows account named `My-User`. The
  `@<LINUX_IP>` part is a second IP check, on top of the firewall and the key's `from=`.
- **`DisableForwarding yes`**: turns off every kind of forwarding at once. The lines after
  it say the same thing one at a time, for older sshd versions and for readers.
- **The `Match Group administrators` block**: leave it as it is. It's why an admin
  account's keys live in `administrators_authorized_keys` (step 5).

Check the file, then restart:

```powershell
& C:\Windows\System32\OpenSSH\sshd.exe -t   # prints nothing when the config is valid
Restart-Service sshd
```

## 5. Install the Linux machine's public key

The key line comes from Linux (`references/linux-controller.md`, steps 2–3). It looks like
`from="<LINUX_IP>",no-port-forwarding,no-agent-forwarding,no-x11-forwarding,no-pty ssh-ed25519 AAAA... herdr linux->winbox`.

If the Windows account is in **Administrators** (check with
`whoami /groups | Select-String S-1-5-32-544`), sshd ignores `~\.ssh\authorized_keys` and
reads only this file:

```powershell
$f = 'C:\ProgramData\ssh\administrators_authorized_keys'
$line = '<paste the whole line from key-line>'
if (Test-Path $f) { Add-Content -Path $f -Value $line -Encoding utf8NoBOM }
else { Set-Content -Path $f -Value $line -Encoding utf8NoBOM }
icacls.exe $f /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

The `icacls` step is required. If anyone else can read the file, sshd ignores it, with no
error. Non-admin accounts use `~\.ssh\authorized_keys` instead, owned by the user.

What the restrictions do:

- **`from=`**: the key only works from the Linux IP.
- **`no-port-forwarding`**: the key can't be used to tunnel into the network.
- **`no-agent-forwarding`, `no-x11-forwarding`**: no agent or X11 forwarding.
- **`no-pty`**: no interactive terminal session. Herdr doesn't need one.

A side effect of `no-pty`: plain `ssh winbox` gives a clumsy shell. Use commands such as
`ssh winbox hc --version` to test.

## 6. Host key fingerprint, for Linux's first connect

```powershell
Get-ChildItem C:\ProgramData\ssh\ssh_host_*_key.pub | ForEach-Object { ssh-keygen -lf $_ }
```

`doctor` prints the same thing. Compare it with what Linux shows on its first `ssh winbox`.

## 7. Keep Herdr's core available

`hc` must be on the user PATH. The desktop app installer adds
`%LOCALAPPDATA%\Programs\herdr-core`, and SSH sessions read the PATH from the registry.

Start the core from the Windows desktop, not over SSH. An admin account's SSH login is
elevated, and `hc`'s own notes warn that a core started elevated over SSH can block the
same user's desktop session. Keep the Herdr app starting at login, or run `hc server start`
in a normal desktop terminal. On Windows, `hc server status` only reports; it never starts
a core.

If this is a laptop, sleep drops the connection. Set "When plugged in, put my device to
sleep" to Never if Linux should reach it anytime.

## 8. Check

```powershell
python -I <skill>\scripts\herdr-remote.py doctor
```

Run it from an elevated window as well; only an elevated run can inspect the key file's
contents.
