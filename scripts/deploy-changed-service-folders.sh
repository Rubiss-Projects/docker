#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR=${DOCKER_REPO_DIR:-/mnt/e/Docker}
DEPLOY_BRANCH=${DOCKER_DEPLOY_BRANCH:-main}
if [[ -n "${DOCKER_DEPLOY_SCOPE:-}" ]]; then
  DEPLOY_SCOPE=$DOCKER_DEPLOY_SCOPE
elif [[ "${DOCKER_DEPLOY_PI_SERVICES:-false}" == "true" ]]; then
  DEPLOY_SCOPE=all
else
  DEPLOY_SCOPE=main
fi
DEPLOY_START_STOPPED=${DOCKER_DEPLOY_START_STOPPED:-false}
LOCK_FILE=${DOCKER_DEPLOY_LOCK_FILE:-/tmp/docker-compose-ops-deploy.lock}

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

BEFORE_SHA=${1:-}
AFTER_SHA=${2:-}
SERVICE_DIR_RESULT=

log() {
  printf '[%(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY RUN: $*"
    return 0
  fi

  "$@"
}

is_zero_sha() {
  [[ "$1" =~ ^0+$ ]]
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

find_service_dir() {
  local changed_path=$1
  local dir

  changed_path=${changed_path#./}
  [[ "$changed_path" == */* ]] || return 1

  dir=${changed_path%/*}
  while [[ -n "$dir" && "$dir" != "." ]]; do
    if [[ -f "$REPO_DIR/$dir/docker-compose.yml" || -f "$REPO_DIR/$dir/compose.yml" || -f "$REPO_DIR/$dir/compose.yaml" ]]; then
      SERVICE_DIR_RESULT=$dir
      return 0
    fi

    [[ "$dir" == */* ]] || break
    dir=${dir%/*}
  done

  return 1
}

resolve_changed_files() {
  if [[ -z "$AFTER_SHA" ]]; then
    AFTER_SHA=$(git -C "$REPO_DIR" rev-parse "origin/$DEPLOY_BRANCH")
  fi

  git -C "$REPO_DIR" cat-file -e "${AFTER_SHA}^{commit}" || die "After commit is not available locally: $AFTER_SHA"

  if [[ -z "$BEFORE_SHA" ]] || is_zero_sha "$BEFORE_SHA"; then
    if git -C "$REPO_DIR" rev-parse --verify "${AFTER_SHA}^" >/dev/null 2>&1; then
      BEFORE_SHA="${AFTER_SHA}^"
    else
      BEFORE_SHA=
    fi
  fi

  if [[ -n "$BEFORE_SHA" ]]; then
    git -C "$REPO_DIR" cat-file -e "${BEFORE_SHA}^{commit}" || die "Before commit is not available locally: $BEFORE_SHA"
    git -C "$REPO_DIR" diff --name-only "$BEFORE_SHA" "$AFTER_SHA" --
  else
    git -C "$REPO_DIR" show --format= --name-only "$AFTER_SHA"
  fi
}

verify_config_mounts() {
  local stack_dir=$1
  local check_rows

  mapfile -t check_rows < <(
    docker compose config --format json \
      | jq -r '.services
        | to_entries[]
        | .key as $service
        | (.value.container_name // $service) as $container
        | (.value.volumes // [])[]
        | select(.type == "bind" and .target == "/config")
        | [$service, $container, .source]
        | @tsv'
  )

  if [[ ${#check_rows[@]} -eq 0 ]]; then
    return 0
  fi

  local row
  for row in "${check_rows[@]}"; do
    local service_name container_name host_path sentinel token actual status

    IFS=$'\t' read -r service_name container_name host_path <<<"$row"
    sentinel=.compose-deploy-mount-check
    token="$stack_dir:$service_name:$(date +%s):$$"

    [[ -d "$host_path" ]] || die "$stack_dir declares /config bind for $service_name, but host path is missing: $host_path"

    status=$(docker inspect -f '{{.State.Running}}' "$container_name" 2>/dev/null || true)
    if [[ "$status" != "true" ]]; then
      die "$container_name is not running after deploy"
    fi

    if [[ -w "$host_path" ]]; then
      printf '%s\n' "$token" > "$host_path/$sentinel"
      actual=$(docker exec "$container_name" sh -c "cat /config/$sentinel 2>/dev/null" || true)
      rm -f "$host_path/$sentinel"
    else
      docker exec -e TOKEN="$token" "$container_name" sh -c "printf '%s\n' \"\$TOKEN\" > /config/$sentinel"
      actual=$(cat "$host_path/$sentinel" 2>/dev/null || true)
      docker exec "$container_name" rm -f "/config/$sentinel"
    fi

    [[ "$actual" == "$token" ]] || die "$container_name failed /config bind mount verification for host path $host_path"
    log "Verified /config bind mount for $container_name"
  done
}

deploy_stack() {
  local stack_dir=$1
  local stack_path="$REPO_DIR/$stack_dir"

  case "$DEPLOY_SCOPE" in
    main)
      if [[ "$stack_dir" == pi/* ]]; then
        log "Skipping $stack_dir because deploy scope is main"
        return 0
      fi
      ;;
    pi)
      if [[ "$stack_dir" != pi/* ]]; then
        log "Skipping $stack_dir because deploy scope is pi"
        return 0
      fi
      ;;
    all)
      ;;
    *)
      die "Invalid DOCKER_DEPLOY_SCOPE: $DEPLOY_SCOPE"
      ;;
  esac

  [[ -d "$stack_path" ]] || die "Service directory no longer exists: $stack_dir"

  log "Deploying $stack_dir"
  (
    cd "$stack_path"
    docker compose config --quiet

    if [[ "$DEPLOY_START_STOPPED" != "true" ]]; then
      local running_services
      running_services=$(docker compose ps --status running --services 2>/dev/null || true)
      if [[ -z "$running_services" ]]; then
        log "Skipping $stack_dir because it has no currently running Compose services"
        exit 0
      fi
    fi

    run docker compose pull --ignore-buildable
    run docker compose up -d --build --remove-orphans

    if [[ "$DRY_RUN" != "true" ]]; then
      verify_config_mounts "$stack_dir"
    fi
  )
}

main() {
  require_command docker
  require_command flock
  require_command git
  require_command jq

  [[ -d "$REPO_DIR/.git" ]] || die "Repository directory is not a git checkout: $REPO_DIR"

  exec 9>"$LOCK_FILE"
  flock -n 9 || die "Another compose deployment is already running"
  case "$DEPLOY_SCOPE" in
    main|pi|all) ;;
    *) die "Invalid DOCKER_DEPLOY_SCOPE: $DEPLOY_SCOPE" ;;
  esac
  log "Deploy scope: $DEPLOY_SCOPE"

  local current_branch
  current_branch=$(git -C "$REPO_DIR" branch --show-current)
  [[ "$current_branch" == "$DEPLOY_BRANCH" ]] || die "Expected $REPO_DIR to be on $DEPLOY_BRANCH, found $current_branch"

  log "Fetching origin/$DEPLOY_BRANCH"
  git -C "$REPO_DIR" fetch --prune origin "$DEPLOY_BRANCH"

  local tracked_changes
  tracked_changes=$(git -C "$REPO_DIR" status --porcelain --untracked-files=no)
  if [[ -n "$tracked_changes" && "$DRY_RUN" != "true" ]]; then
    die "Refusing to deploy with tracked local changes in $REPO_DIR. Commit, stash, or revert them first."
  elif [[ -n "$tracked_changes" ]]; then
    log "DRY RUN: tracked local changes are present; continuing without pulling"
  fi

  local changed_files
  mapfile -t changed_files < <(resolve_changed_files)

  if [[ "$DRY_RUN" != "true" ]]; then
    log "Fast-forwarding $REPO_DIR to origin/$DEPLOY_BRANCH"
    git -C "$REPO_DIR" merge --ff-only "origin/$DEPLOY_BRANCH"
  fi

  if [[ ${#changed_files[@]} -eq 0 ]]; then
    log "No changed files detected"
    return 0
  fi

  local changed
  declare -A service_dirs=()
  for changed in "${changed_files[@]}"; do
    if find_service_dir "$changed"; then
      service_dirs["$SERVICE_DIR_RESULT"]=1
    fi
  done

  if [[ ${#service_dirs[@]} -eq 0 ]]; then
    log "No changed service folders detected"
    return 0
  fi

  local service_dir
  local service_dirs_sorted
  mapfile -t service_dirs_sorted < <(printf '%s\n' "${!service_dirs[@]}" | sort)
  log "Changed service folders: ${service_dirs_sorted[*]}"

  for service_dir in "${service_dirs_sorted[@]}"; do
    deploy_stack "$service_dir"
  done
}

main "$@"
