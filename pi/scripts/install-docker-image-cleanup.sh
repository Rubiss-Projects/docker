#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly USER_ID=$(id -u)

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_ID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if [[ $(loginctl show-user "$USER" --property=Linger --value) != "yes" ]]; then
    if ! loginctl enable-linger "$USER"; then
        echo "A persistent user manager is required; run: sudo loginctl enable-linger $USER" >&2
        exit 1
    fi
fi

if [[ $(loginctl show-user "$USER" --property=Linger --value) != "yes" ]]; then
    echo "A persistent user manager is required; run: sudo loginctl enable-linger $USER" >&2
    exit 1
fi

mkdir -p "$USER_UNIT_DIR"
ln -sfn "$SCRIPT_DIR/docker-image-cleanup.service" "$USER_UNIT_DIR/docker-image-cleanup.service"
ln -sfn "$SCRIPT_DIR/docker-image-cleanup.timer" "$USER_UNIT_DIR/docker-image-cleanup.timer"

systemctl --user daemon-reload
systemctl --user enable --now docker-image-cleanup.timer
systemctl --user start docker-image-cleanup.service
systemctl --user --no-pager status docker-image-cleanup.timer
