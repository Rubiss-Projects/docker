# Homelable

Private office topology and inventory at <https://homelable.benlawson.dev:4443/>.
The hostname must resolve directly to BEN-SERVER (`192.168.50.40`). Port 443
only redirects; keep 4443 private, as for the NAS management listener.

Frontend and backend use proxynet without host ports or a Docker socket.
The backend runs as UID/GID 1000 with persistent SQLite and uploads in `data/`.
Create that directory with owner 1000:1000 before native policy admission.
The native adapter must explicitly admit both services, their pinned images,
proxynet identity, and the canonical `/srv/Docker/homelable/data` bind.
Deploy only through `scripts/native-deploy/compose.py` after admission.

Public defaults are in `.env`; `SECRET_KEY` and the quoted bcrypt
`AUTH_PASSWORD_HASH` are in git-crypt-encrypted `.env.secret`. Login is `ben`.
Generate a unique password; never reuse the upstream default. Preserve single
quotes around the bcrypt hash to prevent Compose dollar interpolation.

Prometheus, Grafana and Uptime Kuma remain the monitoring authorities.
Homelable's status checker is disabled, so canvas state is unknown rather than
a second alert source. Network scanning is manual; bridge networking cannot
discover LAN MAC addresses. MCP, shared live/document views, and Git sync are
disabled. Do not store secrets in inventory notes or upload credentials.

Homepage discovers the frontend labels; Kuma checks `/api/v1/health` through
the frontend, covering its backend connection too. Hardware details and links
are populated through authenticated API calls after deployment. Preserve manual
edits: use incremental node/edge operations, never whole-canvas replacement.

Verify the private HTTPS page, authenticated API access, denied anonymous node
access, public-port redirect, Homepage entry and Kuma monitor after deployment.
Check that NAS access still works on the shared private listener.
