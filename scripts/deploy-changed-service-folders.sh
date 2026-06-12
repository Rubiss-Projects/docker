#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR=${DOCKER_REPO_DIR:-/mnt/e/Docker}
DEPLOY_BRANCH=${DOCKER_DEPLOY_BRANCH:-main}
DEPLOY_REPOSITORY=${DOCKER_DEPLOY_REPOSITORY:-Rubiss-Projects/docker}
if [[ -n "${DOCKER_DEPLOY_SCOPE:-}" ]]; then
  DEPLOY_SCOPE=$DOCKER_DEPLOY_SCOPE
elif [[ "${DOCKER_DEPLOY_PI_SERVICES:-false}" == "true" ]]; then
  DEPLOY_SCOPE=all
else
  DEPLOY_SCOPE=main
fi
DEPLOY_START_STOPPED=${DOCKER_DEPLOY_START_STOPPED:-false}
LOCK_FILE=${DOCKER_DEPLOY_LOCK_FILE:-/tmp/docker-compose-ops-deploy.lock}
CRITICAL_STACK_ORDER=(socket-proxy uptime-kuma plex swag)

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

compose() {
  local env_args=()

  [[ -f .env ]] && env_args+=(--env-file .env)
  [[ -f .env.secret ]] && env_args+=(--env-file .env.secret)

  docker compose "${env_args[@]}" "$@"
}

stack_dependencies() {
  case "$1" in
    homepage|n8n|openclaw)
      printf '%s\n' socket-proxy
      ;;
    uptime-kuma)
      printf '%s\n' socket-proxy
      ;;
    swag)
      printf '%s\n' socket-proxy uptime-kuma plex
      ;;
  esac
}

stack_dependents() {
  case "$1" in
    socket-proxy)
      printf '%s\n' uptime-kuma swag
      ;;
    uptime-kuma|plex)
      printf '%s\n' swag
      ;;
  esac
}

mark_service_dir() {
  local stack_dir=$1
  local reason=$2
  local current=${service_dirs[$stack_dir]:-}

  if [[ "$current" == "changed" ]]; then
    return 0
  fi

  if [[ "$reason" == "changed" || -z "$current" || ( "$current" == "dependency" && "$reason" == "dependent" ) ]]; then
    service_dirs["$stack_dir"]=$reason
  fi
}

scope_allows_stack() {
  local stack_dir=$1

  case "$DEPLOY_SCOPE" in
    main)
      [[ "$stack_dir" != pi/* ]]
      ;;
    pi)
      [[ "$stack_dir" == pi/* ]]
      ;;
    all)
      return 0
      ;;
    *)
      die "Invalid DOCKER_DEPLOY_SCOPE: $DEPLOY_SCOPE"
      ;;
  esac
}

order_service_dirs() {
  local dir
  declare -A remaining=()

  for dir in "$@"; do
    remaining["$dir"]=1
  done

  for dir in "${CRITICAL_STACK_ORDER[@]}"; do
    if [[ -n "${remaining[$dir]:-}" ]]; then
      printf '%s\n' "$dir"
      unset "remaining[$dir]"
    fi
  done

  for dir in "${!remaining[@]}"; do
    printf '%s\n' "$dir"
  done | sort
}

is_zero_sha() {
  [[ "$1" =~ ^0+$ ]]
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

verify_github_actions_context() {
  [[ "${GITHUB_ACTIONS:-}" == "true" ]] || return 0

  [[ "${GITHUB_EVENT_NAME:-}" == "push" ]] || die "Refusing to deploy from GitHub event: ${GITHUB_EVENT_NAME:-unset}"
  [[ "${GITHUB_REF:-}" == "refs/heads/$DEPLOY_BRANCH" ]] || die "Refusing to deploy from Git ref: ${GITHUB_REF:-unset}"
  [[ "${GITHUB_REPOSITORY:-}" == "$DEPLOY_REPOSITORY" ]] || die "Refusing to deploy from GitHub repository: ${GITHUB_REPOSITORY:-unset}"
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
    AFTER_SHA=$(git -C "$REPO_DIR" rev-parse FETCH_HEAD)
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

wait_container_ready() {
  local container_name=$1
  local timeout_seconds=${2:-180}
  local deadline=$((SECONDS + timeout_seconds))
  local state status health exit_code

  while (( SECONDS < deadline )); do
    state=$(docker inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}' "$container_name" 2>/dev/null || true)
    if [[ -n "$state" ]]; then
      IFS='|' read -r status health exit_code <<<"$state"
      if [[ "$status" == "running" && ( "$health" == "none" || "$health" == "healthy" ) ]]; then
        log "Container $container_name is ready"
        return 0
      fi
    fi
    sleep 5
  done

  state=$(docker inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}' "$container_name" 2>/dev/null || true)
  die "Timed out waiting for $container_name readiness. State=${state:-missing}"
}

wait_container_url() {
  local container_name=$1
  local url=$2
  local timeout_seconds=${3:-120}
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    if docker exec "$container_name" curl -fsS --max-time 5 -o /dev/null "$url" >/dev/null 2>&1; then
      log "Container probe succeeded from $container_name to $url"
      return 0
    fi
    sleep 5
  done

  die "Timed out waiting for container probe from $container_name to $url"
}

wait_tcp_port() {
  local host=$1
  local port=$2
  local timeout_seconds=${3:-120}
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    if (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1; then
      exec 3>&-
      exec 3<&-
      log "TCP probe succeeded for $host:$port"
      return 0
    fi
    sleep 5
  done

  die "Timed out waiting for TCP probe $host:$port"
}

verify_swag_dependency_endpoints() {
  local socket_ok=false
  local uptime_ok=false
  local plex_ok=false

  docker exec swag curl -fsS --max-time 5 -o /dev/null http://socket-proxy:2375/_ping >/dev/null 2>&1 && socket_ok=true
  docker exec swag curl -fsS --max-time 5 -o /dev/null http://uptime-kuma:3001/ >/dev/null 2>&1 && uptime_ok=true
  docker exec swag curl -fsS --max-time 5 -o /dev/null http://plex:32400/identity >/dev/null 2>&1 && plex_ok=true

  if [[ "$socket_ok" == "true" && "$uptime_ok" == "true" && "$plex_ok" == "true" ]]; then
    log "SWAG dependency probes are healthy"
    return 0
  fi

  die "SWAG dependency probe failed: socket-proxy=$socket_ok uptime-kuma=$uptime_ok plex=$plex_ok"
}

verify_stack_readiness() {
  local stack_dir=$1

  case "$stack_dir" in
    socket-proxy)
      wait_container_ready socket-proxy 180
      ;;
    uptime-kuma)
      wait_container_ready uptime-kuma 180
      wait_container_url uptime-kuma http://localhost:3001/ 180
      wait_container_url uptime-kuma http://uptime-kuma:3001/ 60
      ;;
    plex)
      wait_container_ready plex 240
      wait_container_url plex http://localhost:32400/identity 240
      ;;
    swag)
      wait_container_ready swag 240
      verify_swag_dependency_endpoints
      wait_tcp_port 127.0.0.1 80 120
      wait_tcp_port 127.0.0.1 443 120
      ;;
  esac
}

verify_config_mounts() {
  local stack_dir=$1
  local check_rows

  mapfile -t check_rows < <(
    compose config --format json \
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

ensure_dependency_stack() {
  local stack_dir=$1
  local stack_path="$REPO_DIR/$stack_dir"

  if ! scope_allows_stack "$stack_dir"; then
    log "Skipping dependency $stack_dir because deploy scope is $DEPLOY_SCOPE"
    return 0
  fi

  [[ -d "$stack_path" ]] || die "Required dependency service directory is missing: $stack_dir"

  log "Ensuring dependency $stack_dir is running"
  (
    cd "$stack_path"
    compose config --quiet

    local running_services
    running_services=$(compose ps --status running --services 2>/dev/null || true)
    if [[ -z "$running_services" && "$DEPLOY_START_STOPPED" != "true" ]]; then
      die "$stack_dir is required by a changed service, but it has no running Compose services. Start it first or set DOCKER_DEPLOY_START_STOPPED=true."
    fi

    run compose up -d --no-build

    if [[ "$DRY_RUN" != "true" ]]; then
      verify_stack_readiness "$stack_dir"
    fi
  )
}

refresh_dependent_stack() {
  local stack_dir=$1
  local stack_path="$REPO_DIR/$stack_dir"

  if ! scope_allows_stack "$stack_dir"; then
    log "Skipping dependent $stack_dir because deploy scope is $DEPLOY_SCOPE"
    return 0
  fi

  [[ -d "$stack_path" ]] || die "Dependent service directory is missing: $stack_dir"

  log "Refreshing dependent $stack_dir after dependency changes"
  (
    cd "$stack_path"
    compose config --quiet

    local running_services
    running_services=$(compose ps --status running --services 2>/dev/null || true)
    if [[ -z "$running_services" ]]; then
      if [[ "$DEPLOY_START_STOPPED" != "true" ]]; then
        log "Skipping dependent $stack_dir because it has no currently running Compose services"
        exit 0
      fi

      run compose up -d --no-build
    else
      run compose restart
    fi

    if [[ "$DRY_RUN" != "true" ]]; then
      verify_stack_readiness "$stack_dir"
    fi
  )
}

deploy_stack() {
  local stack_dir=$1
  local stack_path="$REPO_DIR/$stack_dir"

  if ! scope_allows_stack "$stack_dir"; then
    log "Skipping $stack_dir because deploy scope is $DEPLOY_SCOPE"
    return 0
  fi

  [[ -d "$stack_path" ]] || die "Service directory no longer exists: $stack_dir"

  log "Deploying $stack_dir"
  (
    cd "$stack_path"
    compose config --quiet

    if [[ "$DEPLOY_START_STOPPED" != "true" ]]; then
      local running_services
      running_services=$(compose ps --status running --services 2>/dev/null || true)
      if [[ -z "$running_services" ]]; then
        log "Skipping $stack_dir because it has no currently running Compose services"
        exit 0
      fi
    fi

    run compose pull --ignore-buildable
    run compose up -d --build --remove-orphans

    if [[ "$DRY_RUN" != "true" ]]; then
      verify_config_mounts "$stack_dir"
      verify_stack_readiness "$stack_dir"
    fi
  )
}

add_stack_dependencies() {
  local stack_dir=$1
  local dep

  while IFS= read -r dep; do
    [[ -n "$dep" ]] || continue
    [[ -d "$REPO_DIR/$dep" ]] || die "$stack_dir depends on missing service directory: $dep"
    mark_service_dir "$dep" dependency
    add_stack_dependencies "$dep"
  done < <(stack_dependencies "$stack_dir")
}

add_stack_dependents() {
  local stack_dir=$1
  local dependent

  while IFS= read -r dependent; do
    [[ -n "$dependent" ]] || continue
    [[ -d "$REPO_DIR/$dependent" ]] || die "$stack_dir dependent service directory is missing: $dependent"
    mark_service_dir "$dependent" dependent
    add_stack_dependencies "$dependent"
  done < <(stack_dependents "$stack_dir")
}

main() {
  require_command docker
  require_command flock
  require_command git
  require_command jq
  verify_github_actions_context

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
  git -C "$REPO_DIR" fetch --prune origin "refs/heads/$DEPLOY_BRANCH"

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
    git -C "$REPO_DIR" merge --ff-only FETCH_HEAD
  fi

  if [[ ${#changed_files[@]} -eq 0 ]]; then
    log "No changed files detected"
    return 0
  fi

  local changed
  declare -A service_dirs=()
  for changed in "${changed_files[@]}"; do
    if find_service_dir "$changed"; then
      mark_service_dir "$SERVICE_DIR_RESULT" changed
    fi
  done

  if [[ ${#service_dirs[@]} -eq 0 ]]; then
    log "No changed service folders detected"
    return 0
  fi

  local service_dir
  local service_dirs_sorted
  mapfile -t service_dirs_sorted < <(order_service_dirs "${!service_dirs[@]}")
  log "Changed service folders: ${service_dirs_sorted[*]}"

  for service_dir in "${service_dirs_sorted[@]}"; do
    if [[ "${service_dirs[$service_dir]}" == "changed" ]]; then
      add_stack_dependencies "$service_dir"
      add_stack_dependents "$service_dir"
    fi
  done

  mapfile -t service_dirs_sorted < <(order_service_dirs "${!service_dirs[@]}")
  local plan_parts=()
  for service_dir in "${service_dirs_sorted[@]}"; do
    plan_parts+=("$service_dir:${service_dirs[$service_dir]}")
  done
  log "Dependency-aware deployment plan: ${plan_parts[*]}"

  for service_dir in "${service_dirs_sorted[@]}"; do
    if [[ "${service_dirs[$service_dir]}" == "changed" ]]; then
      deploy_stack "$service_dir"
    elif [[ "${service_dirs[$service_dir]}" == "dependency" ]]; then
      ensure_dependency_stack "$service_dir"
    else
      refresh_dependent_stack "$service_dir"
    fi
  done
}

main "$@"
