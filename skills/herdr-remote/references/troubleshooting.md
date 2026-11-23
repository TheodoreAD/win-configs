# Troubleshooting

Start with `doctor` on both machines. The Windows run is most informative from an elevated
window. Each section below is a symptom.

## Windows sshd logs

Run this in an admin PowerShell window:

```powershell
Get-WinEvent -LogName OpenSSH/Operational -MaxEvents 30 | Format-Table TimeCreated, Message -Wrap
```

The log says why a key was refused: bad file permissions, user not allowed, or a `from=`
mismatch.

## `Permission denied (publickey)`

Check these in order:

1. **Wrong key file.** If the account is an admin, the key must be in
   `C:\ProgramData\ssh\administrators_authorized_keys`, not `~\.ssh\authorized_keys`.
2. **File permissions.** The file must be readable by Administrators and SYSTEM only.
   Redo the `icacls` line in `windows-host.md` step 5.
3. **`from=` IP.** If the Linux IP changed (no DHCP reservation), `from=` no longer
   matches. Fix the reservation, then the key line and the firewall rule.
4. **`AllowUsers`.** The name must be lowercase and placed above the `Match` block.
5. **The key line itself.** It must be a single line. A paste can wrap it or add a BOM;
   `-Encoding utf8NoBOM` avoids the BOM.
6. **Linux side.** Check `IdentityFile` and `IdentitiesOnly yes`. Run
   `ssh -v winbox hc --version` to see which key is offered.

## Timeout or connection refused

- **Windows asleep or off.**
- **sshd stopped.** `doctor` on Windows shows this.
- **Windows IP changed.** Update `HostName` in `~/.ssh/config`.
- **Firewall.** The rule's `RemoteAddress` doesn't match the Linux IP.
- **Network profile.** The rule doesn't cover the LAN's profile. A wired LAN is often
  Public, so a rule limited to Private never applies. Run
  `Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Profile Any`; `doctor` flags this case.

## `Host key verification failed`

Windows was reinstalled, or sshd's host keys were regenerated. Check the new fingerprint
on Windows (`windows-host.md` step 6), then on Linux remove the old one:

```bash
ssh-keygen -R <WINDOWS_IP>
```

After that, connect once by hand. If Herdr's sidebar offers **Connect** for a rebuilt
machine, that re-pairs it.

## `'hc' is not recognized`

The SSH session doesn't have `hc` on PATH. SSH sessions read the user PATH from the
registry, not from the app's environment. Add `%LOCALAPPDATA%\Programs\herdr-core` to the
user PATH. To see what an SSH session gets:

```bash
ssh winbox "echo %PATH%"
```

## Version mismatch warnings

Run `hc machine update winbox` and `hc machine update winbox-wsl` from Linux. This copies
the controller's `hc` across and restarts that core; its terminals keep running.

## `winbox-wsl` fails but `winbox` works

1. **The by-hand test.** Run it from `wsl.md` step 3; it isolates the problem.
2. **`usage: hc-via-b64`, or `not found`.** The bridge is missing or has CRLF line
   endings (`wsl.md` step 1).
3. **`There is no distribution with the supplied name`.** The distro name in the `--via`
   command is wrong. On Windows, `wsl -l -q` lists the names. Remove the machine and add
   it again with the right name.
4. **`base64: invalid input`.** A different wrapper or a manual edit garbled the argument.
   Reinstall `assets/herdr-via-wsl`.
5. **Hangs.** Something asked a question: a host key prompt or a passphrase.
   `herdr-via-wsl` uses `BatchMode=yes`, so it should fail instead. Run `ssh winbox hc
   --version` by hand once.

## WSL terminals gone after reconnect

WSL stopped the distro when it went idle, and the WSL `hc` core went with it. Check with
`wsl -l -v` after disconnecting. There are two ways to fix it:

- **Keep the distro running.** Add a Task Scheduler task that runs at logon with no
  window:

  ```powershell
  conhost.exe --headless wsl.exe -d Ubuntu-24.04 -e sleep infinity
  ```

  While that process lives, WSL keeps the distro up.
- **Set a longer idle timeout** in `%USERPROFILE%\.wslconfig`. The setting names differ
  between WSL versions, so check `wsl --version` and Microsoft's `.wslconfig`
  documentation for yours. Run `wsl --shutdown` after changing it.

Neither fix has been verified on this setup yet; record what works here.

## Windows desktop Herdr stuck, or Windows terminals gone after disconnect

The core was started over SSH instead of from the desktop. An admin account's SSH login is
elevated, and `hc`'s notes say an elevated core started over SSH can block the same user's
desktop session. Windows also ends a session's processes when it closes. To fix it, open
Herdr on the Windows desktop, or run `hc server start` in a normal desktop terminal, then
reconnect from Linux (`hc machine login winbox`). After that, keep Herdr starting at login.
