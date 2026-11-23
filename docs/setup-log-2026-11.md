# Setup log, November 2026

What was changed on the first machine set up this way, during Claude Code sessions on
2026-11-22 and 2026-11-23, in order, with the reasons. The README and the `claude/`, `herdr/`,
`ssh/` and `git/` folders hold the resulting setup; this log keeps the process and the decisions.

## 2026-11-22: PowerShell 7, Claude Code, scoop

- **Herdr reviewed.** Read `~/.config/herdr-app/AGENTS.md`. Terminals already get
  `TERM=xterm-256color` and `COLORTERM=truecolor`, so nothing was needed for 256/24-bit color.
- **PowerShell 7 installed** with `scoop install pwsh` (7.7.0). Only Windows PowerShell 5.1
  existed before; Herdr opens terminals in `pwsh` when available.
- **Profile copied to PowerShell 7** (`Documents\PowerShell\Microsoft.PowerShell_profile.ps1`).
  The 5.1 profile (`Documents\WindowsPowerShell\...`) was left as it was, with the old alias
  removal and `find` function. Terminal-Icons loads from PowerShell 7's own module folder.
- **Claude Code switched to PowerShell 7.** No setting chooses 5.1 vs 7: Claude Code picks
  `pwsh` when it's on PATH, at startup. Added `"defaultShell": "powershell"` (so `!` commands
  run in PowerShell, not Git Bash) and `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` to
  `~/.claude/settings.json`. Global `CLAUDE.md` updated from "PowerShell 5" to "PowerShell 7"
  in three places. Verified after a restart: tool and `!` both on 7.7.0.
- **Alias removal reconsidered.** Claude's shell doesn't load the profile, so the "aliases
  fixed" note in `CLAUDE.md` was only true in interactive terminals. Some removals backfired
  (`sort` became Windows `sort.exe`, `ps`/`kill` became MSYS versions, `man` disappeared;
  `curl`/`wget`/`sc` aren't aliases in PowerShell 7). First narrowed the list, then **stopped
  removing aliases entirely**: `l` now calls `ls.exe`, and `CLAUDE.md` says to use full cmdlet
  names in any command Claude runs or suggests and to call GNU tools as `*.exe`.
- **`find` → `fd` function removed.** It saved no typing, real `find` syntax doesn't work in
  `fd`, and it hid both Windows and GNU `find`. Use `fd`.
- **Node via fnm.** fnm was configured but had no Node installed. Installed the LTS
  (`fnm install --lts; fnm default lts-latest`): Node 26.13.1, npm 11.20.0. nvm isn't needed.
- **`scoop update *`.** 16 of 18 apps updated. It stopped at the Cascadia Nerd Fonts and
  skipped Syncthing (running). Syncthing updated after quitting it from the tray (2.1.7, tray
  2.1.9).
- **Font update impossible → held.** All 24 CaskaydiaCove files were locked by the `System`
  process (PID 4): Windows loads every registered user font at sign-in and holds it for the
  session. The nerd-fonts package's pre-uninstall rename check therefore always fails, so scoop
  can install these fonts but never update them. Ran
  `scoop hold CascadiaCode-NF CascadiaCode-NF-Mono` (held at 3.4.0; 3.5.1 only adds icons).
  The only real update path is: unhold, delete the registry entries, restart, update before
  opening anything. Not reported upstream yet
  ([scoop-nerd-fonts issues](https://github.com/matthewjberger/scoop-nerd-fonts/issues)).
- **Herdr font** set to `CaskaydiaCove Nerd Font Mono` (was plain `Cascadia Code`, briefly
  JetBrains Mono while debugging the lock). Checked with a screenshot.
- **Claude status line** built in PowerShell: first a minimal one, then a maximal one refined
  over ~30 iterations (see `claude/README.md` for the design decisions), then the minimal one
  and the debug input dump were deleted. Fix found on the way: the script must set console
  output to UTF-8 or `│` and Nerd Font glyphs show as `�`.
- **PowerShell extras offered, not done:** PSReadLine history list view
  (`Set-PSReadLineOption -PredictionSource History -PredictionViewStyle ListView`), lazy-loading
  Terminal-Icons (profile adds ~0.6 s per new tab: 755 ms vs 160 ms without), making the 5.1
  profile load the 7 one, the "Open PowerShell 7 here" Explorer menu (`reg import` lines printed
  by scoop).
- **Line endings**: wrote a `.gitattributes` for a repo (LF everywhere, CRLF for
  `.bat`/`.cmd`, binaries marked) to stop CRLF/LF noise. Kept here as `git/gitattributes`.

## 2026-11-22/23 night: Herdr mods

- **Research.** The desktop app has mods and layouts (gallery at herdr.dev/gallery), not the
  TUI's plugins. For "see my open PRs": Better Sidebar (PR icon per space) and Branch PR (full PR
  panel) from munza; Cockpit would list all PRs but is macOS/Linux only.
- **Go installed** with `scoop install go` (1.27.4) for Branch PR's helper. Note learned:
  restarting the Herdr window doesn't restart `herdr-core.exe serve`, but `go` was found anyway
  through the scoop shims folder.
- **Security review** (three parallel reviews of munza `1abf487` and jankeesvw `15ffaad`, about
  20k lines). Nothing malicious. One real bug: Better Files (and Better Config) can run code
  from a file name containing curly quotes. Caveats: Branch PR hands PR text to agents (prompt
  injection), issue/Markdown images load from anywhere (tracking pixels).
- **Install.** Backed up `~/.config/herdr-app` first (the backup was deleted once the setup was
  documented). Copied 7 mods from the pinned commits, built Branch PR, installed Estro with
  jankeesvw's issues mod in place of Branch Issue (Linear), switched to Estro. `keys.json`,
  `settings.json` and Herdr's own layouts unchanged. Shortcuts deliberately not merged.
- **Decision: don't patch the quoting bug** (only own repos are opened; a local patch would be
  wiped on every update). Report upstream instead.
- **Changes panel hang fixed** by lowering Better Changes' "Files shown" to 100 (the repo had
  445 changed files; drawing all rows exceeded Herdr's render time limit).
- **Planning only**: rebuild vs fork munza (fork), a professional layout with a Python
  integrations server, how to avoid per-refresh `git`/`gh` processes, and a Herdr TUI
  orchestrator setup. Summarised under "Ideas, not built" in `herdr/README.md`.

## 2026-11-23: git over SSH

- **Push failed** with "Permission denied (publickey)". Cause: git used its bundled MSYS `ssh`,
  no agent was running (Windows `ssh-agent` service disabled), and the key is passphrase
  protected.
- **Windows ssh-agent instead of PuTTY Pageant.** The README's unfinished Pageant section was
  replaced: the built-in agent keeps keys across reboots and needs nothing in the profile.
- **Setup.** Enabled and started the `ssh-agent` service (admin), `ssh-add`-ed the machine's
  existing key (`id_ed25519_<computer name>`, already on GitHub under the computer name, so no
  new key or upload), set `git config --global core.sshCommand
  C:/Windows/System32/OpenSSH/ssh.exe`, installed `ssh/config`. Verified with
  `ssh -T git@github.com` and a real fetch and push.
- **Cleanup.** Uninstalled `putty-cac` (only used for Pageant), deleted `~/.ssh/agent.env` (a
  2019 Git Bash agent leftover), `~/.ssh/known_hosts.old` and the old config's backup.
- **Commit signing** with the same key: offered, declined.
- **PATH claim corrected.** The README said git's `usr\bin` takes precedence over System32. It
  can't: the user PATH always comes after the system PATH, so `find.exe`, `sort.exe` and
  `ssh.exe` resolve to System32.

## 2026-11-23 evening: cleanup and fresh-machine docs

- **Herdr install command recorded:** the app was installed with the one-liner from
  herdr.dev (`irm https://releases.herdr.dev/app/install.ps1 | iex`).
- **Herdr telemetry turned off** (`"telemetry": false` in `settings.json`).
- **Windows PowerShell 5.1 profile** now only dot-sources the PowerShell 7 profile.
- **WezTerm** starts `pwsh` instead of `powershell.exe`. Kept as the fallback terminal for when
  Herdr has to be closed.
- **Claude Code** is the native install (`~\.local\bin\claude.exe`, self-updating), not npm;
  README updated.
- **Docker state documented** (see "WSL and Docker" in the README): Windows CLIs installed but
  not connected, no Docker Engine in WSL yet. Target: engine in WSL via the separate Linux setup
  project, `DOCKER_HOST=tcp://127.0.0.1:2375` on Windows, profile functions removed. Not done
  yet.
- **README reordered for a fresh machine:** the profile is installed after Oh My Posh,
  Terminal-Icons and fnm, from PowerShell 7.
- **Scripts added:** `scripts/claude-session-extract.py` (recover prompts, replies, commands
  from Claude Code transcripts) and `scripts/check-readme-blocks.py` (checks README PowerShell
  blocks parse).
- **No personal details in the repo:** names, the computer name, key names and paths are
  derived by the commands (`$env:COMPUTERNAME`, `$env:USERNAME`, `$HOME`, `gh api user`) instead
  of written down. Backups made during setup (the Herdr config copy, the old 5.1 profile) were
  deleted.
- **Repo hygiene:** `.gitattributes` (LF for everything, including PowerShell and WSL scripts),
  `.vscode/` and `.idea/` ignored.
- **Obsidian and Syncthing** made optional installs.

## 2026-11-24: WSL user and network notes

- **WSL user `dev` created from Windows.** The distro only had `root`: the old README step that
  wrote `/etc/wsl.conf` with `tee` replaced the whole file, and no normal user existed. `dev` is
  a generic name (not tied to the Windows account, the same on every machine), with
  passwordless sudo (a WSL sudo password isn't a boundary: `wsl -u root` works from Windows
  without one) and set as the default via the registry's `DefaultUid`, leaving
  `/etc/wsl.conf` to the Linux setup repo.
- **Network profile reviewed:** the home LAN is on Public but File and Printer Sharing is on for
  Public and a `Users` share exists; the network printer (IPP) doesn't need either. Ideal setup
  recorded in `docs/plan-apps-and-settings.md`; nothing changed yet.

## Open items

- **Docker target** (above), once the Linux setup project (`power-user-linux-setup`) has run in
  WSL.
- **Herdr follow-up plan:** see "Follow-up plan" in `herdr/README.md`.
- **Apps outside scoop, Windows settings, superseded installs:** see
  `docs/plan-apps-and-settings.md`.
