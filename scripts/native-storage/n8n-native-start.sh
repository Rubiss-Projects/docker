#!/bin/sh
set -eu
node /opt/nas-migration/n8n-startup-admission.cjs --policy /opt/nas-migration/n8n-startup-policy.json
exec /docker-entrypoint.sh "$@"
