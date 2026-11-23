# Claude Code configuration

Global Claude Code setup for this machine, set up on 2026-11-22. Copies of the files in
`~/.claude/`:

- **`CLAUDE.md`** — global instructions for every project (shell, tool usage, scripting,
  naming, Markdown, no memory)
- **`settings.json`** — global settings; `__HOME__` is replaced with your home folder on install
- **`status-line-max.ps1`** — the status line script (PowerShell 7, needs a Nerd Font)

See [../docs/claude-windows-tools.md](../docs/claude-windows-tools.md) for how Claude Code's
shell relates to your PowerShell profile and the Unix tools.

## Install

Needs PowerShell 7 (`scoop install pwsh`), git, and a Nerd Font in the terminal (see the main
README). Run from this repo's root:

```powershell
# ============================================================================
#                                 Claude Code
# ============================================================================
$ClaudeDir = "$HOME\.claude"
New-Item -ItemType Directory -Force $ClaudeDir | Out-Null
foreach ($f in 'CLAUDE.md', 'settings.json', 'status-line-max.ps1') {
    if (Test-Path "$ClaudeDir\$f") { Copy-Item "$ClaudeDir\$f" "$ClaudeDir\$f.bak" -Force }
}
Copy-Item .\claude\CLAUDE.md "$ClaudeDir\CLAUDE.md"
Copy-Item .\claude\status-line-max.ps1 "$ClaudeDir\status-line-max.ps1"
(Get-Content .\claude\settings.json -Raw).Replace("__HOME__", $HOME.Replace("\", "/")) |
    Set-Content "$ClaudeDir\settings.json" -NoNewline
```

This replaces existing files (backed up as `*.bak`). If the machine already has its own
`settings.json`, merge the keys by hand instead.

Then quit Claude Code completely and start it again from a PowerShell 7 terminal. Check:

- `! $PSVersionTable.PSVersion` should print 7.x (the `!` prefix now runs in PowerShell)
- ask Claude to run any PowerShell command: its tool should report PowerShell 7
- the status line appears at the bottom

## Settings explained

- **`"defaultShell": "powershell"`** — `!` commands run in PowerShell instead of Git Bash.
- **`"env": { "CLAUDE_CODE_USE_POWERSHELL_TOOL": "1" }`** — turns on Claude's PowerShell tool
  explicitly (it was already on by default; this guards against the default changing).
- **PowerShell 7 vs 5.1** — there's no setting for this. Claude Code uses `pwsh.exe` when it can
  find it and falls back to `powershell.exe`. It looks at startup, so after installing `pwsh`,
  restart Claude Code from a fresh terminal.
- **`statusLine`** — runs the script with `pwsh -NoProfile -NoLogo`, which skips your profile
  (about 0.16 s to start instead of 0.75 s).
- **`effortLevel`, `tui`, `cleanupPeriodDays`, `permissions`, `extraKnownMarketplaces`** —
  personal preferences, unrelated to the Windows setup.

## Status line

One line, in this order:

```text
win-configs  main ↑1 ●4 +81 −1 │ ◔ 24%  59m  95% 3h14m  99% 5h54m │ $10.63 󰔛 1h33m/20m │ Opus 5.5 med 
```

- **Folder, branch, changes** — folder name (blue); branch icon + branch (orange when dirty,
  green when clean) with `↑`/`↓` commits ahead/behind; `●N` files differing from HEAD (modified,
  staged or untracked); `+a −d` lines changed in tracked files vs HEAD (`git diff --shortstat
  HEAD`, untracked files aren't counted). The changes part disappears in a clean repo.
- **Node / Python** — Node version only in folders with `package.json`, `.nvmrc` or
  `.node-version`; Python version when the folder has a `.venv` or Claude was started in an
  activated venv (read from `pyvenv.cfg`, no process started; named in brackets when the venv
  isn't called `.venv`).
- **Budgets (muted colors)** — context used as a pie that fills in eighths (green, ochre from
  50%, brick red from 80%); prompt cache time left (or `× cold`); 5-hour and 7-day limits as
  **percent left** plus time until reset (color still follows percent used).
- **Cost and time** — session cost, then total/API time in two muted tones.
- **Model** — model, effort (`lo`/`med`/`hi`/`xhi`/`max`), lightbulb while thinking is on, bolt
  in fast mode.

Design decisions made while building it (2026-11-22):

- **Glyphs only where a value would be ambiguous without one** (branch, Node, Python, cache,
  limits, timer). No glyph for the model, folder, cost or effort. The context bar became a pie
  glyph (a brain glyph was unclear).
- **No session/tab name** — Herdr shows it on the tab; parallel sessions should use git worktrees
  (always a distinct folder and branch) or distinctly named clones, so folder + branch already
  tells panes apart.
- **No cost per hour, no cache hit rate** — not useful.
- **Single spaces only**, one space between a glyph and its value, dividers only between groups.
- **Git changes are the repo's current state**, not Claude's session line counts (which include
  edits outside the repo).
- **UTF-8 output** — the script's first line sets console input/output to UTF-8. Without it,
  PowerShell writes in the console's old code page and `│` and the icons arrive as `�`.
- Every glyph was checked against CaskaydiaCove Nerd Font Mono's character map with
  `fontTools` before use. Speed: about 0.4 s per refresh, mostly `pwsh` startup plus two `git`
  calls.

To see every field Claude Code sends the script, temporarily add this after the
`ReadToEnd()` line and look at the file:

```powershell
$raw | Set-Content "$HOME\.claude\status-line-input.json"
```

Ideas from community status lines that weren't used: powerline-style blocks, a context bar,
lines added/removed per session, cost per hour, session name, Herdr space/tab labels
(`herdr.space`, `herdr.tab`). Sources: [Claude Code status line docs](https://code.claude.com/docs/en/statusline),
[ccstatusline](https://github.com/sirmalloc/ccstatusline),
[claude-powerline](https://unpkg.com/@owloops/claude-powerline@1.26.0/README.md),
[cship](https://docs.rs/crate/cship/1.7.1).

## Not set up

- **`/fewer-permission-prompts`** — scans past sessions for read-only commands you keep
  approving and adds them to an allowlist. Useful outside auto mode.
- **Hooks** — deliberately not used (extra complexity); project rules live in each repo's
  `CLAUDE.md`.
