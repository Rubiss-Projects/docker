# Executive health probes

BEN-SERVER's deployment user runs nine application and storage checks every five minutes through its lingering systemd user manager. Each result goes to its own Kuma push monitor. Kuma marks a missing heartbeat down after 450 seconds. The collector uses existing application identities and reports only status or fixed diagnostics. Kuma monitors Google's connectivity endpoint and Cloudflare's trace endpoint every minute. One failed provider raises a warning; both down makes Network & DNS critical. A separate Kuma keyword monitor checks Audiobookshelf's public HTTPS health endpoint through Cloudflare and expects HTTP 200 with OK in the body. The observer is inside the lab, so a full home internet outage also affects its view of the public tunnel.

Run the following from the native checkout to reconcile the nine push and three HTTPS monitors and install the timer. The setup command requires SWAG's existing Kuma integration. Keep the generated file private. If a monitor was recreated, reconcile its ID in the executive dashboard before release.

```sh
set -eu
umask 077
probe_config="$HOME/.config/functional-probes"
mkdir -p "$probe_config" "$HOME/.config/systemd/user"
probe_file=$(mktemp "$probe_config/monitors.XXXXXX")
trap 'rm -f "$probe_file"' EXIT
docker exec -i swag python3 - <scripts/functional-probes/setup-monitors.py >"$probe_file"
mv "$probe_file" "$probe_config/monitors.json"
systemctl --user link "$PWD/scripts/functional-probes/executive-health.service" "$PWD/scripts/functional-probes/executive-health.timer"
systemctl --user daemon-reload
systemctl --user enable --now executive-health.timer
systemctl --user start executive-health.service
```

A tuner in use can supply evidence through its active stream rate. Otherwise the probe requests a short automatically allocated stream, deferring during DVR recording windows. The DVR write check removes its own temporary file. Import checks inspect queue errors without changing downloads. Library checks read one byte from catalogued media. The vault check selects a schema migration marker in a read-only transaction. Backup validation checks the deployed monthly schedule and archive digest. Homebridge supplies a contact sensor reading. Neither sensor state is retained. n8n supplies its latest completed production workflow status. No synthetic automation runs against the worker pool.
