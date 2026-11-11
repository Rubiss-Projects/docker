# Previous-host operations — archived

BEN-SERVER now runs native Ubuntu. `/srv/Docker` is the deployment checkout;
`/mnt/e/Docker` is its compatibility path. Use the
[native deployment runbook](../scripts/native-deploy/README.md), admitted host
policies and existing systemd units. The reviewed automatic startup path has
passed a normal boot with the existing application identities retained.

The following source is archived in place so its paths and rollback definitions
remain intact. It is not a list of tasks to install or enable:

- [`scripts/docker-watchdog/`](../scripts/docker-watchdog/README.md): previous
  Windows Docker Desktop/WSL watchdog and installer.
- [`scripts/windows-loopback-recovery.md`](../scripts/windows-loopback-recovery.md):
  historical Windows loopback diagnosis.
- [`caddy/`](../caddy/README.md): retired Plex/Channels proxy, Windows watchdog
  integration and certificate-copy definitions.
- Windows-only command examples in service history and retained `.ps1` wrappers:
  previous-host context, not native controller or deployment commands.

Plex and Channels use admitted host networking and the media firewall. SWAG
uses its admitted backend and private socket-proxy networks; never put the socket
proxy on the backend network. The native HTTPS starter recovers SWAG after Docker
setup. Do not recreate the old blanket recovery or workflow-import behavior.

Routine CI validates the active native deployment and media paths. Archived
Windows watchdog installation and retired Caddy integration are no longer routine
PR jobs. A deliberate rollback change must explicitly validate the affected
archived components before use.

Original disks, current application state and migration recovery archives remain
retained. Archiving these instructions does not authorize disk erasure, volume
pruning, torrent removal, or starting a second copy of a service. Reconcile the
newest writes and endpoint ownership before any rollback.
