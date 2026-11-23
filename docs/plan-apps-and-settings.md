# Plan: apps outside scoop and Windows settings

Not done yet. Today the repo covers scoop tools, fonts, the PowerShell profile, SSH, Claude Code,
Herdr and WSL. Apps installed any other way (winget, installers, the Store) and Windows settings
aren't captured. This plan is for doing that later. Entertainment apps and tools tied to one
machine's hardware stay out on purpose.

## Apps

Approach:

- **Prefer scoop** when a package exists, so everything updates with `scoop update *`.
- **Otherwise winget.** `winget export` writes package IDs only (nothing personal). Curate it
  into lists in a `winget/` folder, e.g. `winget/dev.json` and `winget/optional.json`, installed
  with `winget import --import-file <file> --accept-package-agreements`.
- **Store apps** that winget can't install get a line in the README instead.

Candidates found on the first machine (2026-11-23), by group:

- **Dev tools** — Visual Studio Code (user install), JetBrains Toolbox (PyCharm), Windows
  Terminal, PowerToys, Notepad++, the Claude desktop app
- **Work and communication (optional)** — Slack, Microsoft Teams, Zoom, Outlook, Chrome Remote
  Desktop, TeamViewer
- **Utilities (optional)** — TeraCopy, PDFtk, Google Drive, OneDrive, a VPN client

Decide per app: scoop or winget, required or optional.

## Windows settings

All of these are a registry value or a config file, so they can be applied without anything
personal in the repo. Per the global rules, anything with logic is a Python script (`winreg`),
not a PowerShell script; one-off values can be README one-liners.

| **Setting** | **Where** | **State on the first machine** |
|---|---|---|
| **Show file extensions** | `HKCU\...\Explorer\Advanced` `HideFileExt=0` | On (not default) |
| **Show hidden files** | `HKCU\...\Explorer\Advanced` `Hidden=1` | On (not default) |
| **Dark mode** | `HKCU\...\Themes\Personalize` `AppsUseLightTheme=0`, `SystemUsesLightTheme=0` | On |
| **Long paths** | `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem` `LongPathsEnabled=1` (admin) | On (not default); helps git and Node |
| **Default terminal app** | Windows Terminal → Settings → Startup | Windows Terminal |
| **Windows Terminal profile** | `%LOCALAPPDATA%\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json` | Exists; capture the parts that matter (default profile `pwsh`, Nerd Font) as a template |
| **WSL limits** | `~/.wslconfig` (memory, CPUs, swap) | Not set |
| **Developer Mode** | Settings → System → For developers | Off; only needed for symlinks without admin |

Left at default and probably not worth capturing: taskbar alignment, power plan (Balanced).

## Network profile and sharing

How it works:

- **A network profile is a label** (Public, Private, Domain) that decides which firewall
  allow-rules apply. Both Public and Private block unsolicited incoming connections by default;
  the difference is which rules are switched on. Windows keeps Network Discovery and File and
  Printer Sharing off on Public and allows them on Private.
- **App rules are tied to a profile:** clicking "Allow" in an app's firewall prompt creates a
  rule only for the profile that was active then. Moving the network to another profile
  silently changes which apps can accept connections.
- **Printing to a network printer is outgoing** (IPP/WSD to the printer), so it needs neither
  File and Printer Sharing nor Private. Those are for sharing this PC's own folders or printers.

State on the first machine (2026-11-24), origin unknown:

- **Profile:** the home LAN adapter is on Public; the VPN adapter is on Private.
- **Sharing:** File and Printer Sharing is enabled for Public, and a share named `Users`
  exposes all of `C:\Users` on the network. The network printer is connected over IPP and
  doesn't depend on either.
- **Syncthing:** its two firewall rules (TCP and UDP, Public only) allow the program at
  `scoop\apps\syncthing\2.0.15\syncthing.exe`. Scoop updated Syncthing to a new version
  folder, so the rules no longer match the running program: incoming LAN connections are
  blocked and Syncthing most likely falls back to relays (slower, but still encrypted).
- **Other app rules** were created for whichever profile was active when "Allow" was clicked,
  so some apps are allowed only on Public and others only on Private.

### Target

- **Home LAN on Private**, anything else Public.
- **No sharing from this PC**: no `Users` share, File and Printer Sharing rules off. Printing
  still works.
- **Syncthing** allowed by port, not by program path (so scoop updates can't break it), only
  from the local subnet: TCP/UDP 22000 (sync, including QUIC) and UDP 21027 (local
  discovery).
- **Every remaining inbound allow rule reviewed**: needed ones scoped to `LocalSubnet` or a
  specific IP, the rest disabled.

### Steps

Run in an **admin** PowerShell 7. Check the adapter name first with `Get-NetConnectionProfile`.

```shell
# 1. Stop sharing C:\Users and turn off File and Printer Sharing (printing via IPP is unaffected)
Remove-SmbShare -Name Users -Force
Disable-NetFirewallRule -DisplayGroup "File and Printer Sharing"
# 2. Home LAN -> Private (replace the adapter name)
Set-NetConnectionProfile -InterfaceAlias "<home LAN adapter>" -NetworkCategory Private
# 3. Syncthing: replace the program-path rules with port rules limited to the local subnet
Get-NetFirewallRule -DisplayName "syncthing.exe" | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "Syncthing sync (TCP 22000)" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 22000 -RemoteAddress LocalSubnet -Profile Private
New-NetFirewallRule -DisplayName "Syncthing sync (UDP 22000, QUIC)" -Direction Inbound -Action Allow `
    -Protocol UDP -LocalPort 22000 -RemoteAddress LocalSubnet -Profile Private
New-NetFirewallRule -DisplayName "Syncthing discovery (UDP 21027)" -Direction Inbound -Action Allow `
    -Protocol UDP -LocalPort 21027 -RemoteAddress LocalSubnet -Profile Private
# 4. Review what else accepts incoming connections; disable what isn't needed
#    (Disable-NetFirewallRule -DisplayName "<name>")
Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True |
    Where-Object { $_.DisplayGroup -notmatch 'Core Networking' } |
    Sort-Object DisplayName | Select-Object DisplayName, Profile
```

Check afterwards:

- **Syncthing:** in its web UI, remote devices on the LAN show a direct address (`tcp://` or
  `quic://<LAN IP>:22000`) instead of `relay://`.
- **Printing:** print a test page.
- **Sharing:** `Get-SmbShare` lists only the built-in admin shares (`ADMIN$`, `C$`, `IPC$`).
- **The Herdr SSH rule** from the `herdr-remote` skill uses all profiles scoped to the Linux
  machine's IP, so it isn't affected by the profile switch.

## Remove superseded or useless installs

Run these yourself (uninstalling needs explicit approval); check each for work dependencies
first.

- **Windows 10 Update Assistant** — useless on Windows 11:
  `winget uninstall --id Microsoft.UpdateAssistant --exact`
- **7-Zip 16.04** — from 2016, known vulnerabilities, superseded by scoop's `7zip`:
  `winget uninstall --id 7zip.7zip --exact`. This removes the Explorer right-click menu; scoop's
  7-Zip restores it with `reg import "$HOME\scoop\apps\7zip\current\install-context.reg"`.
- **Probably obsolete, check first:** Microsoft SQL Server 2012 Native Client, Microsoft ODBC
  Driver 17 for SQL Server, Microsoft Azure Storage Emulator (deprecated; Azurite replaces it),
  Microsoft MPI, Microsoft Web Deploy 4.0. These come from old .NET/Azure tooling and may still
  be needed by work projects.
