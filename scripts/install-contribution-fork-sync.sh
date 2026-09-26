#!/usr/bin/env bash
set -Eeuo pipefail

# Install only the reviewed canonical main checkout, as the host operator.
readonly SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly OPERATOR=$(id -un)
readonly OPERATOR_ID=$(id -u)

[[ "$SCRIPT_DIR" == /mnt/e/Docker/scripts && "$OPERATOR" == rubiss ]] || {
  echo 'Run as rubiss from the canonical /mnt/e/Docker checkout.' >&2
  exit 1
}
[[ $(git -C /mnt/e/Docker branch --show-current) == main ]] || {
  echo 'The canonical checkout must be on main.' >&2
  exit 1
}

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$OPERATOR_ID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if [[ $(loginctl show-user "$OPERATOR" --property=Linger --value) != yes ]]; then
  loginctl --no-ask-password enable-linger "$OPERATOR" || {
    echo "A persistent user manager is required; run: sudo loginctl enable-linger $OPERATOR" >&2
    exit 1
  }
fi
[[ $(loginctl show-user "$OPERATOR" --property=Linger --value) == yes ]] || exit 1

mkdir -p "$USER_UNIT_DIR"
ln -sfn "$SCRIPT_DIR/contribution-fork-sync.service" "$USER_UNIT_DIR/contribution-fork-sync.service"
ln -sfn "$SCRIPT_DIR/contribution-fork-sync.timer" "$USER_UNIT_DIR/contribution-fork-sync.timer"
systemctl --user daemon-reload
systemctl --user enable --now contribution-fork-sync.timer
systemctl --user start --no-block contribution-fork-sync.service
systemctl --user --no-pager status contribution-fork-sync.timer
