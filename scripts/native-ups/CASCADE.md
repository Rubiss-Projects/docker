# NAS shutdown cascade and ordered recovery

This extends the admitted Pi collector; it does not replace either computer's
30-second UPS guard. No outlet switching or physical outage is needed to install
the files. Leave both new controls disabled until the owner approves acceptance.

## Policy

- BEN-PC and BEN-SERVER begin their existing graceful shutdown after 30 seconds
  of confirmed battery operation. BEN-SERVER retains its 45-second container
  grace (10 seconds on critical battery).
- The server's UPS-only helper caps the subsequent Docker service stop at 15
  seconds using a **runtime** drop-in. The 35-minute maintenance setting remains
  on disk and returns at reboot. It stops Docker/socket, stops `srv-Media.mount`,
  verifies the mount is absent, and reports release over authenticated SSH.
- The Pi requests NAS shutdown on the first poll after this release and the
  server going offline. There is **no additional NAS settling timer**. A failed
  drain has a three-minute ceiling measured from the original battery event,
  not from server shutdown. This leaves room for the existing 60-second maximum
  drain call plus the bounded release helper. Critical UPS status skips that
  ceiling; at that point preserving NAS storage takes priority over unavailable
  clients. Network loss alone does not authorize early NAS shutdown.
- QNAP's native UPS policy remains an independent fallback if the Pi coordinator
  or SSH fails. At acceptance, select full shutdown rather than standby and a
  three-minute fallback using the supported UPS settings. Keep low-battery
  protection. Verify this against measured runtime before enabling; do not rely
  on a three-minute reserve when the UPS reports less remaining runtime.
- Recovery requires 180 seconds of valid uninterrupted utility power and at least
  50% charge. NAS and BEN-PC may wake first. BEN-SERVER waits for authenticated NAS
  readiness: the admitted pool ONLINE, Media dataset mounted read/write, the data
  directory present and NFS threads running. Native host mount admission remains
  the final protection before containers regain writer ownership.
- Only hosts recorded at the outage are candidates. NAS shutdown is tied to its
  recorded boot ID; a recovered NAS cannot be shut down by a stale command.
  Shutdown requests, outage IDs and wake attempts persist across Pi restarts.
  Unknown UPS status never authorizes waking. Five attempts, 60 seconds apart,
  remain the maximum. Unresolved intent/errors and exhausted attempts require
  operator reconciliation; do not delete state to make a check pass.

## Authentication and installation preparation

Use two distinct Ed25519 keys, generated on their originating hosts. Private keys
stay root-owned mode 600 under `/etc/ups-cascade`. Use the supplied SSH config,
with host keys pinned through the already trusted administration connections.
Never place passwords or private keys in Git. Do not reuse the temporary wake
test keys, grant a general root shell, or disable host-key checks.

1. Pi: install `pi_recovery.py`, `nas_cascade.py`, `native_ups_guard.py` root-owned
   under `/usr/local/lib/ups-pi-recovery`. Retain observe-only service arguments.
2. Server: install the reviewed guard, `server_storage_release.py`, and
   `ups-storage-release.service`. Do not yet set `NATIVE_UPS_CASCADE=1` in the
   root-controlled `/etc/nut/native-ups.env`. The helper checks a current-boot
   committed UPS intent before doing anything, even when started manually.
3. NAS: install `qnap-ups-command.sh` root-owned mode 755 at
   `/etc/config/ups-cascade/command.sh`, with root-controlled parent directories.
   This persistent configuration path is separate from the Media data tree.
   It only accepts `status` or `shutdown <current-boot-uuid>`. Normal BusyBox
   poweroff signals init, which runs QNAP's `/etc/init.d/rcK`; never use `-f`.
4. Authorize the Pi's dedicated NAS key for `rubiss` with `from="192.168.50.216"`,
   `no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty`, and a forced
   command invoking **only** this root-owned helper through sudo:
   `sudo -n /etc/config/ups-cascade/command.sh "$SSH_ORIGINAL_COMMAND"`.
   Permit only this exact helper in the NAS sudo policy. Validate with visudo and
   verify persistence through the acceptance reboot; do not overwrite QNAP's
   generated sudo policy or enable the disabled built-in admin account.
5. Authorize the server's reporting key on the Pi for `rubiss`, restricted to
   `from="192.168.50.40"` and the same forwarding/PTY restrictions, forced to
   `sudo -n /usr/bin/python3 -B /usr/local/lib/ups-pi-recovery/nas_cascade.py "$SSH_ORIGINAL_COMMAND"`.
   The sudo rule must permit only that fixed root-owned script. It accepts only
   `begin <server-boot>` and `released <server-boot> <pi-outage-id>`, not shell text.
   An active Pi outage and matching begin handshake are required for release.

The example command strings above describe the forced-command payload; escape
their double quotes when writing an `authorized_keys` entry. Preserve existing
authorized keys and sudo rules. Test denied commands as well as accepted status
reads before enabling either mutation path.

## Non-disruptive acceptance

Run `python3 -B -m unittest discover -s scripts/native-ups -p 'test_*.py'` on Linux.
Validate units with `systemd-analyze verify` and the QNAP helper with `sh -n`.
Using the restricted NAS key, `ssh -F /etc/ups-cascade/ssh_config nas status` must
return the current boot UUID and `ready:true`. Verify arbitrary commands fail.
Do not send `shutdown`, stop the mount, start the release service with an intent,
inject battery readings into live NUT, or enable mutation flags during this stage.

Inspect `state.json` and the journal for `nasReady`, `wouldShutdownNas`,
`nasShutdownEnabled`, `wakeEnabled`, `pending`, and `cascade.error`. Before release,
connect stale observations, held candidates and exhausted attempts to the existing
operator notification path; journals alone are not unattended acceptance.

## Owner-approved disruptive acceptance

1. Stop storage consumers in the approved maintenance window. Prove NAS graceful
   shutdown and wake through MAC `24:5e:be:78:08:94`, with the production Pi wake
   function, and verify the pool, exports and restricted SSH access after boot.
2. Exercise the complete cascade with a bounded test harness using isolated input
   and state, invoking the same reviewed shutdown/wake functions. Prove the
   server's mount is released before NAS shutdown; confirm no extra delay. Test
   return-during-shutdown, low battery, missing status, failed SSH and controller
   restart in pure policy tests before any live scenario.
3. Verify NAS-first recovery through real mount admission and exact-container
   restoration. Verify Windows guard recovery too. Restore test credentials and
   configuration; preserve logs/receipts without credentials.
4. Verify Pi/network battery-backed outlets, Pi boot/service persistence and UPS
   output-return behavior. A long outage can remove Pi power. Do not claim an
   exercised battery-exhaustion recovery from a normal computer wake test.

## Final enablement and rollback

After review, accepted tests, notification wiring, and reconciliation of all
pending state, enable `NATIVE_UPS_CASCADE=1` on BEN-SERVER. Add a Pi systemd drop-in
resetting `ExecStart` to the installed script with **both** `--enable-wake` and
`--enable-nas-shutdown`; keep the base unit observe-only. Apply the QNAP fallback
through its supported settings. Verify startup enablement and fresh live state
with both booleans true and no stale intent. No enabled claim until these checks
pass. Record exact installed hashes, QNAP setting values and test receipts here.

Rollback removes the two Pi mutation flags and the server cascade environment
flag, restoring the QNAP five-minute standby policy if required. Preserve the
computer shutdown guards, mount admission, pending restore manifests and UPS
collector. Reconcile an already committed shutdown instead of cancelling it.

## Current acceptance

Implementation only; mutation flags remain disabled. BEN-SERVER and BEN-PC have
passed separate normal shutdown/wake tests after BIOS PCI-E wake enablement.
The NAS's QXG-10G1TD reports magic-packet support and `Wake-on: g`; its PCIe device
and QNAP WOL setting are enabled. NAS shutdown/wake and integrated cascade tests
still require the owner's go-ahead.
