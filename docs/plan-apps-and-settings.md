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

State on the first machine (2026-11-24): the home LAN is on Public, but File and Printer Sharing
is enabled for Public, a share named `Users` exists, and some app rules exist only for Public
(e.g. Syncthing) while others exist only for Private.

Ideal setup, to decide and apply:

1. **Profile:** Private for the trusted home LAN (Windows' intended label; Network Discovery
   helps find printers), Public for anything else. Keeping Public at home also works, as long
   as the rules below are right.
2. **File and Printer Sharing off** unless this PC really shares a folder or printer. Remove
   unneeded shares first (`Get-SmbShare`, `Remove-SmbShare -Name <name>`), then, as admin:
   `Disable-NetFirewallRule -DisplayGroup "File and Printer Sharing"`.
3. **App rules that need the LAN** (Syncthing, remote access tools, the Herdr SSH rule) cover
   the profile actually in use, ideally scoped to the LAN (`-RemoteAddress LocalSubnet`) or to
   a specific IP. Check with:
   `Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True | Select-Object DisplayName, Profile`.
4. **Switch the profile** (admin):
   `Set-NetConnectionProfile -InterfaceAlias <adapter> -NetworkCategory Private`.

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
