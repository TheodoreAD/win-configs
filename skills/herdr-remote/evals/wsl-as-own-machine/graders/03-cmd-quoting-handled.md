---
type: llm
focus: trace
weight: 1
---

wsl-plan.md accounts for Windows sshd passing the command through cmd.exe (quoting), e.g. with a wrapper/bridge or encoding, rather than a raw `ssh winbox wsl.exe ... sh -c` line
