# Transmission guidance

Transmission runs on native Ubuntu through the admitted deployment adapter.
Use `NATIVE-MONITORING.md` for the existing Telegraf probes and Grafana metrics.

## Storage and retention

- Preserve the external `transmission_config` volume and its ownership.
- The admitted NAS mapping exposes the media tree at `/data`. Downloads use
  `/data/downloads`, including its existing category and incomplete directories.
- Keep a single parent data mount so imports and cross-seeds can use hardlinks.
  Never replace admitted mounts with empty local directories.
- Never remove a torrent registration, its files or partial data without the
  owner's immediate, specific approval. Preserve completed seeding torrents.
- Do not add bandwidth caps, ratio/idle limits or seeding queues as a stability
  fix. The owner requested that all retained torrents remain resumed for seeding.

## Health and recovery

`init/10-health-probe.sh` installs `scripts/rpc-health.py` in the container.
Its functional RPC health check validates session statistics and inventory;
a listening port alone does not prove the daemon works. The native host probes
retain the existing metric history without exposing the Docker socket.

Docker's `unless-stopped` policy handles exited containers. The owner retired
health-check-triggered n8n restart loops. An unhealthy check alone does not cause
an automatic restart. Inspect RPC, host responsiveness, logs and the NAS mount
before intervening; failures use the existing Grafana channels.

## Operations

Use the normal adapter for lifecycle changes:

```sh
cd /srv/Docker
python3 -B scripts/native-deploy/compose.py --stack transmission -- up -d
```

RPC access is port 9091; peer traffic uses TCP/UDP 51413. Credentials belong only
in the encrypted secret overlay and private installed probe configuration.
Use RPC headers for token negotiation; never print authentication values.

`scripts/cross-seed-complete.sh` retains the existing completion notification.
Preserve the existing functional Docker-health monitor and its history during
label changes. Keep the native probe/installer and their focused tests when
updating monitoring. Retired Windows and one-time migration helpers remain in
Git history.
