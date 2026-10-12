# APC UPS monitoring

The BR1500MS2 data cable is connected directly to Ben-server. Native Windows
apcupsd reads USB telemetry; Homepage's official `apcups` widget reads its NIS
status protocol. This is a host service, not a Docker Compose stack. No USB/IP,
public proxy, additional container or firewall opening is needed.

**Monitoring only:** this setup cannot provide unattended safe shutdown.
`apccontrol.bat` deliberately performs no actions, and battery/runtime/time
thresholds and `KILLDELAY` are zero. Do not replace the handler with the upstream
shutdown handler until the PCs, NAS and networking have a coordinated and tested
shutdown plan. Do not use `apctest`, `--killpower`, or an unplug test for telemetry.

## Installed Windows setup

- Upstream release: [apcupsd 3.14.14 Windows](https://sourceforge.net/projects/apcupsd/files/win-binaries%20-%20Stable/3.14.14/).
- Installer SHA-256: `a4e99ad5b6cd8c9aa9afa2471eabb69a4dc9a494eed8a4d63929c19717845952`.
- Installer signature was valid (Adam Kropelin); driver catalog signature was
  valid (Jernej Simoncic). This is an old Windows release; compatibility was
  verified on this server, not assumed from its supported-OS list.
- Install directory: `C:\ProgramData\apcupsd`. SYSTEM and Administrators have
  full control; Users have read/execute. Preserve these ACLs on updates.
- Windows service: `Apcupsd`, automatic start. Native binaries live in `bin`,
  configuration/handler in `etc\apcupsd`, events in `var\log`.
- USB parent `USB\VID_051D&PID_0002` uses the package's WinUSB binding. Do not
  install it on the separate HID battery child. The original binding was
  Microsoft's `input.inf`.
- NIS listens only on `127.0.0.1:3551`. Docker Desktop's
  `host.docker.internal:3551` path was tested from the Homepage container.
  NIS has no authentication; keep it off the LAN and public internet.

The files here are the reproducible configuration. Changing them in Git does
**not** deploy the native service; deployment automation only updates Homepage.

## Reinstall or update deliberately

1. Stop only the `Apcupsd` service if it exists. Preserve its current configuration
   and driver information privately. Never run the upstream installer unattended:
   its default options install the driver and start the service.
2. Download the release from upstream; verify the checksum and valid Authenticode
   signature. Extract it without executing the installer. Copy `apcupsd.exe`,
   `apcaccess.exe`, `mingwm10.dll`, and `pthreadGCE.dll` from `bin`, and the complete
   `driver` directory, into the layout above. Do not copy `shutdown.exe` or
   `apctest.exe` into this monitoring installation.
3. Create `var\log`; install this configuration and no-action handler before
   starting anything. Preserve administrator-only write access.
4. Verify `driver\apcupsd.cat` has a valid signature before staging its INF with
   `pnputil /add-driver C:\ProgramData\apcupsd\driver\apcupsd.inf /install`.
   The initial install required trusting that exact verified signing certificate
   in LocalMachine TrustedPublisher (thumbprint
   `1D93780CC466FD8C18B306BCA674069A6E507127`). This is publisher trust, not a new
   root certificate. Never disable signature enforcement or Secure Boot. If
   Windows rejects the package, stop and investigate instead of bypassing it.
5. Register with `C:\ProgramData\apcupsd\bin\apcupsd.exe /quiet /install`, then
   start `Apcupsd`. Read status with the command below and verify the model,
   current timestamp, ONLINE/ONBATT state and zero shutdown thresholds. A USB
   device appearing in Device Manager alone does not prove telemetry works.
6. Verify Homepage's card under Hardware. A communication failure must remain
   visible; do not substitute fabricated or cached healthy readings.

```powershell
& C:\ProgramData\apcupsd\bin\apcaccess.exe status
Get-Service Apcupsd
Get-NetTCPConnection -State Listen -LocalPort 3551
```

`LOADPCT * NOMPOWER / 100` estimates watts; this model reports nominal power as
900 W. Estimated runtime and the programmed battery date do not establish battery
health or a passed runtime test. The earlier rear wiring-fault indication still
requires resolution independently of these telemetry readings.

## Backout and Linux migration

Remove the Homepage card if monitoring is retired. Stop `Apcupsd`, unregister
with `apcupsd.exe /quiet /remove`, and restore the UPS parent's Microsoft HID
driver through Device Manager if returning to PowerChute/Windows battery support.
Remove the apcupsd driver package and the exact TrustedPublisher certificate only
after checking no other installed device/software depends on them. Retain logs
and configuration until backout is confirmed; no UPS output change is required.

On native Ubuntu use the distribution's native UPS service and Linux paths;
do not transplant this Windows configuration. Review the service's packaged
shutdown/kill-power hooks, Docker-to-host routing and local firewall together.
The current localhost/`host.docker.internal` pairing is specifically verified
for Docker Desktop and must be replaced or explicitly tested on native Linux.
Keep network equipment powered for shutdown signaling and finish server writes
before stopping NAS storage. That coordinated policy remains separate work.

Reference: [Homepage APC UPS widget](https://gethomepage.dev/widgets/services/apcups/).
