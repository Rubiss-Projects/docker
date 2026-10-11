# Docker Desktop watchdog

Versioned source for the Windows scripts installed in `E:\Scripts`. The minute
task remains `Start Docker Desktop if not running`. Image updates and service
deployments do not install these scripts automatically.

## Recovery policy

A failed WSL command, integration socket, or Windows Docker API is a degraded
control plane, not proof that existing streams stopped. Broad automatic recovery
requires all of the following:

1. The same backend failure survives three health observations.
2. Windows has been up for at least ten minutes.
3. Channels DVR, Plex, Sonarr and Radarr all fail Windows-native HTTP requests on
   **both** `127.0.0.1` and `192.168.50.40`, for three observations 30 seconds apart.
4. The backend failure still exists after those observations, and the existing
   ten-minute cooldown / three-restarts-per-hour limit permits recovery.

Any HTTP response, including 401/403/500, vetoes a broad restart. This is evidence
of a responding application, **not** a claim that it is healthy. A partial reply,
missing curl executable, incomplete result, or unknown boot time also withholds
recovery. The probes bypass proxies, use literal addresses, and have bounded
process and request deadlines. Keep the LAN address current if the host moves.

The CLI restart gets a fresh availability check immediately before mutation.
Docker then gets the full 600-second readiness wait (previously capped at 180).
Hard recovery rechecks boot grace and sustained service unavailability; WSL
shutdown and Windows reboot each recheck availability too. Existing shared locks,
recovery inventory, and six-hour Windows reboot cooldown remain in place.

The unconditional 05:00 restart is retired. Installation disables that task and
replaces its entry point with a compatibility wrapper for the normal watchdog,
so re-enabling it does not restore unconditional restarts. The minute task no
longer skips 05:00–05:05. Explicit maintenance still uses the shared lock.

Individual application/mount failures retain targeted repair. A resumed recovery
journal selects stopped containers and confirmed mount failures, rather than
recreating every previously running stack. Failed inspection defers that repair;
an RPC health timeout alone does not select a running stack for recreation.

Tradeoff: a partial outage with another service still responding can require
operator intervention. The watchdog logs a degraded condition and returns a
nonzero exit code instead of sacrificing working services to repair its probes.
The existing notification integration only announces admitted recovery attempts;
withheld attempts are recorded in the watchdog log.

## Validate and install

Run focused tests on Windows (Windows PowerShell 5.1 is supported):

```powershell
powershell -NoProfile -File scripts\docker-watchdog\test-existing-watchdog.ps1
powershell -NoProfile -File scripts\docker-watchdog\test-install.ps1
```

After review and merge, run elevated on Ben-Server:

```powershell
powershell -NoProfile -File E:\Docker\scripts\docker-watchdog\install.ps1
```

The installer rejects drift from the audited original scripts or its last
installation manifest. It disables task scheduling, lets active recovery finish,
holds the shared lock, backs up scripts/task definitions, installs the files,
and runs both entry points with `-ValidateOnly`. It checks container IDs **and
start times** before/after. No recovery or restart is used as an installation
test. Failures restore prior scripts and task enabled states.

The existing notification URL is extracted as a literal without evaluating the
old script, and preserved in host-only `docker-watchdog-notifications.json` with
the old script's ACL. Neither that file nor backups belong in Git. The installed
sentinel Bash script, Grafana helper, and native Caddy helper remain dependencies;
this change does not replace them.

Read-only live checks:

```powershell
powershell -NoProfile -File E:\Scripts\start-docker-desktop.ps1 -ValidateOnly
. E:\Scripts\docker-desktop-common.ps1
Get-DockerServiceAvailability
```

For backout, disable the two schedules and wait for active recovery to finish,
acquire `Enter-DockerOperationLock`, then restore the backed-up scripts and
installation manifest (remove the manifest if the backup predates it). Restore
the saved task enabled states and release the lock. Keep the minute watchdog
enabled. Backout itself does not need a Docker restart.

## Incident behind this change

On 2026-10-11, WSL launch timeouts at 15:52–15:54 EDT triggered broad recovery.
The Windows Docker CLI still captured 35 running stacks at 15:54:04, and the
operator reported an uninterrupted Channels DVR stream before recovery.
There was no independent service-outage check. WSL shutdown failures and the
Windows reboot occurred *after* recovery began, so they do not establish that
applications were initially unavailable. A later successful cold start took
about 210 seconds, longer than the former 180-second readiness cap.
