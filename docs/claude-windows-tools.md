# Claude Code on Windows: shells and tools

How Claude Code, PowerShell 7, the PowerShell profile and the Unix tools fit together on this
machine. Current as of 2026-11-23. The Claude Code config itself is in
[../claude/](../claude/README.md).

## Shells

- **Claude's shell tool is PowerShell 7.** Claude Code uses `pwsh.exe` when it's on PATH and
  falls back to Windows PowerShell 5.1 otherwise. There's no setting to choose; it's detected at
  startup, so restart Claude Code after installing `pwsh`.
- **`!` commands run in PowerShell** because of `"defaultShell": "powershell"` in
  `~/.claude/settings.json`. Without it they run in Git Bash.
- **Claude's shell doesn't load your PowerShell profile.** Aliases, functions (`l`, `d`,
  `docker`) and Oh My Posh exist only in your interactive terminals.
- **Claude's shell sets `NO_COLOR=1`** for its own commands. It's not in the Windows environment
  or the profile, so your own terminals aren't affected.

## Aliases are kept

PowerShell 7's built-in aliases (`ls`, `cat`, `rm`, `cp`, `mv`, `where`, `sort`, `echo`,
`tee`, `diff`, `sleep`, `ps`, `kill`, `man`, ...) are **kept** in the profile. The profile used
to remove them so the GNU tools would run instead. That was dropped on 2026-11-22 because:

- Claude's shell never loaded the profile anyway, so commands behaved differently in Claude's
  shell and in your terminal.
- Some removals backfired: `sort` became Windows' `sort.exe` (neither `Sort-Object` nor GNU
  sort), `ps`/`kill` became MSYS versions that only see MSYS processes, `man` disappeared.
- PowerShell's object pipelines (`ls | where Length -gt 1MB | sort Length`) and Terminal-Icons
  (icons in `Get-ChildItem` output) need the aliases.
- `curl`, `wget` and `sc` aren't aliases in PowerShell 7 at all, so removing them did nothing.

Rules that follow from this (also in the global `CLAUDE.md`):

- **Commands Claude runs or suggests use full cmdlet names** (`Get-ChildItem`, `Get-Content`,
  `Where-Object`, `Remove-Item`, ...), so they work the same in both shells.
- **GNU tools are called with `.exe`** when they share a name with an alias: `ls.exe`,
  `cat.exe`, `rm.exe`. The profile's `l` function calls `ls.exe`.
- **Tools without an alias** are called by name: `grep`, `sed`, `awk`, `rg`, `fd`, `curl`.

## No `find` → `fd` function

The profile used to define `function find { fd @Args }`. It was removed on 2026-11-22: it saved
no typing (`fd` is shorter), real `find` syntax (`find . -name "*.js"`) doesn't work in `fd`, and
it hid both Windows `find.exe` and GNU `find`. Type `fd` for file search. `find` now runs
Windows' `System32\find.exe` (a text search tool).

## PATH order and which tool runs

Windows builds PATH as **system PATH + user PATH**, so `System32` always comes before the
folders the README adds to the user PATH (git's `usr\bin` and `bin`, `~\.local\bin`). Any tool
that exists in both resolves to the System32 version:

| **Name** | **Runs in PowerShell** | **To get the other one** |
|---|---|---|
| **`find`** | `C:\Windows\System32\find.exe` (text search) | Use `fd`, or the full path to git's `usr\bin\find.exe` |
| **`sort`** | `Sort-Object` (alias); `sort.exe` is Windows' | Git's `usr\bin\sort.exe` by full path |
| **`ssh`** | `C:\Windows\System32\OpenSSH\ssh.exe` | Wanted: it's the one that talks to the Windows ssh-agent |

`System32\OpenSSH` appears twice in PATH; that's harmless.

Git is different: when git runs `ssh` it puts its own `usr\bin` first, whatever PATH says.
That's why the README sets `core.sshCommand` to Windows' `ssh.exe` by full path.

Git Bash (including Claude's Bash tool, if used) resolves `/usr/bin` first, so `ssh`, `ssh-add`
there are git's MSYS versions, which can't reach the Windows agent. Git commands from Git Bash
are fine once `core.sshCommand` is set; only a manual `ssh -T git@github.com` in Git Bash would
ask for the passphrase. Not worth fixing since PowerShell is the shell everywhere.

## Tools Claude relies on

- **`rg`** (`scoop install main/ripgrep`) — content search, preferred over `grep`
- **`fd`** (`scoop install main/fd`) — file search, preferred over `find`
- **`grep`, `sed`, `awk`, `head`, `tail`** — Git for Windows `usr\bin`
- **`curl`** — `scoop install main/curl` (PowerShell 7 has no `curl` alias)
- **`jq`** — `scoop install main/jq`
- **`uv`** — Python scripts (`uv run`), see the main README
- **`gh`** — GitHub, logged in with SSH as the git protocol

Claude prefers its own Read/Write/Edit/Glob/Grep tools over all of these; see the global
`CLAUDE.md`.

## Verifying

In a fresh PowerShell 7 terminal (profile loaded):

```powershell
$PSVersionTable.PSVersion                       # 7.x
Get-Command ls, cat, sort, where | Select-Object Name, CommandType   # Alias
Get-Command l, d | Select-Object Name, CommandType                   # Function
Get-Command rg, fd, grep, curl | Select-Object Name, Source          # Application
```

In Claude Code: `! $PSVersionTable.PSVersion` should print 7.x.
