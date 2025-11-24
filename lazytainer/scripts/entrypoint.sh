#!/bin/sh
set -e

# Ensure scripts are executable
chmod +x /scripts/healthcheck.sh

# Start socat proxies to hold connections and forward to targets
# Lazytainer monitors the traffic (sniffing) and starts the containers
# Socat holds the connection until the target is ready
echo "Starting socat proxies..."
socat TCP-LISTEN:8080,fork,reuseaddr EXEC:"/scripts/connect.sh open-webui 8080" &
socat TCP-LISTEN:11434,fork,reuseaddr EXEC:"/scripts/connect.sh ollama 11434" &

# Start the healthcheck listener (foreground process)
echo "Starting healthcheck listener..."
exec socat TCP-LISTEN:8081,fork,reuseaddr EXEC:/scripts/healthcheck.sh
