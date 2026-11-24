# Global Preferences

Applies to all projects.

---

## Environment

- **OS:** Windows 11
- **Shell for one-off commands:** PowerShell 7 (`pwsh`, installed via scoop) — not Bash, and not Windows PowerShell 5.1
- PowerShell 7 syntax is fine: `&&`, `||`, `??`, `?.` and ternary `?:` all work
- Unix tools available from Git's `usr/bin` (`grep`, `sed`, `awk`, ...). PowerShell's built-in aliases are kept everywhere (`ls`, `cat`, `rm`, `where`, `sort` are cmdlets), so call GNU versions with `.exe` (`ls.exe`, `cat.exe`)
- Claude Code's own shell does not load the user's PowerShell profile
- In PowerShell commands Claude runs or suggests, prefer full cmdlet names (`Get-ChildItem`, `Get-Content`, `Where-Object`, `Remove-Item`, ...) over aliases
- `rg` (ripgrep) and `fd` available and preferred over `grep`/`find` when shell search is needed
- `curl` available

---

## Tool Usage

Always prefer Claude Code's built-in tools over shell commands. They are more transparent and reviewable.

| Task | Use | Never use |
|---|---|---|
| **Read a file** | Read tool | `cat`, `head`, `tail` |
| **Create/write a file** | Write tool (handles dirs implicitly) | `echo`, heredoc, `mkdir` + touch |
| **Edit a file** | Edit tool | `sed`, `awk` |
| **Find files** | Glob tool | `find`, `fd` |
| **Search content** | Grep tool | `grep`, `rg` |
| **One-off shell command** | PowerShell 7 | Bash |

The Bash tool is disabled on Windows (`permissions.deny` in `~/.claude/settings.json`). When shell search is needed and no internal tool covers it: use `rg` for content search, `fd` for file search.

---

## Scripting

- **Simple one-off commands** → PowerShell 7 one-liner
- **Anything with logic, data processing, or reuse value** → Python script, saved to `scripts/` in the project
- Never write PowerShell scripts unless the user explicitly requests it — PowerShell is only acceptable for quick one-liners
- Always ask the user if scripts should be saved for reuse

---

## File & Directory Naming

- All file and directory names use **kebab-case** (e.g. `my-note.md`, `area-health/`)

---

## Markdown Formatting

- Use tables only when there are **three or more columns** — two-column data belongs in a bullet list
- In bullet lists replacing tables, format as: `- **First item** — description`
- When using tables, always **bold the values in the first column** and the header
- Always add a blank line below headings (any level), and below any paragraph that is immediately followed by a list

---

## Code and Repositories

- **No personal details in repos.** Never write the user's name, email, GitHub login or ID, Windows username, computer name, key names, home path or hardware into code, configs or docs. Derive them when needed (`$HOME`, `$env:USERNAME`, `$env:COMPUTERNAME`, `gh api user`), and use placeholders in templates (e.g. `__HOME__`) that the install step fills in. Examples use made-up values (`MY-PC`, `my-user`)
- **Commit email:** commits must not expose a personal email address. Use GitHub's noreply address (`<id>+<login>@users.noreply.github.com`, derived from `gh api user`)
- **Line endings:** every repo gets a `.gitattributes` that stores and checks out text as LF (`* text=auto eol=lf`), keeps `.bat`/`.cmd` as CRLF and marks binaries. Shell scripts that run in WSL or on Linux must be LF. A template lives in the `win-configs` repo (`git/gitattributes`)
- **Editor folders** (`.vscode/`, `.idea/`) are personal and never committed
- **No repo-specific rules for machine behavior.** Git and Claude Code behavior comes from global config so every repo works the same. Don't add local git config (`core.autocrlf`, `url.*.insteadOf`, ...) or `.claude/settings*.json` entries that would make sense in any repo, and never add hooks; propose a global change in the `win-configs` repo instead. `.claude/settings.local.json` is only for things specific to that repo on this machine (e.g. `additionalDirectories`)
- **Python tools run through `uv run`** (`uv run invoke ...`, `uv run pytest`); never activate a venv

---

## Git Commits

- **One commit per meaningful change.** Split unrelated changes into separate commits, even when they were made in the same session. If one file holds changes for several concerns, commit it in stages (write the intermediate version, commit, then the next) rather than lumping concerns together
- **Commit only your own session's changes.** Changes made by another session (another Claude Code session, another agent, or the user) are left for that session to commit. Before committing, check `git status` and `git diff` for changes this session didn't make and don't stage them, even when they're in a file this session also changed (stage only this session's hunks). Mention what was left out
- **Descriptive messages.** `git log` should tell the story without checking anything out:
  - Subject line: what changed, in the imperative, specific enough to stand alone (`Add headless browse tool for blocked shop sites`, not `Update scripts`)
  - Body: why the change was made, what it does, notable decisions or limitations, and what was tested. Mention files when it helps
- Order commits so each builds on the previous one and the repo makes sense at every commit

---

## Memory

- Never create, save, or write entries to the persistent memory system, for any reason, in any project — not for user info, feedback, project context, or references, even when a memory-worthy moment occurs or the user's message would otherwise call for it
- If durable instructions are worth persisting, put them in a CLAUDE.md (global or project) or a project's own docs (e.g. AGENTS.md) instead, and say so explicitly rather than defaulting to memory
