#!/bin/sh
# QPKG startup hook: /usr/etc is volatile; keep the helper in persistent config.
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
[ "$(id -u)" = 0 ]
policy=/usr/etc/sudoers.d/ups-cascade
case "${1:-}" in
    start)
        [ -x /etc/config/ups-cascade/command.sh ]
        mkdir -p /usr/etc/sudoers.d
        chmod 750 /usr/etc/sudoers.d
        umask 077
        printf '%s\n' 'rubiss ALL=(admin) NOPASSWD: /etc/config/ups-cascade/command.sh *' > "$policy.tmp"
        chmod 440 "$policy.tmp"
        mv "$policy.tmp" "$policy"
        # This firmware ships sudo without visudo. Exercise its policy parser;
        # remove only this new rule if the complete policy cannot be read.
        if ! /usr/bin/sudo -n -l -U rubiss >/dev/null; then
            rm -f "$policy"
            exit 1
        fi
        ;;
    stop)
        rm -f "$policy"
        ;;
    *) exit 64 ;;
esac
