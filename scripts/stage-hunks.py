"""Stage only some of a file's changes, for one-commit-per-change history.

Lists a file's changes (index vs working tree) as numbered hunks, then stages the chosen ones by
writing that intermediate version straight into git's index. The working tree is never touched,
so the rest stays uncommitted for a later commit (or for another session to commit).

Usage, from the root of any git repo:
  uv run python <path-to>/stage-hunks.py list README.md
  uv run python <path-to>/stage-hunks.py stage README.md 1,4,7-9
  git diff --cached README.md        # check, then commit

Notes:
- Hunks come from `git diff --histogram -U0` with CR at end of line ignored, so CRLF/LF
  differences don't show up as changes.
- Numbers change after each stage: run `list` again before the next `stage`.
- A hunk can't be split. When one hunk mixes two changes (e.g. a whole section rewritten), build
  the intermediate file another way (write it, `git add`, restore the final version).
- Staged content is written with LF line endings (pair with an LF `.gitattributes`).
"""

import re
import subprocess
import sys


def git(*args, input=None):
    r = subprocess.run(["git", *args], capture_output=True, input=input)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.decode()}")
    return r.stdout


def hunks(path):
    """Return the index version's lines and a list of (old_start, old_end, new_lines, old_lines)."""
    staged = git("ls-files", "-s", "--", path)
    index = git("show", f":{path}").decode("utf-8") if staged else ""
    old = index.replace("\r\n", "\n").splitlines(keepends=True)
    with open(path, encoding="utf-8", newline="") as f:
        new = f.read().replace("\r\n", "\n").splitlines(keepends=True)
    diff = git("-c", "core.autocrlf=false", "diff", "--histogram", "-U0", "--ignore-cr-at-eol",
               "--no-color", "--", path).decode("utf-8")
    out = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff, re.M):
        old_start, old_count = int(m[1]), int(m[2] or 1)
        new_start, new_count = int(m[3]), int(m[4] or 1)
        i = old_start if old_count == 0 else old_start - 1  # pure inserts go after line old_start
        j = new_start if new_count == 0 else new_start - 1
        out.append((i, i + old_count, new[j:j + new_count], old[i:i + old_count]))
    return old, out


def parse(spec):
    chosen = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        chosen.update(range(int(a), int(b or a) + 1))
    return chosen


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3 or sys.argv[1] not in ("list", "stage"):
        raise SystemExit(__doc__)
    mode, path = sys.argv[1], sys.argv[2]
    old, hs = hunks(path)
    if mode == "list":
        for n, (i1, _, add, rem) in enumerate(hs, 1):
            first = (add or rem)[0].rstrip()[:90]
            print(f"{n:>3}: line {i1 + 1:>4}  -{len(rem)} +{len(add)}  {'+' if add else '-'} {first}")
        return
    chosen = parse(sys.argv[3])
    result = list(old)
    for n, (i1, i2, add, _) in reversed(list(enumerate(hs, 1))):  # bottom-up keeps positions valid
        if n in chosen:
            result[i1:i2] = add
    blob = git("hash-object", "-w", "--stdin", input="".join(result).encode("utf-8")).decode().strip()
    entry = git("ls-files", "-s", "--", path).decode().split()
    git("update-index", "--add", "--cacheinfo", f"{entry[0] if entry else '100644'},{blob},{path}")
    print(f"staged {len(chosen & set(range(1, len(hs) + 1)))} hunk(s) of {path}")


if __name__ == "__main__":
    main()
