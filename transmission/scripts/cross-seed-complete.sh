#!/bin/sh

# Ask cross-seed to search configured trackers as soon as a download completes.
# Transmission supplies TR_TORRENT_HASH to completion scripts.

log_file="/config/cross-seed-completion.log"
timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [ -z "${TR_TORRENT_HASH:-}" ]; then
    printf '%s missing TR_TORRENT_HASH; skipping cross-seed webhook\n' "$timestamp" >> "$log_file"
    exit 0
fi

if [ -z "${CROSS_SEED_API_KEY:-}" ]; then
    printf '%s CROSS_SEED_API_KEY is unset; skipping cross-seed webhook\n' "$timestamp" >> "$log_file"
    exit 0
fi

http_code="$(
    curl --silent --show-error \
        --connect-timeout 5 \
        --max-time 30 \
        --output /dev/null \
        --write-out '%{http_code}' \
        --request POST \
        --header "X-Api-Key: ${CROSS_SEED_API_KEY}" \
        --data-urlencode "infoHash=${TR_TORRENT_HASH}" \
        --data-urlencode "includeSingleEpisodes=true" \
        http://cross-seed:2468/api/webhook 2>> "$log_file"
)"

case "$http_code" in
    200|204|409)
        printf '%s cross-seed webhook accepted for %.12s (HTTP %s)\n' \
            "$timestamp" "$TR_TORRENT_HASH" "$http_code" >> "$log_file"
        ;;
    *)
        printf '%s cross-seed webhook failed for %.12s (HTTP %s)\n' \
            "$timestamp" "$TR_TORRENT_HASH" "${http_code:-none}" >> "$log_file"
        ;;
esac

# A cross-seed outage must never make Transmission treat post-processing as failed.
exit 0
