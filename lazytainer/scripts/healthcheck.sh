#!/bin/sh

# Read the request line (first line of HTTP request) with a timeout
# This captures "GET /health/ollama HTTP/1.1"
REQUEST_LINE=$(timeout 0.5 head -n 1)

# Consume the rest of the headers so the client doesn't get a connection reset
timeout 0.1 cat > /dev/null 2>&1

# Extract the path from the request line (2nd word)
REQUEST_PATH=$(echo "$REQUEST_LINE" | awk '{print $2}')

# Determine container name based on path
case "$REQUEST_PATH" in
    "/health/ollama")
        CONTAINER_NAME="ollama"
        ;;
    "/health/open-webui"|"/health"|"/")
        CONTAINER_NAME="open-webui"
        ;;
    *)
        echo -e "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nUnknown container: $REQUEST_PATH"
        exit 0
        ;;
esac

# Get container status
# We use the container name directly. Since we share the socket, we can see all containers.
STATUS=$(docker inspect --format '{{.State.Status}}' $CONTAINER_NAME 2>/dev/null)
EXIT_CODE=$(docker inspect --format '{{.State.ExitCode}}' $CONTAINER_NAME 2>/dev/null)

if [ "$STATUS" = "running" ]; then
    # It's running, return 200
    echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRunning"
elif [ "$STATUS" = "exited" ]; then
    # It's stopped. Check if it was a clean stop.
    # 0 = Clean exit
    # 137 = SIGKILL (OOM or Docker stop)
    # 143 = SIGTERM (Docker stop)
    if [ "$EXIT_CODE" = "0" ] || [ "$EXIT_CODE" = "137" ] || [ "$EXIT_CODE" = "143" ]; then
        echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nSleeping (Clean Exit)"
    else
        echo -e "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/plain\r\n\r\nCrashed (Exit Code: $EXIT_CODE)"
    fi
else
    # Unknown state (e.g. restarting, dead) or container not found
    if [ -z "$STATUS" ]; then
         echo -e "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nContainer not found"
    else
         echo -e "HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/plain\r\n\r\nState: $STATUS"
    fi
fi
