"""Check that PowerShell code blocks in Markdown files parse.

Extracts every ```shell / ```powershell block and runs PowerShell 7's parser on it (nothing is
executed). Blocks meant for bash (e.g. the WSL steps) fail to parse; mark those ```bash so
they're skipped.

Usage, from the repo root:
  uv run python scripts/check-readme-blocks.py README.md herdr/README.md claude/README.md docs/*.md
"""

import glob
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PARSE = (
    "$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$e); "
    "if ($e) {{ $e | ForEach-Object {{ 'line {{0}}: {{1}}' -f $_.Extent.StartLineNumber, $_.Message }}; exit 1 }}"
)


def main():
    files = [p for pattern in sys.argv[1:] for p in glob.glob(pattern)]
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for md in files:
            text = Path(md).read_text(encoding="utf-8")
            for m in re.finditer(r"^ *```(shell|powershell)\n(.*?)^ *```", text, re.S | re.M):
                line = text[: m.start()].count("\n") + 1
                block = Path(tmp) / "block.ps1"
                block.write_text(m.group(2), encoding="utf-8")
                cmd = PARSE.format(path=str(block).replace("'", "''"))
                r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
                status = "ok" if r.returncode == 0 else "FAIL\n    " + r.stdout.strip().replace("\n", "\n    ")
                failed += r.returncode != 0
                print(f"{md}:{line}: {status}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
