#!/usr/bin/env bash
# Sourced by the deployment helper after pulling images; uses its compose/log helpers.
upgrade_tracearr_database() (
  set -Eeuo pipefail
  local desired current target pending backup_dir backup container
  desired=$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["timescale"]["image"])')
  target=$(docker image inspect "$desired" --format '{{.Id}}')

  # Native host storage keeps backups outside the database's Docker disk.
  umask 077
  backup_dir=${DOCKER_TRACEARR_BACKUP_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/docker-backups/tracearr}
  container=$(docker ps --all --quiet --filter 'name=^/tracearr-db$')
  if [[ -z "$container" ]]; then
    # After compose down there is no old container to start for pg_dump. Save
    # the stopped cluster before starting the new image. Never create empty
    # replacement state for this existing service (see Tracearr's AGENTS.md).
    docker volume inspect tracearr_tracearr_postgres > /dev/null
    mkdir -p "$backup_dir"
    backup=$(mktemp "$backup_dir/pre-start-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.tar")
    docker run --rm --network none --read-only \
      --mount type=volume,source=tracearr_tracearr_postgres,target=/source,readonly \
      --entrypoint /bin/sh "$desired" \
      -c 'test -s /source/PG_VERSION && test "$(cat /source/PG_VERSION)" = 18 && tar -C /source -cf - .' > "$backup"
    tar -tf "$backup" > /dev/null
    log "Tracearr stopped-cluster backup: $backup"
    compose up -d --no-deps --wait --wait-timeout 180 timescale
  elif [[ $(docker inspect tracearr-db --format '{{.State.Running}}') != true ]]; then
    # Start the existing image/configuration without recreating it, then dump it.
    compose start --wait --wait-timeout 180 timescale
  fi

  current=$(docker inspect tracearr-db --format '{{.Image}}')
  pending=$(compose exec -T timescale psql -X -U tracearr -d tracearr -At -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_available_extensions WHERE name IN ('timescaledb','timescaledb_toolkit') AND installed_version IS DISTINCT FROM default_version;")
  if [[ "$current" == "$target" && "$pending" == 0 ]]; then
    return 0
  fi

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
