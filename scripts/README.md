# Host operations scripts

BEN-SERVER uses native Linux; the Pi has its own deployment context. Main-server
Compose operations use `native-deploy/compose.py` and its admitted host policy.

| Source | Current purpose |
| --- | --- |
| `native-deploy/` | Storage/image/network admission, mount guard, checkout permissions and HTTPS boot recovery |
| `native-media-network/` | Host-networked Plex/Channels preparation and INPUT firewall |
| `native-host-network/` | Native Ethernet DNS configuration, retaining DHCP addressing and routes |
| `native-ups/` | Existing ordered UPS shutdown policy and reviewed recovery source |
| `deploy-changed-service-folders.sh` | Trusted main-push deployment for the native host and Pi |
| `grafana-maintenance.py`, `kuma-maintenance.py` | Scoped maintenance around existing deployment/lifecycle operations |
| `sunday-edge-autoscale.py`, `native-sunday-edge/` | Native DFS controller and fixed SSH entry points; shared deployment admission and resource guards |
| `login-sunday-edge-registry.py` | Private registry authentication through stdin |
| `sync-contribution-forks.py`, contribution-fork installer/units | Existing contribution repository synchronization |
| `check_image_pins.py` | Image pin validation used by CI |
| `runner-docker-*` | Runner Docker authentication guidance/examples |
| `test_*.py` | Focused coverage for the corresponding active operations |

The Windows watchdog, WSL memory collection, ETW diagnostic image, Windows
Compose bridge and retired maintenance-hook installer are removed. Their source
remains in Git history. Do not recreate these tasks or recurring backup jobs as
part of migration cleanup. Preserve the existing Lazywarden setup.
