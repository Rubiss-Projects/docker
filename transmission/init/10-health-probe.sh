#!/bin/sh
set -eu
# Run probes from Linux storage so a stalled Windows media/config mount does
# not also prevent the diagnostic code itself from loading.
install -m 0755 /scripts/rpc-health.py /usr/local/bin/transmission-rpc-health
