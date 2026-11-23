# Skills

Agent skills are authored here and installed with [`npx skills`](https://github.com/vercel-labs/skills)
wherever they're needed. Installed copies (`.claude/skills/`, `.agents/`) and `skills-lock.json`
are gitignored: never edit or commit them, edit the source here and reinstall.

- **[herdr-remote](herdr-remote/SKILL.md)** — Herdr desktop app with a Linux controller reaching
  this Windows machine and its WSL distro over SSH: setup steps, plus `doctor`, `status` and
  `key-line` commands (`scripts/herdr-remote.py`)

## Install (Claude Code only)

From the repo root, in this project:

```powershell
npx skills add ./skills --skill herdr-remote -a claude-code -y
```

`-a claude-code` is the "Claude only" marker. Without it, `npx skills` also installs for every
agent it detects and creates `.agents/skills/`. The lock file doesn't record agents, so always
pass `-a`. Add `-g` to install for all your projects instead (`~/.claude/skills/`).

The install is a copy, not a link. After editing a skill here, run the same command again.

## Running the doctor without Claude

```powershell
python -I skills\herdr-remote\scripts\herdr-remote.py doctor     # Windows
```

```bash
python3 skills/herdr-remote/scripts/herdr-remote.py doctor       # Linux controller
```
