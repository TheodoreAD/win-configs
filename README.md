# Windows Configs

Configurations for all manner of Windows system and software

## Development tools

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
# Ensure .local\bin is in the Path, at the top
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
if (!(Test-Path $PROFILE)) { New-Item -ItemType File -Force -Path $PROFILE | Out-Null }
param([string]$SourceFile = ".\scripts\profile.ps1")
$blockContent = Get-Content $SourceFile -Raw
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

```

Run the rest after testing `l`, `d`, and `where` work.

```shell
# ============================================================================
#                                   Fonts
# ============================================================================
scoop bucket add nerd-fonts
# Proportional Nerd Font (for editors)
scoop install nerd-fonts/CascadiaCode-NF
# Monospaced Nerd Font (for terminals)
scoop install nerd-fonts/CascadiaCode-NF-Mono
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
$additions = @"

# Oh My Posh
oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH\if_tea.omp.json" | Invoke-Expression

# Terminal Icons
Import-Module Terminal-Icons

"@
if (!(Select-String -Path $PROFILE -Pattern "oh-my-posh" -Quiet)) {
    Add-Content -Path $PROFILE -Value $additions
    Write-Host "Profile updated successfully." -ForegroundColor Green
} else {
    Write-Host "Oh My Posh already configured in profile. Skipping." -ForegroundColor Yellow
}
# ============================================================================
#                                   Wezterm
# ============================================================================
scoop bucket add extras
scoop install extras/wezterm
reg import "C:\Users\Memphis-Mobile-PC\scoop\apps\wezterm\current\install-context.reg"
$weztermConfigDir = "$env:USERPROFILE\.config\wezterm"
$weztermConfigFile = "$weztermConfigDir\wezterm.lua"
New-Item -ItemType Directory -Force -Path $weztermConfigDir | Out-Null
$weztermConfig = @"
local wezterm = require "wezterm"
local mux = wezterm.mux
local config = wezterm.config_builder()
config.default_prog = { "powershell.exe", "-NoLogo" }
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
#                                CLI Utilities
# ============================================================================
scoop install main/fd
scoop install main/jq
scoop install main/ripgrep
scoop install main/curl
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
