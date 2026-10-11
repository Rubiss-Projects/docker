#!/usr/bin/env bash
# Sourced by the deployment helper after pulling images; uses its compose/log helpers.
upgrade_tracearr_database() (
  set -Eeuo pipefail
  local desired current target pending backup_dir backup
  desired=$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["timescale"]["image"])')
  current=$(docker inspect tracearr-db --format '{{.Image}}')
  target=$(docker image inspect "$desired" --format '{{.Id}}')
  pending=$(compose exec -T timescale psql -X -U tracearr -d tracearr -At -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_available_extensions WHERE name IN ('timescaledb','timescaledb_toolkit') AND installed_version IS DISTINCT FROM default_version;")
  if [[ "$current" == "$target" && "$pending" == 0 ]]; then
    return 0
  fi

  # Native host storage keeps this backup outside the database's Docker disk.
  umask 077
  backup_dir=${DOCKER_TRACEARR_BACKUP_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/docker-backups/tracearr}
  mkdir -p "$backup_dir"
  backup=$(mktemp "$backup_dir/pre-upgrade-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.dump")
  compose exec -T timescale pg_dump -U tracearr -d tracearr -Fc > "$backup"
  compose exec -T timescale pg_restore --list < "$backup" > /dev/null
  log "Tracearr database backup: $backup"

  # Stop writers, update PostgreSQL within its pinned major, then migrate the
  # extensions before the regular compose up resumes the application.
  compose stop tracearr
  compose up -d --no-deps --wait --wait-timeout 180 timescale
  compose exec -T timescale psql -X -U tracearr -d tracearr -v ON_ERROR_STOP=1 \
    -c 'ALTER EXTENSION timescaledb UPDATE;' \
    -c 'ALTER EXTENSION timescaledb_toolkit UPDATE;'
)
