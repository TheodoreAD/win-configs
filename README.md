# Windows Configs

Configurations for all manner of Windows system and software

## Development tools

```shell
#Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
scoop install main/git

scoop bucket add nerd-fonts
# Proportional Nerd Font
scoop install nerd-fonts/CascadiaCode-NF
# Monospaced Nerd Font (recommended for terminals)
scoop install nerd-fonts/CascadiaCode-NF-Mono

scoop install main/oh-my-posh

Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name Terminal-Icons -Repository PSGallery -Scope CurrentUser -Force


# Create profile file if it doesn't exist
if (!(Test-Path -Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force
}

# Lines to add
$additions = @'

# Oh My Posh
# other themes: atomic powerlevel10k_modern
oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH\if_tea.omp.json" | Invoke-Expression

# Terminal Icons
Import-Module Terminal-Icons
'@

# Only add if not already present
if (!(Select-String -Path $PROFILE -Pattern "oh-my-posh" -Quiet)) {
    Add-Content -Path $PROFILE -Value $additions
    Write-Host "Profile updated successfully." -ForegroundColor Green
} else {
    Write-Host "Oh My Posh already configured in profile. Skipping." -ForegroundColor Yellow
}

scoop bucket add extras
scoop install extras/wezterm
reg import "C:\Users\Memphis-Mobile-PC\scoop\apps\wezterm\current\install-context.reg"

# ============================================================================
# TODO: make this work
# ============================================================================
scoop install versions/putty-cac

$SshAgentProfileBlock = @'

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
        Where-Object { $_.Extension -notin '.pub','.bak','.ppk' -and $_.Name -notmatch 'known_hosts|config|authorized_keys' } |
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

'@

$ProfileContent = [string](Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue)
$ProfileContent = $ProfileContent -replace "(?s)\r?\n# SSH Agent.*$", ""
Set-Content $PROFILE $ProfileContent.TrimEnd()
Add-Content $PROFILE $SshAgentProfileBlock
Write-Host "SSH agent block updated in $PROFILE"

& $GitSshAdd -l
# ============================================================================

scoop install main/gh
# TODO: create SSH key, update in .ssh/config, ensure password isn't required every time etc
# only do this after you have the SSH key
gh auth login

# Ensure .local\bin is in the Path
$binPath = "$env:USERPROFILE\.local\bin"
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$binPath", "User")
    Write-Host "Added $binPath to user PATH. Restart your shell."
} else {
    Write-Host "Already in PATH."
}
scoop install main/python
pip install uv
uv python install 3.11 3.12 3.13
uv tool install invoke

scoop install main/fd
scoop install main/jq
scoop install main/ripgrep
# Currently not needed, we're using wsl shims
#scoop install main/docker
#scoop install main/docker-compose
scoop install main/kubectl
scoop install main/helm
scoop install main/kind
scoop bucket add tilt-dev https://github.com/tilt-dev/scoop-bucket
scoop install tilt-dev/tilt

wsl --install -d Ubuntu-24.04
wsl --set-default Ubuntu-24.04
wsl
```

In WSL:

```shell
# Enable systemd
echo -e "[boot]\nsystemd=true" | sudo tee /etc/wsl.conf
# Exit and restart WSL
exit
```

In Powershell:

```shell
wsl --shutdown
wsl
```

In WSL:

```shell
# Install Docker Engine
curl -fsSL https://get.docker.com | sh
# add the docker group if it doesn't already exist
sudo groupadd docker
# add docker group to the user
sudo gpasswd --add ${USER} docker

sudo systemctl enable --now docker

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
# Ensure systemd override exists (needed when 'hosts' is set in daemon.json)
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

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart docker
echo "✅ Docker restarted"

# Verify
echo ""
echo "Docker socket listeners:"
sudo ss -tlnp | grep dockerd || true
docker version --format 'Client: {{.Client.Version}}  Server: {{.Server.Version}}'
```

In Powershell:

```shell
$WSL_DISTRO = "Ubuntu-24.04"

# Ensure profile file exists
if (!(Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

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
