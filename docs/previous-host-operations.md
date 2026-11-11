# Previous-host operations

BEN-SERVER runs native Ubuntu. `/srv/Docker` is the deployment checkout;
`/mnt/e/Docker` is its compatibility path. Use the
[native deployment runbook](../scripts/native-deploy/README.md), admitted host
policies and installed systemd units.

The retired Windows Docker Desktop/WSL watchdog, host-memory collector,
Transmission ETW diagnostics, Windows Compose bridge and Caddy proxy source
were removed during final migration cleanup. Their historical definitions remain
in Git history. Do not reinstall their scheduled tasks, blanket recovery loops,
certificate-copy timer or nightly Docker restart on the native server.

Plex and Channels use admitted host networking and the media firewall. Plex's
accepted public TCP 18443 mapping reaches native TCP 32400 directly. Channels
At Home uses `192.168.50.40:8089`; Away From Home remains deferred. SWAG retains
its admitted backend and private socket-proxy networks. The native HTTPS starter
recovers SWAG after Docker setup. Never attach the socket proxy to the backend
network or import old recovery workflows.

Original disks and retained migration recovery archives are separate from this
source cleanup. Removing obsolete helpers does not authorize disk erasure,
volume pruning, torrent removal, or starting a second application owner. Any
rollback must first reconcile newest application writes, current routes and
explicitly admitted storage.
