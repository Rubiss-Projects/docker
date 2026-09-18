# Tracearr

Tracearr runs alongside Tautulli; do not disable or remove Tautulli as part of Tracearr maintenance.

- URL: https://tracearr.benlawson.dev/
- App: `tracearr:3000`; loopback maintenance access: `127.0.0.1:3040`.
- Plex: `http://plex:32400`; Tautulli import source: `http://tautulli:8181`.
- Health: `/health`. Homepage and Uptime Kuma use the internal Docker URL.
- Start from this directory: `docker compose --env-file .env --env-file .env.secret up -d`.
- Credentials are in git-crypt protected `.env.secret`. The owner's Plex account is linked with login enabled; use Sign in with Plex. The initial local username was `admin`, but Plex login synchronizes it to the Plex username. Local login by the owner's email remains available with `TRACEARR_ADMIN_PASSWORD`. Homepage uses `TRACEARR_API_KEY`.
- The database uses `tracearr_tracearr_postgres`, a Docker-managed Linux volume. This is a necessary exception to relative bind mounts: PostgreSQL rejects the permissions provided by the Windows-backed E: drive. Never remove this volume during updates.
- Redis persists in `./data/redis`; application backups use `./data/backup`.
- Back up the database using Tracearr's backup feature or `pg_dump`; copying the repository alone does not back up the database. Preserve the secret overlay with backups.
- TimescaleDB and Redis start before the app through health-gated Compose dependencies. Deployment ensures Plex is ready before Tracearr and prioritizes Tracearr immediately after the critical startup chain. Plex restarts do not force a Tracearr database restart; Tracearr reconnects automatically.
- Windows nightly maintenance and watchdog bind repair also prioritize Tracearr immediately after `socket-proxy -> uptime-kuma -> plex -> swag`. The main-host deployment job installs this ordering with `python3 scripts/install-tracearr-maintenance.py --apply`. The installer backs up `E:\Scripts\docker-desktop-common.ps1` and preserves task states and maintenance locks.
- Tautulli history was imported on 2026-09-18 (job 1): 8,518 new records, zero skipped, zero errors. All 8,518 records also completed stream-detail enrichment with zero failures. Check import status before starting another run.
