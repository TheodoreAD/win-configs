# Skills

Agent skills are authored here and installed with [`npx skills`](https://github.com/vercel-labs/skills)
wherever they're needed. Installed copies (`.claude/skills/`, `.agents/skills/`, ...) and
`skills-lock.json` are gitignored, because each machine and person may install a different set:
never edit or commit them, edit the source here and reinstall.

- **[herdr-remote](herdr-remote/SKILL.md)** — Herdr desktop app with a Linux controller reaching
  this Windows machine and its WSL distro over SSH: setup steps, plus `doctor`, `status` and
  `key-line` commands (`scripts/herdr-remote.py`)

## Install

From the repo root, in this project:

```powershell
npx skills add ./skills --skill herdr-remote -a universal claude-code -y
```

`-a universal claude-code` puts the real copy in `.agents/skills/`, which every agent but Claude
Code reads, and one link per skill in `.claude/skills/` for Claude Code (a junction on Windows, no
Developer Mode needed). Without `-a`, `npx skills` installs for every agent it detects, some into
non-hidden folders. The lock file doesn't record agents, so always pass `-a`. Add `-g` to install
for all your projects instead (`~/.agents/skills/` plus links in `~/.claude/skills/`).

The installed copy doesn't follow the source. After editing a skill here, run the same command again.
`npx skills update` doesn't help here: it skips skills installed from a local path.

## Install on another machine (e.g. the Linux side of herdr-remote)

No clone needed: `npx skills` installs straight from GitHub. Replace `<github-user>` with
this repo's owner:

```bash
npx skills add <github-user>/win-configs --skill herdr-remote -a universal claude-code -g -y
```

`-g` makes it available in every project on that machine (`~/.agents/skills/`, linked into
`~/.claude/skills/`). Then ask
Claude there to "set up the herdr remote" or "run the herdr doctor". It finds the current
step itself, and only asks for what lives on the other machine. Only pushed changes reach
other machines.

To pull later pushes into every skill installed from GitHub this way, run:

```bash
npx skills update -g -y
```

It reads `~/.agents/.skill-lock.json`, which records each global install and its source.

## Running the doctor without Claude

```powershell
python -I skills\herdr-remote\scripts\herdr-remote.py doctor     # Windows
```

```bash
python3 skills/herdr-remote/scripts/herdr-remote.py doctor       # Linux controller
```
