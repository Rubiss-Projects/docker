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

```sh
sudo python3 -B -m unittest discover -s scripts/native-deploy -p 'test_*.py'
python3 scripts/native-deploy/compose.py --admit homepage plex channels-dvr
```
