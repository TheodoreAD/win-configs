"""Summarize Claude Code session transcripts (~/.claude/projects/<project>/<session>.jsonl).

Useful for recovering what was done in past sessions, e.g. to document a machine setup.

Modes:
  prompts   user prompts only
  dialog    user prompts and Claude's text replies
  actions   file writes/edits and shell commands (truncated), one per line
  commands  full shell commands and edit diffs, optionally within a time window

Examples (from the repo root):
  uv run python scripts/claude-session-extract.py list win-configs
  uv run python scripts/claude-session-extract.py prompts ~/.claude/projects/<dir>/*.jsonl
  uv run python scripts/claude-session-extract.py dialog <session.jsonl> > dialog.txt
  uv run python scripts/claude-session-extract.py commands <session.jsonl> --since 2026-11-22T23:29 --until 2026-11-22T23:40

Timestamps in transcripts are UTC, compared as ISO-8601 string prefixes (YYYY-MM-DDTHH:MM).
"""

import argparse
import datetime as dt
import glob
import json
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
SHELL_TOOLS = ("Bash", "PowerShell")
EDIT_TOOLS = ("Write", "Edit", "MultiEdit")


def records(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(
        c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"
    )


def is_user_prompt(rec):
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("toolUseResult") is not None:
        return None
    t = text_of((rec.get("message") or {}).get("content")).strip()
    # skip tool results and harness-injected blocks
    return t if t and not t.startswith("<") and "tool_result" not in t else None


def tool_uses(rec):
    if rec.get("type") != "assistant":
        return
    for c in (rec.get("message") or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_use":
            yield c.get("name"), c.get("input") or {}


def in_window(ts, since, until):
    return (not since or ts >= since) and (not until or ts[: len(until)] <= until)


def cmd_list(args):
    for d in sorted(PROJECTS.iterdir()):
        if not d.is_dir() or (args.filter and args.filter.lower() not in d.name.lower()):
            continue
        print(d)
        for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
            mtime = dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            first = next((p for p in map(is_user_prompt, records(f)) if p), "")
            print(f"  {mtime}  {f.stat().st_size // 1024:>6} KB  {f.stem}  {first[:80]!r}")


def cmd_extract(args):
    files = [p for pattern in args.files for p in (glob.glob(str(Path(pattern).expanduser())) or [pattern])]
    for f in files:
        print(f"\n######## {Path(f).stem}")
        for rec in records(f):
            ts = (rec.get("timestamp") or "")[:16]
            if not in_window(ts, args.since, args.until):
                continue
            prompt = is_user_prompt(rec)
            if prompt and args.mode in ("prompts", "dialog"):
                print(f"\n[{ts}] USER: {prompt[: args.max]}")
            if args.mode == "dialog" and rec.get("type") == "assistant":
                t = text_of((rec.get("message") or {}).get("content")).strip()
                if t:
                    print(f"[{ts}] CLAUDE: {t[: args.max]}")
            if args.mode in ("actions", "commands"):
                for name, inp in tool_uses(rec):
                    if name in SHELL_TOOLS:
                        cmd = inp.get("command", "")
                        print(f"[{ts}] {name}: {cmd[:300] if args.mode == 'actions' else cmd}")
                    elif name in EDIT_TOOLS and args.mode == "actions":
                        print(f"[{ts}] {name}: {inp.get('file_path')}")
                    elif name in EDIT_TOOLS:
                        print(f"\n[{ts}] {name.upper()} {inp.get('file_path')}")
                        if "old_string" in inp:
                            print(f"--- old\n{inp['old_string']}\n--- new\n{inp.get('new_string')}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # transcripts contain glyphs; Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("list", help="list projects and sessions")
    p.add_argument("filter", nargs="?", help="substring of the project folder name")
    p.set_defaults(func=cmd_list)
    for mode in ("prompts", "dialog", "actions", "commands"):
        p = sub.add_parser(mode)
        p.add_argument("files", nargs="+", help="session .jsonl files (globs allowed)")
        p.add_argument("--since", help="UTC start, e.g. 2026-11-22T20:00")
        p.add_argument("--until", help="UTC end (prefix compare), e.g. 2026-11-22T23")
        p.add_argument("--max", type=int, default=4000, help="truncate texts to this many characters")
        p.set_defaults(func=cmd_extract)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
