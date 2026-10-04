# Caddy

Native Ubuntu service, not a Docker Compose stack. Read README.md before changing
public routing, TLS, watchdog or monitoring. Keep the Unix admin socket private;
LAN monitoring must expose only the explicit read-only resources. Preserve the
existing Plex LAN path, all authentication/bandwidth settings and other router
rules. Never remediate Caddy by restarting Docker Desktop/WSL. Source changes
must go through the root PR/review process; deploy the native service explicitly.
