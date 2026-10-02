SWAG starts after socket-proxy, Uptime Kuma and Plex. Kuma HTTP readiness alone
does not establish that its Socket.IO login handler is ready: the server sends
`info` before finishing that connection's initialization.

The `init-kuma-initial-info` s6 oneshot runs after mod package installation and
before `init-mod-swag-auto-uptime-kuma-install`. It installs the same bounded
initial-info wait that recovered this server, then the original mod performs its
normal login and monitor sync. Both read-only Compose mounts are necessary.
The upstream module's original and patched hashes are checked; an unreviewed
upstream change stops the patch instead of changing unrelated code.

This survives both restart and recreation. `/custom-cont-init.d` runs after mods,
so it cannot resolve this particular startup race.

Validation: `python3 -m unittest discover -s swag -p 'test_*.py'`. Before deployment,
place public proxy monitors in Kuma maintenance and retain the running module
and Compose definition. Recreate only SWAG using its existing image. Check the
patch marker, nginx configuration and verified HTTPS routes. If startup fails,
restore the prior Compose definition and tested module before returning SWAG;
do not reset Kuma credentials or monitors.
