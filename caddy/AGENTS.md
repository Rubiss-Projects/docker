# Archived Caddy rollback reference

The native migration retired this proxy. Its service and certificate timer are
disabled, and the temporary gaming-PC proxy is stopped. Do not install, start,
or add monitoring for it during routine maintenance. Current operations use
`../scripts/native-deploy/README.md` and direct Plex/Channels native routes.

The following constraints describe only an explicitly chosen rollback, which
must reconcile current state and routing before activating a single owner.

Native Ubuntu service, not a Docker Compose stack. Read README.md before changing
public routing, TLS, watchdog or monitoring. Keep the Unix admin socket private;
LAN monitoring must expose only the explicit read-only resources. Preserve the
existing Plex LAN path, all authentication/bandwidth settings and other router
rules. Never remediate Caddy by restarting Docker Desktop/WSL. Source changes
must go through the root PR/review process.
