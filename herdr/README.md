# Herdr desktop app

Setup for the Herdr desktop app (`herdr-app`), first set up on 2026-11-22/23. For connecting
another machine (and WSL) to Herdr over SSH, see the `herdr-remote` skill in
[../skills/](../skills/README.md). Herdr keeps its whole
configuration as plain files in `~/.config/herdr-app/` and redraws itself within about a second
of any change, so everything here is "copy a file into that folder".

Files in this folder:

- **`settings.json`** — copy of `~/.config/herdr-app/settings.json` (font, zoom, sounds)
- **`layouts/estro.json`** — munza's Estro layout with the Linear issues panel swapped for
  jankeesvw's GitHub issues mod (4 lines changed, see below)
- **`layouts/estro-issues.svg`** — icon for the Issues button (Branch Issue's `issue.svg`)

## Two products, don't mix them up

- **Herdr desktop app** — `herdr-app.exe` (the window) plus `herdr-core.exe` / `hc.exe` (runs the
  terminals and agents, which keep running when the window closes). Installed per user under
  `%LOCALAPPDATA%\Programs\herdr-app` and `%LOCALAPPDATA%\Programs\herdr-core`; it has no entry
  in Windows' installed apps list. Extensions are **mods** (JavaScript, in `mods/`) and
  **layouts** (JSON, in `layouts/`).
- **Herdr TUI** — the original terminal app (`herdr` CLI, [herdr.dev/tui](https://herdr.dev/tui/)).
  Its extensions are **plugins** (`herdr-plugin.toml`, `herdr plugin install`), which do
  **not** work in the desktop app. Not installed on this machine.

## Install

1. Install the app with the one-liner from [herdr.dev/download](https://herdr.dev/download/).
   It also sets up herdr-core and adds a Start menu entry; after that the app updates itself.

   ```powershell
   powershell -c "irm https://releases.herdr.dev/app/install.ps1 | iex"
   ```

2. Start it once so it creates `~/.config/herdr-app/`.
3. Read `~/.config/herdr-app/AGENTS.md`. It's the full manual for agents working on the config
   (layouts, `keys.json`, `settings.json`, mods, the `herdr-app` CLI). Ask Claude to read it first
   whenever it changes Herdr. Don't edit `AGENTS.md`, the `.d.ts` files or `frame/`: the app
   rewrites them.

Useful CLI, all from any terminal:

- **`herdr-app status`** — errors and current state; run after every config change
- **`herdr-app check <mod folder>`** — validates a mod; a mod isn't done until this passes
- **`herdr-app shot <file.png>`** — screenshot of the window
- **`herdr-app commands`** / **`herdr-app do <cmd> <json>`** — list and run app commands
- **`Ctrl+Alt+Shift+Esc`** in the app — emergency reset: sets the shown layout and `keys.json`
  aside and restores the default layout

## Prerequisites from the main README

- **PowerShell 7** (`scoop install pwsh`) — Herdr opens new terminals in `pwsh` when it's
  installed, otherwise in Windows PowerShell 5.1. Existing panes keep their shell; new tabs pick
  up `pwsh` (restart Herdr if they don't).
- **CaskaydiaCove Nerd Font Mono** (`scoop install nerd-fonts/CascadiaCode-NF-Mono`) — the Mono
  variant keeps icons one cell wide in a terminal. See the fonts section in the main README for
  why the font packages are held.
- **`git` and `gh` logged in** — used by the sidebar, changes, PR and issues mods.
- **Go** (`scoop install go`) — only for building Branch PR's helper. Go lives in
  `~\scoop\apps\go\current`; `go install` puts programs in `~\go\bin` (scoop adds it to PATH),
  modules in `~\go\pkg\mod`, build cache in `%LOCALAPPDATA%\go-build`. `scoop uninstall go`
  leaves the last three behind.

## Settings

Copy the settings file:

```powershell
Copy-Item .\herdr\settings.json "$HOME\.config\herdr-app\settings.json"
herdr-app status
```

What's in it and why:

- **`"font": "CaskaydiaCove Nerd Font Mono"`, `"font_weight": 300`** — Cascadia shapes with
  Nerd Font icons drawn by the font itself (Oh My Posh prompt, Terminal-Icons, the Claude status
  line). Weight 300 uses the font's real Light face. Herdr falls back to its bundled JetBrains
  Mono if the font name is wrong, and borrows glyphs the font lacks (e.g. `↻`) from other fonts.
- **`"minimum_contrast": 1`** — leaves program colors as they are. Raise to `1.6` if some
  program's colors are unreadable on the theme.
- **`"font_ligatures": false`**, `terminal_line_height` / `terminal_cell_width` `1` — defaults.
- **`"telemetry": false`** — Herdr otherwise sends anonymous daily usage counts (version, OS,
  which agents, layouts, shipped mods and commands were used; never terminal content or names)
  and deletes what wasn't sent when turned off. Settings → Privacy shows each report.
  `DO_NOT_TRACK=1` or `HERDR_TELEMETRY=0` turns it off for a single run.

Terminal environment Herdr sets for every pane (nothing to configure):
`TERM=xterm-256color`, `COLORTERM=truecolor`, `TERM_PROGRAM=ghostty`, so programs use 24-bit
color. Test with:

```powershell
0..255 | ForEach-Object { Write-Host -NoNewline "$([char]27)[48;5;${_}m  " }; "$([char]27)[0m"
```

Windows notes:

- **Ctrl+Alt is AltGr** on Windows, so avoid Ctrl+Alt key bindings if you type characters with
  AltGr.
- **Herdr's background server keeps its PATH.** Restarting the window doesn't restart
  `herdr-core.exe serve`, so new terminals still get the PATH from when the server started.
  Tools that go through `~\scoop\shims` work anyway (the shims folder was already on PATH).
  For a genuinely new PATH entry: quit Herdr, end `herdr-core.exe` in Task Manager (this ends
  every running terminal and agent), start Herdr again.

## Themes

Built in: `graphite`, `ink`, `moss` (dark), `paper` (light). Switch in Settings → Look, or
`herdr-app do app.theme --name <name>`. More themes: drop a JSON file into
`~/.config/herdr-app/themes/` (no restart needed):

```json
{
  "background": "#1e1e2e",
  "foreground": "#cdd6f4",
  "selection": "#45475a",
  "cursor": "#f5e0dc",
  "ansi": ["#45475a", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
           "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8"]
}
```

Any terminal color scheme (Catppuccin, Gruvbox, Tokyo Night, ...) maps onto these fields. A
theme with the same name as a layout only shows while that layout is active. The
[gallery](https://herdr.dev/gallery) has community themes; none were installed.

## Estro layout and mods

Estro is [munza/herdr-mods](https://github.com/munza/herdr-mods)'s layout: sidebar on the left,
session in the middle, a 368px right panel with Files, Changes, PRs and Issues. It was installed
**without Branch Issue** (Linear, not used) and with
[jankeesvw/herdr-issues](https://github.com/jankeesvw/herdr-issues) (GitHub issues) in the
Issues slot. Better Alerts was skipped too: its notifications use Linux `notify-send`.

Pinned versions, as security-reviewed on 2026-11-23:

- **munza/herdr-mods** — `1abf4870adb4c3f7a71739db1e0c29493f5e3f95` (2026-11-19), Apache-2.0
- **jankeesvw/herdr-issues** — `15ffaad00d37efe17ef952109a3198fe299ecb67` (2026-11-03)

Installed mods:

| **Mod** | **What it does** | **Review verdict** |
|---|---|---|
| **better-sidebar** | Spaces with branch, PR status icon + number (green open, gray draft, purple merged, red closed/conflict/failing, yellow changes requested), nested worktrees | Safe. Runs `git`/`gh` read-only, at most once a minute per checkout. github.com remotes only |
| **better-tabs** | Draggable, wrapping tabs plus the panel toolbar | Safe. Only Herdr's own commands |
| **better-files** | File browser, Markdown preview, hand a file to an agent | **Quoting bug, unpatched** (see below). Markdown previews load remote images |
| **better-changes** | Git panel: stage, unstage, commit, amend, history, diffs | Safe. No discard/reset/push. "Stage all" doesn't confirm |
| **better-config** | One settings dialog for every mod (Mod settings) | Safe, minor: same quoting bug on mod folder names; writes backups to `~/.config/herdr-mods/` |
| **better-icons** | VS Code Material icons (1,184 SVGs, shipped, nothing downloaded) for the other mods | Safe |
| **branch-pr** | Current branch's PR: blockers, checks, threads, merge, "Fix with agent" | Caveats: hands PR comments/CI logs to an agent (prompt injection from anyone who can comment); comments post in one click; merges confirm first |
| **issues** (jankeesvw) | GitHub issues for the focused terminal's repo | Caveats: buttons act on GitHub as you; reads the focused terminal's last 300 lines every 3s for `#123` references (local only) |

### Install steps

Run from this repo's root in PowerShell 7. Nothing here is irreversible as long as step 1 is
done: Herdr restores its own shipped mods and layouts on every start, and these steps only add
new folders and one layout file.

```powershell
# ============================================================================
#                             Herdr: Estro + mods
# ============================================================================
$h = "$HOME\.config\herdr-app"
# 1. Back up the whole config (restoring this folder undoes everything below)
$backup = "$HOME\.config\herdr-app-backup-$(Get-Date -Format yyyy-MM-dd)"
Copy-Item -LiteralPath $h -Destination $backup -Recurse -Exclude 'herdr-app.sock'
# 2. Clone the reviewed commits (not the latest code; review again before bumping)
$src = Join-Path $env:TEMP "herdr-mods-src"
git clone --quiet https://github.com/munza/herdr-mods "$src\munza"
git -C "$src\munza" checkout --quiet 1abf4870adb4c3f7a71739db1e0c29493f5e3f95
git clone --quiet https://github.com/jankeesvw/herdr-issues "$src\issues"
git -C "$src\issues" checkout --quiet 15ffaad00d37efe17ef952109a3198fe299ecb67
# 3. Copy the mod folders (never overwrite an existing mod of the same name)
$mods = @(
    "$src\munza\better-icons\mods\better-icons",
    "$src\munza\better-sidebar\mods\better-sidebar",
    "$src\munza\better-tabs\mods\better-tabs",
    "$src\munza\better-files\mods\better-files",
    "$src\munza\better-changes\mods\better-changes",
    "$src\munza\better-config\mods\better-config",
    "$src\issues\mods\issues"
)
foreach ($m in $mods) {
    if (Test-Path "$h\mods\$(Split-Path $m -Leaf)") { Write-Host "exists, skipped: $m" }
    else { Copy-Item -LiteralPath $m -Destination "$h\mods\" -Recurse }
}
# 4. Build and install Branch PR (Go helper -> mods\branch-pr\bin\herdr-pr.exe).
#    GOTOOLCHAIN=local stops Go from downloading a different toolchain.
$env:GOTOOLCHAIN = 'local'
go -C "$src\munza\branch-pr\helper" run ./install
# 5. The Estro layout from this repo (Issues slot -> jankeesvw's mod) and its icon
Copy-Item .\herdr\layouts\estro.json "$h\layouts\estro.json"
Copy-Item .\herdr\layouts\estro-issues.svg "$h\layouts\estro-issues.svg"
# 6. Check every mod, then switch layout
foreach ($n in 'better-icons','better-sidebar','better-tabs','better-files','better-changes','better-config','branch-pr','issues') {
    herdr-app check "$h\mods\$n"
}
herdr-app do layout.switch '{"name":"estro"}'
herdr-app status
```

Notes on these steps:

- **Recipes not used as-is.** Each munza mod has a `RECIPE.md` for an agent ("add this mod:
  ..."). They point at the latest code, may run `sync.sh` and Node/Go tests. The steps above do
  the same copying from the pinned commits without any of that.
- **Shortcuts skipped.** Better Sidebar, Better Files and Better Config each offer one shortcut
  in `keys.json`. Not merged on purpose: once you edit `keys.json`, Herdr treats the whole file
  as yours and stops adding new default shortcuts on updates. Everything works from the toolbar.
- **`layouts/estro.json` vs munza's original:** the Issues button's `icon` is
  `layouts/estro-issues.svg` (was `mods/branch-issue/icons/issue.svg`) and its `target` is
  `issues` (was `linear-issues`); the stack block's `id` is `issues` and its `mod` is `issues`
  (were `linear-issues` / `branch-issue`). The SVG is Branch Issue's `icons/issue.svg`, since
  jankeesvw's mod ships none.
- **Branch PR on Windows** calls its helper without `.exe`; it works anyway ("No pull requests
  from main" shows up).
- **`Ctrl+Shift+L`** switches back to the `main` layout.

### Better Changes: limit the file list to 100

The Changes panel hangs ("This view could not be re-rendered ... interrupted", stuck on
"Loading changes…") when a repo has a few hundred changed files: it draws every row at once and
Herdr cuts off slow renders. Lower **Files shown** from 1000 to 100 (the header still counts all
changes; the list shows the first 100 with a note). Either use **Mod settings → Better Changes**,
or:

```powershell
$f = "$HOME\.config\herdr-app\mods\better-changes\mod.json"
$j = Get-Content $f -Raw | ConvertFrom-Json
$j | Add-Member -NotePropertyName settings -NotePropertyValue ([pscustomobject]@{ limits = [pscustomobject]@{ files = 100 } }) -Force
[IO.File]::WriteAllText($f, ($j | ConvertTo-Json -Depth 10))
```

Re-copying the mod folder on an update resets this.

### Known issues, deliberately left alone

- **Better Files quoting bug (unpatched).** On Windows it runs PowerShell with file names inside
  single quotes and only escapes `'` (`better-files/mods/better-files/files/shell.js:6`).
  PowerShell also treats curly quotes (`’`, `‘`) as quotes, so a file named like
  `x’;Start-Process calc;’` runs code when you expand its folder or open/reveal it in the Files
  panel. Same bug in Better Config, but only on mod folder names. One-line fix: escape the curly
  quotes too. Decision (2026-11-23): not patched, because only own repos are opened and a local
  patch would be wiped by every re-copy on update. Avoid expanding dependency folders
  (`node_modules/`, `.venv/`) and downloaded archives in the Files panel. Worth reporting
  upstream to munza (together with the slow Changes list).
- **jankeesvw issues: remote images don't load.** The mod expects
  `C:/Program Files/Git/bin/sh.exe`, which doesn't exist with scoop's git, so images in issues
  show "could not be loaded". Leave it: loading them would act as a tracking pixel (reveals your
  IP to whoever posted the image).
- **GitHub Enterprise isn't supported** by Better Sidebar: `githubRepository()` in
  `git/pr-status.js:31` only accepts `github.com` remotes, so setting `GH_HOST` doesn't help.
  A patch would need an allowed-hosts list there (return `host/owner/repo` and pass
  `--repo HOST/OWNER/REPO` to `gh`), the fork filter at line 166, the saved-PR-link pattern at
  line 120, and the fallback link in `views/spaces.js:625`, plus
  `gh auth login --hostname <host>`. Branch PR's Go helper wasn't checked for Enterprise.

### Uninstalling

Delete the mod folders and `layouts/estro*`, or restore the backup. Leftovers that removing the
folders doesn't clean up (all harmless):

- **issues** — cache in `data/issues/`, a few keys in `shared.json`, an entry in `seen.json`
- **branch-pr** — worktrees under `~/.herdr/worktrees/`, `branch.<name>.herdr-pr` entries in
  each repo's git config
- **better-config** — backups in `~/.config/herdr-mods/`

## Follow-up plan

Not done yet, in rough order:

1. **Report upstream to munza/herdr-mods:** the Better Files / Better Config curly-quote
   quoting bug (cause, affected files, one-line fix) and the Changes list drawing every row
   (hangs past a few hundred changed files; needs a virtualized list).
2. **Report upstream to scoop-nerd-fonts:** the pre-uninstall rename check can never pass while
   the font is registered, because the System process holds every user font for the session
   (see the Fonts section in the main README).
3. **Decide fork vs. upstream:** if the upstream fixes don't land, fork munza's mods (Apache-2.0)
   and install from the fork's pinned commits; patch the quoting bug, the list, and GitHub
   Enterprise support there.
4. **Build the ideas below** as needed: the all-PRs panel first.

## Ideas, not built

Discussed on 2026-11-23, kept for later:

- **One list of all my open PRs** across repos: none of the mods do this. It's a single
  `gh search prs --author @me --state open` call, so a small custom panel would do it.
  [Cockpit](https://github.com/quaresc/cockpit) does it but supports macOS/Linux only.
- **Fork munza's mods instead of rewriting** (Apache-2.0): fix the quoting bug, the slow Changes
  list, add Enterprise support. A full rewrite with Claude Code was estimated at 1–2 weeks of
  evenings (munza's mods are ~19k lines plus the icon set); each mod ships a `RECIPE.md` that
  doubles as a build brief.
- **Professional layout**: sidebar + terminals + a right panel stack (Files, Changes, PRs incl.
  Enterprise, work items from Jira/Azure DevOps, CI/CD, inbox) and a CI status bar. Panels must
  be JavaScript (Herdr's runtime draws them natively); integrations can be Python.
  - **Python helpers** installed once (a `uv` venv synced from `uv.lock` with `--locked`, called
    by full path), not `uv run` on every call.
  - **Better: one long-running local Python server** the mods `fetch()` from, so corporate
    endpoint scanners don't see a new process per refresh. Start it with a Task Scheduler
    "at logon" task (`pythonw.exe`), bind to `127.0.0.1` only, require a token from a file in the
    user profile, check the `Host` header, no CORS, read-only by default.
  - **Fewer `git`/`gh` processes**: `pygit2` for reading repo state (not GitPython, which shells
    out to `git`), `watchfiles` on `.git` to recompute only on change, `githubkit` or `httpx`
    with GraphQL (one query for all PRs) and ETags (304s don't count against rate limits). Keep
    commits, fetch and push on the real `git` (hooks, signing, credential helpers).
- **Orchestrator agent** (Herdr TUI, not the desktop app): run Claude in a `herdr` pane, give it
  the official skill (`npx skills add herdrdev/herdr --skill herdr -g`, or paste
  `herdr --skill` output into a CLAUDE.md) plus an orchestrator brief: split work, start helper
  agents with `herdr agent start <name> --kind claude --pane <id>`, delegate with
  `herdr agent prompt <name> "<task>" --wait --timeout 600000`, collect with
  `herdr agent read`, never approve a blocked helper's prompts on the user's behalf. Caveats:
  agent state is read from the screen (an unrecognised approval dialog can look `idle`), waits
  are unbounded without `--timeout`, no tmux inside panes.
