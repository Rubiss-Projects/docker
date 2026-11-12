# Pi UPS ownership and wake recovery

Preparation is separate from USB ownership. Do not move the cable until the
operator confirms the handoff, and request each computer shutdown test separately.
Never cut UPS output or simulate battery failure as part of a computer wake test.

## Admitted hardware

- BEN-SERVER: ASUS TUF GAMING Z490-PLUS (WI-FI), active TX401/AQC113 at
  `192.168.50.40`, MAC `58:d8:12:91:1c:89`. The adapter reports magic-packet
  support and `Wake-on: g`. `usb/91-ups-wake.yaml` preserves it through Netplan.
- BEN-PC: ASUS ROG STRIX Z790-E GAMING WIFI, Intel I226-V at `192.168.50.209`,
  MAC `58:11:22:bb:86:30`. Driver magic-packet and S5 wake settings are enabled.
  Disable Windows Fast Startup. Allow ICMP echo only from the Pi for inventory.
- BEN-PI: `192.168.50.216`, wired `eth0`. Reserve these addresses in DHCP.
- UPS: APC BR1500MS2, USB `051d:0002`, serial `0B2234N12112`.

Both motherboards require their BIOS PCI-E wake setting; verify during the
separately approved tests. Preserve standby power (ErP settings can disable it).
No claim of successful wake-from-shutdown follows from driver settings alone.

## Preparation without a power transition

Install `nut-server` and `nut-client` on the Pi with server, monitor, driver target
and enumerator units masked. Keep `nut-monitor.service` masked permanently:
the existing host guards remain shutdown owners, and no UPS killpower is used.

Stage the exact UPS driver definition, `MODE=netserver`, `pi-upsd.conf`, and
the existing NAS secondary-monitor identity/password privately under `/etc/nut`.
Do not put the password in this repository. Install the dedicated firewall table
and unit, and `pi-nut-network.conf` as the NUT server drop-in. This exposes only
3493 to BEN-SERVER, BEN-PC and the NAS, without changing other host firewall rules.

The Pi endpoint requires authenticated TLS for native shutdown decisions. Issue
a dedicated private CA and a server certificate with IP SAN `192.168.50.216`,
then import the server key/certificate as `ups-pi` into the Pi's root-controlled
NSS database `/etc/nut/tls` (Ubuntu NUT uses NSS). Install only the CA public
certificate as `/etc/nut/pi-ups-ca.pem` on BEN-SERVER, owned by root and not
writable by other users. The guard requires STARTTLS, TLS 1.2 or later, chain
verification against this dedicated CA, and matching IP identity; failure never
falls back to plaintext. Verify both a valid connection and rejection of an
untrusted certificate before switching the endpoint. Preserve the private CA
securely for renewal; never place private keys in the repository.

Install `pi_recovery.py`, `nas_cascade.py`, and `native_ups_guard.py` under
`/usr/local/lib/ups-pi-recovery`, with `ups-pi-recovery.service` in observe mode.
Run the guard, restoration and Pi policy unit tests on Linux, and validate units
and firewall syntax. Do not enable wake during preparation.

## Controlled cable handoff

1. Confirm fresh online UPS readings on all clients, no battery deadline or
   current-boot shutdown intent, and saved previous configurations for rollback.
2. Ask the operator to move **only the USB data cable** from BEN-SERVER to BEN-PI.
   Keep all UPS power cables unchanged. Keep this interruption short and do it
   only while utility power is stable. Loss of status alone must not power off
   either computer.
3. Stop the former server USB driver, unmask/start the Pi driver and server
   (not `nut-monitor`), and verify the exact serial, fresh status and charge.
4. Set BEN-SERVER's `/etc/nut/native-ups.env` to
   `NATIVE_UPS_HOST=192.168.50.216` with the reviewed guard that admits this address.
   Restart its guard only after the Pi reports online and no deadline is active.
   Its restore helper must use the same endpoint.
5. Add verified STARTTLS to the protected Windows guard before retargeting it
   from `.40` to `.216`, using the same dedicated CA and matching Pi identity;
   prohibit plaintext fallback. Preserve the
   shutdown policy and drain hash. Update its admission payload hash atomically
   while the task is stopped, then start and verify a fresh online observation.
6. Use the NAS's supported UPS network-slave setting to select `.216`, retaining
   its monitor identity and five-minute protection delay. Verify current status.
7. Retarget only the native Telegraf UPS input to `.216`; retain existing outputs,
   dashboard and alerts. Validate collection before restarting Telegraf.
8. Run Pi recovery in observe mode and check both live host identities and UPS
   readings. Retire the old server driver only after all clients pass acceptance.

For backout, return the USB cable and all client endpoints to BEN-SERVER's saved
configuration. Never run competing USB owners. Do not restore stale observation
or intent files over current outage state.

## Wake policy and tests

The Pi remembers hosts reachable during the 20 seconds preceding a confirmed
battery/critical event. It waits for 180 seconds of uninterrupted valid utility
status and at least 50% charge, then sends up to five magic packets per pending
host, at least 60 seconds apart. A process restart resets stability and inventory;
pending candidates persist. Candidates clear only after being observed offline
and then reachable again after stability. A still-reachable host can be draining
applications (Docker allows 35 minutes), so ping alone never clears it. After
45 stable minutes, still-reachable candidates are held for operator reconciliation
and cannot receive automatic wake packets. This timeout resets on controller
restart; an already-recorded hold persists.
An unknown reading resets the stability timer and never authorizes waking.

Observe mode records candidates without sending packets. Enable automatic wake
only after separately approved normal-shutdown/wake tests of each computer,
using a systemd override adding `--enable-wake`. Ordinary manual shutdowns outside
an outage do not generate candidates. ICMP is a conservative reachability proxy,
not proof that an outage caused a shutdown; a computer manually stopped during
an outage or while its candidate is still pending can be included. A brief outage
can leave an unresolved candidate even if the computer never committed shutdown.
Retry exhaustion and unresolved holds require operator reconciliation.

Keep the Pi and networking on battery-backed outlets. This change introduces no
Pi shutdown or UPS outlet policy. If battery power is exhausted, the Pi can lose
power; automated recovery then depends on the UPS restoring output and the Pi
booting. A Pi restarted after an outage begins cannot reconstruct computers that
were never recorded. BIOS AC-recovery and full battery-exhaustion behavior remain
separate acceptance work, not part of the normal shutdown/wake tests.
