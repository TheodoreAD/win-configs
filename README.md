# Windows Configs

Configurations for all manner of Windows system and software

## Development tools installation

IMPORTANT: It's best to download the repo as a zip file and run the commands
from the root of the repo. Some commands depend on the files in the repo.

You can skip some scripts and simply copy and paste the contents of the various files
if you don't want to download the repo.

Run this before any other section below:
```shell
# ============================================================================
#                                Prerequisites
# ============================================================================
# NOTE: the long-lived execution policy was required for some items
#Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
scoop install main/git
# Add git's GNU tools and .local\bin to the user PATH.
# NOTE: Windows builds PATH as system PATH + user PATH, so System32 always comes
# first. Programs present in both (find.exe, sort.exe, ssh.exe) resolve to the
# System32 versions; call git's GNU ones by full path if needed. See
# docs/claude-windows-tools.md.
$pathsToAdd = @(
    "$env:USERPROFILE\scoop\apps\git\current\usr\bin",
    "$env:USERPROFILE\scoop\apps\git\current\bin",
    "$env:USERPROFILE\.local\bin"
)
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$newEntries  = $pathsToAdd | Where-Object { $currentPath -notlike "*$_*" }
if ($newEntries.Count -gt 0) {
    $combined = ($newEntries -join ";") + ";$currentPath"
    [Environment]::SetEnvironmentVariable("PATH", $combined, "User")
    Write-Host "Added to user PATH (restart your shell):"
    $newEntries | ForEach-Object { Write-Host "  + $_" }
} else {
    Write-Host "All paths already in PATH."
}
# PowerShell 7: the shell for everything from here on (terminals, Herdr, Claude Code).
# Its profile is separate from Windows PowerShell 5.1's:
#   5.1: Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
#   7:   Documents\PowerShell\Microsoft.PowerShell_profile.ps1
# NOTE: update pwsh itself from powershell.exe (`scoop update pwsh`), not from inside pwsh.
scoop install main/pwsh
```

Open a new **PowerShell 7** terminal (`pwsh`, from the Start menu or by typing `pwsh`) and run
everything below from there, from the root of this repo. This block installs what the profile
needs, then the profile itself:

```shell
# ============================================================================
#                                   Fonts
# ============================================================================
scoop bucket add nerd-fonts
# Proportional Nerd Font (for editors)
scoop install nerd-fonts/CascadiaCode-NF
# Monospaced Nerd Font (for terminals; font name "CaskaydiaCove Nerd Font Mono")
scoop install nerd-fonts/CascadiaCode-NF-Mono
# Hold the fonts: scoop can install them but never update them. Windows loads every
# registered font at sign-in and the System process keeps the files locked for the
# whole session, so the package's pre-uninstall "is it in use" check always fails.
# Without the hold, a new font version makes `scoop update *` stop entirely.
# To update anyway: scoop unhold both, delete their "CaskaydiaCove ... (TrueType)"
# entries under HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts, restart
# Windows, then `scoop update CascadiaCode-NF CascadiaCode-NF-Mono` before opening
# anything (it re-registers the new version).
scoop hold CascadiaCode-NF CascadiaCode-NF-Mono
# TODO: configure VS Code with CascadiaCode Nerd Font
#   editor: "CaskaydiaCove Nerd Font"
#   terminal: "CaskaydiaCove NFM"
# ============================================================================
#                               Terminal Icons
# ============================================================================
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name Terminal-Icons -Repository PSGallery -Scope CurrentUser -Force
# ============================================================================
#                                 Oh My Posh
# ============================================================================
scoop install main/oh-my-posh
# TODO: test more prompts from https://ohmyposh.dev/docs/themes
# current theme: if_tea
# other tested themes: atomic powerlevel10k_modern
# Terminal-Icons must be installed from pwsh so it lands in PowerShell 7's own
# module folder (Documents\PowerShell\Modules).
# ============================================================================
#                                    fnm
# ============================================================================
# fnm (Fast Node Manager) installs Node versions side by side; Node itself is
# installed further down. The profile runs `fnm env --use-on-cd`.
scoop install main/fnm
# ============================================================================
#                              PowerShell profile
# ============================================================================
# Install scripts/profile.ps1 as the "Power User Profile" block of the PowerShell 7
# profile (Documents\PowerShell\Microsoft.PowerShell_profile.ps1).
if (!(Test-Path $PROFILE)) { New-Item -ItemType File -Force -Path $PROFILE | Out-Null }
$blockContent = Get-Content .\scripts\profile.ps1 -Raw
$profileText = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($profileText -match [regex]::Escape("# Power User Profile")) {
    $pattern = '(?m)^# ={10,}\r?\n# Power User Profile\r?\n# ={10,}[\s\S]*?^# ={10,}[ \t]*(\r?\n|$)'
    $newText = [regex]::Replace($profileText, $pattern, { $blockContent })
    Set-Content $PROFILE -Value $newText -NoNewline
    Write-Host "✅ Power User Profile block replaced in: $PROFILE"
} else {
    Add-Content $PROFILE -Value "$([Environment]::NewLine)$blockContent"
    Write-Host "✅ Power User Profile block added to: $PROFILE"
}
# Windows PowerShell 5.1 has its own profile; make it load this one, so there's a
# single file to maintain (the old 5.1 profile is kept as .bak). On a fresh machine
# Terminal-Icons exists only for PowerShell 7, so 5.1 reports it missing; 5.1 isn't
# used day to day, so that's left as is.
$Docs = [Environment]::GetFolderPath('MyDocuments')
$Ps51Profile = "$Docs\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
New-Item -ItemType Directory -Force (Split-Path $Ps51Profile) | Out-Null
if (Test-Path $Ps51Profile) { Copy-Item $Ps51Profile "$Ps51Profile.bak" -Force }
Set-Content $Ps51Profile -Value @'
# Windows PowerShell 5.1 loads the PowerShell 7 profile, so there's one file to maintain.
. (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PowerShell\Microsoft.PowerShell_profile.ps1')
'@
```

Open a new `pwsh` tab: the Oh My Posh prompt should show icons, and `l` (GNU long listing) and
`d` (listing with icons) should work. The profile keeps PowerShell's built-in aliases (`ls`,
`cat`, `where`, `sort` are cmdlets); GNU tools are `ls.exe`, `cat.exe` and so on. See
[docs/claude-windows-tools.md](docs/claude-windows-tools.md) for why. Then continue:

```shell
# ============================================================================
#                                   Wezterm
# ============================================================================
# Fallback terminal. Herdr (see herdr/README.md) is the main terminal; WezTerm is
# for when Herdr has to be closed: `scoop update pwsh` (run from powershell.exe),
# Herdr updates or problems, restarting herdr-core. Starts pwsh in two side-by-side
# panes, maximized. (Windows Terminal, built into Windows 11, would also do.)
scoop bucket add extras
scoop install extras/wezterm
reg import "$HOME\scoop\apps\wezterm\current\install-context.reg"
$weztermConfigDir = "$env:USERPROFILE\.config\wezterm"
$weztermConfigFile = "$weztermConfigDir\wezterm.lua"
New-Item -ItemType Directory -Force -Path $weztermConfigDir | Out-Null
$weztermConfig = @"
local wezterm = require "wezterm"
local mux = wezterm.mux
local config = wezterm.config_builder()
config.default_prog = { "pwsh.exe", "-NoLogo" }
config.font = wezterm.font "CaskaydiaCove NFM"
config.font_size = 12.0
wezterm.on("gui-startup", function(cmd)
  local tab, pane, window = mux.spawn_window(cmd or {})
  local right_pane = pane:split { direction = "Right", size = 0.5 }
  window:gui_window():maximize()
  right_pane:activate()
end)
return config
"@
Set-Content -Path $weztermConfigFile -Value $weztermConfig -Encoding UTF8
Write-Host "Config written to $weztermConfigFile"
```

### Git over SSH

Git uses the Windows OpenSSH client and the Windows `ssh-agent` service. The agent
stores added keys in the registry (encrypted per user with DPAPI), so they survive
reboots: you type the passphrase once at `ssh-add` and never again on this machine.

Git for Windows bundles its own (MSYS) `ssh.exe`, which only knows how to reach an
agent through a Unix socket (`SSH_AUTH_SOCK`). The Windows agent listens on the named
pipe `\\.\pipe\openssh-ssh-agent`, which only Windows OpenSSH can talk to, so git must
be pointed at it with `core.sshCommand`. Changing PATH doesn't help: git prepends its
own `usr\bin` internally, so it always finds the bundled `ssh.exe` first.

In an **admin** PowerShell, enable and start the agent service:

```shell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

In a normal PowerShell:

```shell
# ============================================================================
#                                Git over SSH
# ============================================================================
$OpenSsh = "C:\Windows\System32\OpenSSH"
# One key per machine, named after the computer: a PC called MY-PC gets
# id_ed25519_my_pc, and the GitHub key title is the computer name
$KeyName = "id_ed25519_" + $env:COMPUTERNAME.ToLower().Replace("-", "_")
$KeyPath = "$HOME\.ssh\$KeyName"
# Generate the key (set a passphrase when prompted)
if (!(Test-Path $KeyPath)) {
    & "$OpenSsh\ssh-keygen.exe" -t ed25519 -C "$env:USERNAME@$env:COMPUTERNAME" -f $KeyPath
}
# Add it to the agent (asks for the passphrase once, persists across reboots)
& "$OpenSsh\ssh-add.exe" $KeyPath
& "$OpenSsh\ssh-add.exe" -l
# Make git use Windows OpenSSH, which can reach the agent
git config --global core.sshCommand C:/Windows/System32/OpenSSH/ssh.exe
# Install ssh/config from this repo (github.com -> this machine's key, plus
# global defaults), backing up any existing config to config.bak
$SshConfig = "$HOME\.ssh\config"
if (Test-Path $SshConfig) { Copy-Item $SshConfig "$SshConfig.bak" -Force }
(Get-Content .\ssh\config -Raw).Replace("__KEY_NAME__", $KeyName) |
    Set-Content $SshConfig -NoNewline
# Check: core.sshCommand set, agent running with the key loaded
git config --global --get core.sshCommand
Get-Service ssh-agent
```

The public key is uploaded to GitHub in the GitHub CLI step below.

Continue installing tools:

```shell
# ============================================================================
#                                  GitHub CLI
# ============================================================================
scoop install main/gh
# Do this after the "Git over SSH" step; choose SSH as the git protocol
gh auth login
# Git identity, derived from the GitHub account (only if not set yet): the profile
# name (or login), and the public profile email or else GitHub's noreply address
$GhUser = gh api user | ConvertFrom-Json
if (-not (git config --global user.name)) {
    git config --global user.name ($GhUser.name ? $GhUser.name : $GhUser.login)
}
if (-not (git config --global user.email)) {
    $NoReply = "$($GhUser.id)+$($GhUser.login)@users.noreply.github.com"
    git config --global user.email ($GhUser.email ? $GhUser.email : $NoReply)
}
# Upload this machine's key (skip if gh auth login already uploaded it)
$KeyName = "id_ed25519_" + $env:COMPUTERNAME.ToLower().Replace("-", "_")
gh ssh-key add "$HOME\.ssh\$KeyName.pub" --title $env:COMPUTERNAME
# Verify: should print "Hi <username>! You've successfully authenticated..."
# (exit code 1 is normal, GitHub has no shell access)
ssh -T git@github.com
# Make gh clone over SSH (gh auth login sets this if you picked SSH)
gh config set git_protocol ssh
# Switch an existing HTTPS clone to SSH, then test with git fetch / git push:
#   git remote set-url origin git@github.com:<user>/<repo>.git
# ============================================================================
#                                 Python & UV
# ============================================================================
# we don't install python separately, we let uv handle it
#scoop install main/python
scoop install main/uv
uv python install 3.11 
uv python install 3.12
uv python install 3.13
uv python install 3.14 --default
uv tool install invoke --with python-dotenv
# ============================================================================
#                              Node.js & npm (via fnm)
# ============================================================================
# fnm (installed with the profile above) switches to a project's Node version on cd
# when it has a .nvmrc or .node-version file. No nvm needed: the original doesn't
# run on Windows, and fnm reads the same .nvmrc files (`fnm use` where docs say
# `nvm use`).
fnm install --lts
fnm use lts-latest
fnm default lts-latest
# To update later: fnm install --lts; fnm default lts-latest
# ============================================================================
#                                CLI Utilities
# ============================================================================
scoop install main/fd
scoop install main/jq
scoop install main/ripgrep
scoop install main/curl
# Go: needed to build Herdr's Branch PR helper (see herdr/README.md)
scoop install main/go
# Claude Code, native installer (installs to ~\.local\bin\claude.exe, which the
# Prerequisites put on PATH; updates itself in the background)
Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
claude --version
# Then install the Claude Code config: see claude/README.md
# ============================================================================
#                           Containerization Tools
# ============================================================================
# We currently don't need Docker CLI, we're using WSL shims
#scoop install main/docker
#scoop install main/docker-compose
scoop install main/kubectl
scoop install main/helm
scoop install main/kind
scoop bucket add tilt-dev https://github.com/tilt-dev/scoop-bucket
scoop install tilt-dev/tilt
```

Now the hard part, Docker in WSL, without anything on the Windows side:

```shell
# ============================================================================
#                               WSL Installation
# ============================================================================
wsl --install -d Ubuntu-24.04
wsl --set-default Ubuntu-24.04
wsl
```

In WSL:

```shell
# ============================================================================
#                                Enable Systemd
# ============================================================================
# Enable systemd
echo -e "[boot]\nsystemd=true" | sudo tee /etc/wsl.conf
# Exit and restart WSL
exit
```

In Powershell:

```shell
# ============================================================================
#                                 WSL Restart
# ============================================================================
wsl --shutdown
wsl
```

In WSL:

```shell
# ============================================================================
#                               Docker Installation
# ============================================================================
curl -fsSL https://get.docker.com | sh
sudo groupadd docker
sudo gpasswd --add ${USER} docker
sudo systemctl enable --now docker
# ============================================================================
#                              Docker Configuration
# ============================================================================
DAEMON_JSON="/etc/docker/daemon.json"
# Configure daemon.json for TCP + unix socket
if [ ! -f "$DAEMON_JSON" ] || ! grep -q "2375" "$DAEMON_JSON"; then
    echo "Configuring $DAEMON_JSON..."
    sudo tee "$DAEMON_JSON" > /dev/null <<'EOF'
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://127.0.0.1:2375"]
}
EOF
    echo "✅ daemon.json updated"
else
    echo "⚠️  daemon.json already configured, skipping."
fi
# Ensure systemd override exists (needed when "hosts" is set in daemon.json)
# Otherwise dockerd conflicts with the default socket flag in the service unit
OVERRIDE_DIR="/etc/systemd/system/docker.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"
if [ ! -f "$OVERRIDE_FILE" ]; then
    echo "Adding systemd override to strip default -H flag..."
    sudo mkdir -p "$OVERRIDE_DIR"
    sudo tee "$OVERRIDE_FILE" > /dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
EOF
    echo "✅ systemd override created"
else
    echo "⚠️  systemd override already present, skipping."
fi
# ============================================================================
#                                Docker Restart
# ============================================================================
sudo systemctl daemon-reload
sudo systemctl restart docker
echo "✅ Docker restarted"
# ============================================================================
#                                 Verification
# ============================================================================
echo "Docker socket listeners:"
sudo ss -tlnp | grep dockerd || true
docker version --format "Client: {{.Client.Version}}  Server: {{.Server.Version}}"
```

In Powershell:

```shell
# ============================================================================
#                             Docker WSL2 bridge
# ============================================================================
$WSL_DISTRO = "Ubuntu-24.04"
$profileContent = @"

# Docker WSL2 bridge
`$WSL_DISTRO = "$WSL_DISTRO"
function docker { wsl -d `$WSL_DISTRO docker `@Args }
function docker-compose { wsl -d `$WSL_DISTRO docker compose `@Args }
"@

# Avoid duplicate entries
if (!(Select-String -Path $PROFILE -Pattern "Docker WSL2 bridge" -Quiet)) {
    Add-Content -Path $PROFILE -Value $profileContent
    Write-Host "✅ PowerShell profile updated: $PROFILE"
} else {
    Write-Host "⚠️  Docker bridge already present in profile, skipping."
}
```

## Claude Code

Global `CLAUDE.md`, `settings.json` (PowerShell 7 as Claude's shell, status line) and the status
line script: see [claude/README.md](claude/README.md). How Claude's shell relates to your
profile and the Unix tools: [docs/claude-windows-tools.md](docs/claude-windows-tools.md).

## Herdr

The Herdr desktop app (terminals and agents), its settings, and the Estro layout with munza's
mods and a GitHub issues panel, pinned to security-reviewed commits: see
[herdr/README.md](herdr/README.md). Needs `pwsh`, the Nerd Fonts, `gh` and `go` from above.
