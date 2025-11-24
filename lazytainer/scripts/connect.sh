#!/bin/sh
HOST=$1
PORT=$2

# Loop until the host resolves
while ! nslookup "$HOST" >/dev/null 2>&1; do
  # Optional: Check if we should timeout? 
  # For lazy loading, we expect it to come up eventually (within ~10-20s)
  sleep 0.5
done

# Once resolved, connect with retry (in case connection is refused initially)
exec socat - TCP:"$HOST":"$PORT",retry=120,interval=1
