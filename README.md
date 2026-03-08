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

This is still under construction, skip it.

```shell
TODO: make ssh password persist across restarts, or at least across terminal sessions.
# ============================================================================
#                                  SSH Agent
# ============================================================================
scoop install versions/putty-cac
$SshAgentProfileBlock = @"

# SSH Agent via ssh-pageant + Pageant bridge
$GitBin     = Join-Path (scoop prefix git) "usr\bin"
$SshPageant = Join-Path $GitBin "ssh-pageant.exe"
$GitSshAdd  = Join-Path $GitBin "ssh-add.exe"
$PageantCmd = Get-Command pageant -ErrorAction SilentlyContinue
$PageantExe = if ($_PageantCmd) { $_PageantCmd.Source } else { $null }
#$SshPageantSock = "$env:TEMP\ssh-pageant.sock"
$SshPageantSock = "/tmp/ssh-pageant.sock"
if ($PageantExe -and -not (Get-Process pageant -ErrorAction SilentlyContinue)) {
    $SshKey = Get-ChildItem "$env:USERPROFILE\.ssh" -File |
        Where-Object { $_.Extension -notin ".pub",".bak",".ppk" -and $_.Name -notmatch "known_hosts|config|authorized_keys" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    $PpkKey = [System.IO.Path]::ChangeExtension($SshKey, ".ppk")
    $KeyArg = if (Test-Path $PpkKey) { $PpkKey } else { $SshKey }
    if (-not (Get-Process ssh-pageant -ErrorAction SilentlyContinue)) {
        $_Bash = Join-Path (scoop prefix git) "bin\bash.exe"
        & $_Bash -c "rm -f $SshPageantSock && ssh-pageant -a $SshPageantSock -q &"
        Start-Sleep -Milliseconds 600
    }
}
if (-not (Get-Process ssh-pageant -ErrorAction SilentlyContinue)) {
    & $SshPageant -a $SshPageantSock -r -q 2>&1 | Out-Null
}
$env:SSH_AUTH_SOCK = $SshPageantSock 

"@
$ProfileContent = [string](Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue)
$ProfileContent = $ProfileContent -replace "(?s)\r?\n# SSH Agent.*$", ""
Set-Content $PROFILE $ProfileContent.TrimEnd()
Add-Content $PROFILE $SshAgentProfileBlock
Write-Host "SSH agent block updated in $PROFILE"

& $GitSshAdd -l
```

Continue installing tools:

```shell
# ============================================================================
#                                  GitHub CLI
# ============================================================================
scoop install main/gh
# TODO: create SSH key, update in .ssh/config, ensure password isn't required every time etc
# WARNINGL: only do this after you have the SSH key
gh auth login
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
