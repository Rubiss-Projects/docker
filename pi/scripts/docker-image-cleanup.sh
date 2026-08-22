#!/usr/bin/env bash

set -Eeuo pipefail

readonly RETENTION_HOURS="${DOCKER_UNUSED_IMAGE_RETENTION_HOURS:-168}"
readonly STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/docker-image-cleanup"
readonly STATE_FILE="$STATE_DIR/unused-images.tsv"
readonly DEPLOY_LOCK_FILE="${DOCKER_DEPLOY_LOCK_FILE:-/tmp/docker-compose-ops-deploy.lock}"
readonly LOCK_WAIT_SECONDS="${DOCKER_DEPLOY_LOCK_WAIT_SECONDS:-600}"

if [[ ! "$RETENTION_HOURS" =~ ^[0-9]+$ ]]; then
    echo "DOCKER_UNUSED_IMAGE_RETENTION_HOURS must be a non-negative integer" >&2
    exit 1
fi

if [[ ! "$LOCK_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "DOCKER_DEPLOY_LOCK_WAIT_SECONDS must be a non-negative integer" >&2
    exit 1
fi

exec 9>"$DEPLOY_LOCK_FILE"
if ! flock --wait "$LOCK_WAIT_SECONDS" 9; then
    echo "Timed out waiting for Docker deployment lock: $DEPLOY_LOCK_FILE" >&2
    exit 1
fi

mkdir -p "$STATE_DIR"
touch "$STATE_FILE"

declare -A first_seen_unused=()
declare -A used_images=()

remove_image() {
    local image_id=$1
    local references_output
    local -a references=()

    if ! references_output=$(docker image inspect --format '{{range .RepoTags}}{{println .}}{{end}}' "$image_id"); then
        return 1
    fi

    while read -r reference; do
        [[ -n "$reference" ]] && references+=("$reference")
    done < <(sort -u <<< "$references_output")

    if (( ${#references[@]} > 0 )); then
        docker image rm "${references[@]}"
    else
        docker image rm "$image_id"
    fi
}

while read -r image_id first_seen; do
    [[ -n "${image_id:-}" && "${first_seen:-}" =~ ^[0-9]+$ ]] || continue
    first_seen_unused["$image_id"]=$first_seen
done < "$STATE_FILE"

container_ids_output=$(docker container ls --all --quiet)
container_ids=()
while read -r container_id; do
    [[ -n "$container_id" ]] && container_ids+=("$container_id")
done <<< "$container_ids_output"

if (( ${#container_ids[@]} > 0 )); then
    used_images_output=$(docker container inspect --format '{{.Image}}' "${container_ids[@]}")
    while read -r image_id; do
        [[ -n "$image_id" ]] && used_images["$image_id"]=1
    done <<< "$used_images_output"
fi

all_images_output=$(docker image ls --all --quiet --no-trunc)
all_images=()
while read -r image_id; do
    [[ -n "$image_id" ]] && all_images+=("$image_id")
done < <(sort -u <<< "$all_images_output")
readonly now=$(date +%s)
readonly retention_seconds=$((RETENTION_HOURS * 60 * 60))
state_tmp=$(mktemp "$STATE_DIR/unused-images.tsv.XXXXXX")
trap 'rm -f "$state_tmp"' EXIT

before=$(df --output=pcent,avail / | awk 'NR == 2 {gsub(/%/, "", $1); print $1, $2}')
read -r used_before available_before <<<"$before"

echo "Docker image cleanup started: root=${used_before}% used, available=${available_before}K, unused_retention=${RETENTION_HOURS}h"

for image_id in "${all_images[@]}"; do
    if [[ -n "${used_images[$image_id]:-}" ]]; then
        continue
    fi

    first_seen=${first_seen_unused[$image_id]:-$now}
    unused_seconds=$((now - first_seen))
    if (( unused_seconds >= retention_seconds )); then
        if remove_image "$image_id"; then
            echo "Removed image $image_id after $((unused_seconds / 3600)) hours unused"
            continue
        fi

        echo "Image $image_id could not be removed; retaining its unused timestamp" >&2
    fi

    printf '%s\t%s\n' "$image_id" "$first_seen" >> "$state_tmp"
done

sort -o "$state_tmp" "$state_tmp"
mv "$state_tmp" "$STATE_FILE"

after=$(df --output=pcent,avail / | awk 'NR == 2 {gsub(/%/, "", $1); print $1, $2}')
read -r used_after available_after <<<"$after"
reclaimed_kb=$((available_after - available_before))

echo "Docker image cleanup finished: root=${used_after}% used, available=${available_after}K, reclaimed=${reclaimed_kb}K"
