#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$USER_UNIT_DIR"
ln -sfn "$SCRIPT_DIR/docker-image-cleanup.service" "$USER_UNIT_DIR/docker-image-cleanup.service"
ln -sfn "$SCRIPT_DIR/docker-image-cleanup.timer" "$USER_UNIT_DIR/docker-image-cleanup.timer"

systemctl --user daemon-reload
systemctl --user enable --now docker-image-cleanup.timer
systemctl --user start docker-image-cleanup.service
systemctl --user --no-pager status docker-image-cleanup.timer
