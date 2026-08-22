#!/usr/bin/env bash

set -Eeuo pipefail

readonly IMAGE_MAX_AGE="${DOCKER_IMAGE_MAX_AGE:-168h}"

before=$(df --output=pcent,avail / | awk 'NR == 2 {gsub(/%/, "", $1); print $1, $2}')
read -r used_before available_before <<<"$before"

echo "Docker image cleanup started: root=${used_before}% used, available=${available_before}K, max_age=${IMAGE_MAX_AGE}"
docker image prune --all --force --filter "until=${IMAGE_MAX_AGE}"

after=$(df --output=pcent,avail / | awk 'NR == 2 {gsub(/%/, "", $1); print $1, $2}')
read -r used_after available_after <<<"$after"
reclaimed_kb=$((available_after - available_before))

echo "Docker image cleanup finished: root=${used_after}% used, available=${available_after}K, reclaimed=${reclaimed_kb}K"
