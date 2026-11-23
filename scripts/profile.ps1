# ============================================================================
# Power User Profile
# ============================================================================
# Oh My Posh
oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH\if_tea.omp.json" | Invoke-Expression

# Terminal Icons
Import-Module Terminal-Icons

# PowerShell's built-in aliases (ls, cat, rm, where, sort, ...) are kept as-is.
# GNU tools are still available explicitly: ls.exe, cat.exe, rm.exe, ...

# Aliases
# Improved ls
function l { ls.exe -l --almost-all --human-readable --group-directories-first --no-group --color=auto --time-style=long-iso $args }
# Improved dir
function d {
    $esc = [char]27
    $reset = "${esc}[0m"
    function format-size($bytes) {
        if ($bytes -ge 1GB) { "{0,6:N1}G" -f ($bytes / 1GB) }
        elseif ($bytes -ge 1MB) { "{0,6:N1}M" -f ($bytes / 1MB) }
        elseif ($bytes -ge 1KB) { "{0,6:N1}K" -f ($bytes / 1KB) }
        else { "{0,6}B" -f $bytes }
    }
    Get-ChildItem $args | ForEach-Object {
        $iconLine = ($_ | Format-TerminalIcons | Out-String).Trim()
        $size = if ($_.PSIsContainer) { "  <DIR>" } else { format-size $_.Length }
        [PSCustomObject]@{
            Mode     = $_.Mode
            Modified = $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm")
            Size     = $size
            Name     = "$iconLine$reset"
        }
    } | Format-Table Mode, Modified, Size, Name -HideTableHeaders |
        Out-String -Stream |
        Where-Object { $_ -match '\S' }
}

# Docker WSL2 bridge (interactive shells only; to be replaced by DOCKER_HOST,
# see "WSL and Docker" in the win-configs README)
$WSL_DISTRO = "Ubuntu-24.04"
function docker { wsl -d $WSL_DISTRO docker @Args }
function docker-compose { wsl -d $WSL_DISTRO docker compose @Args }

# fnm (Fast Node Manager)
fnm env --use-on-cd --shell powershell | Out-String | Invoke-Expression
# ============================================================================
