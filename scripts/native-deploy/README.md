# Native Linux deployments

The main-host job runs on BEN-SERVER with `native-docker-ops`; Pi deployments
retain their existing runner and helper. Keep the workflow disabled until the
native runner and its host policy are accepted.

The existing deployment helper selects this adapter with
`DOCKER_DEPLOY_HOST=native-linux`. It renders the current service Compose file
and secret overlays, then applies the root-controlled accepted Linux wiring
from `/etc/docker-ops/native-policy.json`. The policy records released service
keys, existing storage/network identities and the source hashes of fields that
need native replacements. New services and changes to those protected fields
require an explicit policy update. Application environment and ordinary labels
continue to come from the current repository.

An unchanged image pin can use the verified image already imported during the
migration. A new registry digest uses the new source image and the usual pull;
the adapter does not freeze later image updates to migration snapshots.

Before maintenance or container operations, the complete deployment plan must
pass the media mount guard, existing-volume/network checks and service identity
admission. Bind mounts cannot create missing host paths. Dormant game stacks
are outside the released policy. Explicit database-only operations retain their
service selection, including the existing Tracearr upgrade procedure.

Install the non-secret mount policy as
`/etc/docker-ops/media-mount-policy.json`. Both policy files and their directory
must be controlled by root and readable by the deployment account. Keep compiled
recipes in `/var/lib/docker-ops/compiled`, owned by that account with mode 0700;
the generated files contain expanded secrets and use mode 0600. Do not commit
host policies or compiled recipes, print their contents, or upload them as CI
artifacts.

The adapter adds no application schedules, monitoring providers or backup jobs.

## HTTPS startup

The native host policy must bind SWAG's published HTTPS port to the server LAN
address, not all addresses: Tailscale Serve owns HTTPS on its own address.
The NAS administration listener retains its separate LAN-only binding.

The 10GbE link can briefly drop during boot after `network-online.target` has
completed. If Docker cannot bind a published address while restoring a container,
its restart policy does not recover that initial networking failure. Install the
admitted proxy startup unit after the native policy and deployment account pass:

```sh
sudo install -o root -g root -m 0644 scripts/native-deploy/native-https-startup.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now native-https-startup.service
```

The unit starts after Docker finishes setup, takes the existing deployment lock,
applies the adapter's admission checks and starts only the existing SWAG container. It retries a failed
initial start every 15 seconds and remains satisfied after success. It neither
recreates nor restarts a running proxy. Docker restarts also re-run this startup
step. Confirm the unit is active/exited and both LAN HTTPS and Tailscale access
work after a normal host boot.

To remove it, disable/stop `native-https-startup.service`, remove that unit file
from `/etc/systemd/system/`, and run `systemctl daemon-reload`. Stopping this
oneshot unit does not stop the proxy container.

## Normal host shutdown

Install the Docker systemd stop-timeout override on the native host:

```sh
sudo install -o root -g root -m 0644 scripts/native-deploy/docker-shutdown-grace.conf /etc/systemd/system/docker.service.d/shutdown-grace.conf
sudo systemctl daemon-reload
systemctl show docker.service -p TimeoutStopUSec
```

The packaged unit's 90-second limit is shorter than the existing worker stop
grace periods, which reach 31 minutes. Docker honors those container timeouts,
so systemd must allow it to finish before killing the daemon. The override gives
it 35 minutes; idle containers still stop immediately. Increase this bound if a
future service needs a longer grace period. Reloading the unit does not restart
Docker or its containers. The separate UPS emergency-stop policy is unchanged.

To remove this override, remove only `shutdown-grace.conf` from that drop-in
directory and run `systemctl daemon-reload` again.

```sh
sudo python3 -B -m unittest discover -s scripts/native-deploy -p 'test_*.py'
python3 scripts/native-deploy/compose.py --admit homepage plex channels-dvr
```
