#!/bin/sh
# Reconcile volatile access from QNAP's persistent crontab and configuration.
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
[ "$(id -u)" = 0 ]
policy=/usr/etc/sudoers.d/ups-cascade
case "${1:-}" in
    start)
        [ -x /etc/config/ups-cascade/command.sh ]
        [ -s /etc/config/ups-cascade/authorized-key ]
        # Homes point at /tmp on this NAS. Run home writes as the user so a
        # user-controlled symlink cannot redirect a privileged write.
        /usr/bin/sudo -u rubiss /bin/sh -c '
            set -eu
            umask 077
            mkdir -p /share/homes/rubiss/.ssh
            touch /share/homes/rubiss/.ssh/authorized_keys
            if ! grep -Fqx -f /etc/config/ups-cascade/authorized-key /share/homes/rubiss/.ssh/authorized_keys; then
                printf "\n" >> /share/homes/rubiss/.ssh/authorized_keys
                cat /etc/config/ups-cascade/authorized-key >> /share/homes/rubiss/.ssh/authorized_keys
            fi
        '
        mkdir -p /usr/etc/sudoers.d
        chmod 750 /usr/etc/sudoers.d
        umask 077
        # No recurring writes when the exact rule is already installed.
        rule='rubiss ALL=(admin) NOPASSWD: /etc/config/ups-cascade/command.sh *'
        if [ -f "$policy" ] && [ "$(cat "$policy")" = "$rule" ]; then exit 0; fi
        printf '%s\n' "$rule" > "$policy.tmp"
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
