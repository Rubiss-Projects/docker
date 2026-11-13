# Native Linux deployments

The main-host job runs on BEN-SERVER with `native-docker-ops`; Pi deployments
retain their existing runner and helper. The native runner and policy have passed
acceptance, and the workflow is enabled. On a replacement host, hold deployment
until its runner, mounts, restored state and policy pass admission.

The existing deployment helper selects this adapter with
`DOCKER_DEPLOY_HOST=native-linux`. It renders the current service Compose file
and secret overlays, then applies the root-controlled accepted Linux wiring
from `/etc/docker-ops/native-policy.json`. The policy records released service
keys, existing storage/network identities and the source hashes of fields that
need native replacements. New services and changes to those protected fields
require an explicit policy update. Application environment and ordinary labels
continue to come from the current repository.

Native checkout writes use a temporary private umask so decrypted secrets are
private from creation. The caller's umask is restored on success or failure.
After a successful checkout update, the helper restores Git-tracked file
permissions: public source is 0644 (0755 for Git executables), git-crypt files
are 0600, and their parent directories are 0755. The standalone `.git` directory
and its git-crypt key directories are 0700; local key files are 0600. This removes inherited NTFS
permissions without traversing untracked application data or changing ownership.
It refuses foreign-owned paths, unexpected file types and symlinked parents;
public tracked symlinks remain untouched. Run a read-only plan with
`python3 scripts/native-deploy/checkout_permissions.py --repo /srv/Docker` before
an initial repair, then add `--apply` as the checkout owner. Secret files can
still be read by the deployment account for Compose environment loading.

An unchanged image pin can use the verified image already imported during the
migration. A new registry digest uses the new source image and the usual pull;
the adapter does not freeze later image updates to migration snapshots.

Before maintenance or container operations, the complete deployment plan must
pass the media mount guard, existing-volume/network checks and service identity
admission. Bind mounts cannot create missing host paths. Stopped game stacks
retain their data and require admission just like running stacks. Changed stacks
pull their pinned images even when stopped; they remain stopped unless
`DOCKER_DEPLOY_START_STOPPED=true` explicitly requests startup. Pulling an image
does not run game updates against the saved data; those happen on the next start.
Explicit database-only operations retain their
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
applies the adapter's admission checks, restores any missing admitted SWAG bridge
attachments, and starts only the existing SWAG container. A failed Docker boot
start can leave either attachment missing, even though both remain in Compose.
Recovery checks the existing container, image and network identities, preserves
aliases, and rejects unexpected networks or unsupported missing static settings.
It never attaches the Docker socket proxy to the backend network. It retries a failed
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
