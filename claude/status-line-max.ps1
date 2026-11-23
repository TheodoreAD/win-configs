# Claude Code status line, maximal version (PowerShell 7, needs a Nerd Font).
# Claude Code pipes session info as JSON on stdin; whatever this prints becomes the status line.
# One line, in this order:
#   folder + branch + git changes (dirty files, uncommitted lines +/-) (+node, +python venv) |
#   context, cache, 5h + 7d limits left with reset (muted) | cost, total/api time | model
# No session/tab name: Herdr already shows it on the tab, and parallel sessions use worktrees
# (distinct folder + branch).
# Configured in ~/.claude/settings.json under "statusLine".

[Console]::InputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$raw = [Console]::In.ReadToEnd()
$j = $raw | ConvertFrom-Json

# ---------------------------------------------------------------- helpers

$e = [char]27
function C([string]$text, [int]$color) { "$e[38;5;${color}m$text$e[0m" }
function G([int]$codepoint) { [char]::ConvertFromUtf32($codepoint) }

# muted green -> yellow -> red by percentage used
function Heat([double]$pct) { if ($pct -ge 80) { 167 } elseif ($pct -ge 50) { 179 } else { 108 } }

# seconds -> 3d4h / 2h14m / 47m / <1m
function Span([double]$s) {
    if ($s -lt 60) { return '<1m' }
    $t = [TimeSpan]::FromSeconds($s)
    if ($t.TotalDays -ge 1) { return '{0}d{1}h' -f [int][Math]::Floor($t.TotalDays), $t.Hours }
    if ($t.TotalHours -ge 1) { return '{0}h{1:D2}m' -f [int][Math]::Floor($t.TotalHours), $t.Minutes }
    '{0}m' -f $t.Minutes
}

$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
function Until([long]$epoch) { Span ([Math]::Max(0, $epoch - $now)) }

# Nerd Font glyphs, only where the value alone would be ambiguous
$I = @{
    think   = G 0xF0EB   # lightbulb
    fast    = G 0xF0E7   # bolt
    branch  = G 0xE725
    node    = G 0xF0399
    python  = G 0xE73C
    five    = G 0xF252   # hourglass
    week    = G 0xF073   # calendar
    cache   = G 0xF1C0   # database
    time    = G 0xF051B  # timer
    no      = G 0xF00D   # x
}
$sep = C ' │ ' 238

# ---------------------------------------------------------------- where + git changes

$line1 = @()


$where = @()
$dirty = 0
$dir = $j.workspace.current_dir ?? $j.cwd
if ($dir) {
    $where += C (Split-Path $dir -Leaf) 75

    # one git call: branch, ahead/behind, changed files
    $st = git -C $dir status --porcelain=v2 --branch 2>$null
    if ($LASTEXITCODE -eq 0 -and $st) {
        $head  = ($st | Where-Object { $_ -like '# branch.head *' }) -replace '^# branch\.head '
        $ab    = ($st | Where-Object { $_ -like '# branch.ab *' }) -replace '^# branch\.ab '
        $dirty = @($st | Where-Object { $_ -notlike '#*' }).Count
        $txt = "$($I.branch) $head"
        if ($ab -match '\+(\d+) -(\d+)') {
            $sync = ''
            if ([int]$Matches[1]) { $sync += "↑$($Matches[1])" }
            if ([int]$Matches[2]) { $sync += "↓$($Matches[2])" }
            if ($sync) { $txt += " $sync" }
        }
        $branch = C $txt ($dirty ? 214 : 114)

        # changes, one space after the branch: uncommitted files, then lines vs HEAD (tracked only)
        if ($dirty) {
            $branch += ' ' + (C "●$dirty" 214)
            $stat = git -C $dir diff --shortstat HEAD 2>$null
            $add = $stat -match '(\d+) insertion' ? [int]$Matches[1] : 0
            $del = $stat -match '(\d+) deletion' ? [int]$Matches[1] : 0
            if ($add -or $del) { $branch += ' ' + (C "+$add" 114) + ' ' + (C "−$del" 203) }
        }
        $where += $branch
    }

    # node version, only in folders that look like node projects
    if ((Test-Path "$dir\package.json") -or (Test-Path "$dir\.nvmrc") -or (Test-Path "$dir\.node-version")) {
        $nv = node --version 2>$null
        if ($nv) { $where += C "$($I.node) $($nv.TrimStart('v'))" 71 }
    }

    # python venv: the activated one, else the folder's .venv; version from pyvenv.cfg (no process)
    $venv = $env:VIRTUAL_ENV ?? ((Test-Path "$dir\.venv\pyvenv.cfg") ? "$dir\.venv" : $null)
    if ($venv -and (Test-Path "$venv\pyvenv.cfg")) {
        $cfg = Get-Content "$venv\pyvenv.cfg" -ErrorAction SilentlyContinue
        $pv = ($cfg | Where-Object { $_ -match '^\s*(version_info|version)\s*=' } | Select-Object -First 1) -replace '^[^=]+=\s*'
        $pv = ($pv -split '\.')[0..1] -join '.'   # 3.13.1 -> 3.13
        $name = Split-Path $venv -Leaf
        $txt = "$($I.python) $pv"
        if ($name -ne '.venv') { $txt += " ($name)" }   # only name unusual venvs
        $where += C $txt 179
    }
}
if ($where) { $line1 += $where -join ' ' }
$c = $j.cost

# ---------------------------------------------------------------- line 2: budgets | cost | time | model

$line2 = @()

# context used: a pie that fills in eighths (md-circle_slice_1..8)
$ctx = $null
$pct = $j.context_window.used_percentage
if ($null -ne $pct) {
    $slice = [Math]::Clamp([int][Math]::Ceiling($pct / 12.5), 1, 8)
    $ctx = C "$(G (0xF0A9E + $slice - 1)) $([int]$pct)%" (Heat $pct)
}

# usage limits (Pro/Max only): what's left, coloured by what's used
$limits = @()
foreach ($k in @(@{ key = 'five_hour'; icon = $I.five }, @{ key = 'seven_day'; icon = $I.week })) {
    $r = $j.rate_limits.($k.key)
    if ($r) {
        $used = [int]$r.used_percentage
        $limits += (C "$($k.icon) $(100 - $used)%" (Heat $used)) + (C " $(Until $r.resets_at)" 241)
    }
}
# prompt cache: time until it expires, or cold
$cache = $null
$pc = $j.prompt_cache
if ($pc) {
    $cache = $pc.warm `
        ? (C "$($I.cache) $($pc.expires_at ? (Until $pc.expires_at) : 'warm')" 109) `
        : (C "$($I.cache)$($I.no) cold" 167)
}

# context, limits and cache form one segment, without dividers between them
$budget = @($ctx) + @($cache) + $limits | Where-Object { $_ }
if ($budget) { $line2 += $budget -join ' ' }

# cost, then total / api time in two muted tones: one segment
$spend = @()
if ($null -ne $c.total_cost_usd) { $spend += C ('${0:N2}' -f $c.total_cost_usd) 250 }
if ($c.total_duration_ms) {
    $t = C "$($I.time) $(Span ($c.total_duration_ms / 1000))" 248
    if ($c.total_api_duration_ms) { $t += (C '/' 240) + (C (Span ($c.total_api_duration_ms / 1000)) 103) }
    $spend += $t
}
if ($spend) { $line2 += $spend -join ' ' }

# model, effort, thinking, fast — last
$model = @(C ($j.model.display_name ?? 'Claude') 141)
$lvl = $j.effort.level
if ($lvl) { $model += C (@{ low = 'lo'; medium = 'med'; high = 'hi'; xhigh = 'xhi'; max = 'max' }[$lvl] ?? $lvl) 245 }
if ($j.thinking.enabled) { $model += C $I.think 221 }
if ($j.fast_mode)        { $model += C $I.fast 220 }
$line2 += $model -join ' '

(@($line1) + @($line2)) -join $sep
