#!/bin/sh
# SSH forced command, installed root-owned on persistent QNAP storage. The key
# may inspect readiness or request ordinary init shutdown of one exact boot.
set -eu
boot=$(cat /proc/sys/kernel/random/boot_id)
case "${1:-${SSH_ORIGINAL_COMMAND:-}}" in
  status)
    ready=false
    # Verify the admitted Media dataset and NFS service, not just ICMP/SSH.
    if /sbin/zpool list -H -o name,health | grep -qx 'zpool1[[:space:]]*ONLINE' &&
       grep -q '^zpool1/zfs19 /share/ZFS19_DATA zfs rw,' /proc/mounts &&
       test -d /share/ZFS19_DATA/Media/data &&
       test -r /proc/fs/nfsd/threads &&
       test "$(cat /proc/fs/nfsd/threads)" -gt 0; then
      ready=true
    fi
    printf '{"boot":"%s","ready":%s}\n' "$boot" "$ready"
    ;;
  "shutdown $boot")
    # No -f: BusyBox poweroff asks init to run QNAP's /etc/init.d/rcK.
    /sbin/poweroff
    printf '{"accepted":true}\n'
    ;;
  *) exit 64 ;;
esac
