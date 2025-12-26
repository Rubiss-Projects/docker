#!/bin/bash
# GitOps Deployment Script
# Deploys a single Docker Compose service after git changes
# Usage: ./deploy-service.sh <service-name> [host-type]

set -e

SERVICE_NAME="${1}"
HOST_TYPE="${2:-auto}"  # auto, windows, or pi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

if [ -z "$SERVICE_NAME" ]; then
    log_error "Service name is required"
    echo "Usage: $0 <service-name> [host-type]"
    echo "  host-type: auto (default), windows, or pi"
    exit 1
fi

# Detect host type if auto
if [ "$HOST_TYPE" == "auto" ]; then
    if [ -d "pi/$SERVICE_NAME" ]; then
        HOST_TYPE="pi"
        SERVICE_DIR="pi/$SERVICE_NAME"
    elif [ -d "$SERVICE_NAME" ]; then
        HOST_TYPE="windows"
        SERVICE_DIR="$SERVICE_NAME"
    else
        log_error "Service directory not found: $SERVICE_NAME"
        exit 1
    fi
fi

log_info "Deploying service: $SERVICE_NAME (host: $HOST_TYPE)"

# Determine service directory and path
if [ "$HOST_TYPE" == "pi" ]; then
    SERVICE_DIR="pi/$SERVICE_NAME"
    DEPLOY_PATH="/home/rubiss/docker/pi/$SERVICE_NAME"
else
    SERVICE_DIR="$SERVICE_NAME"
    DEPLOY_PATH="/mnt/e/Docker/$SERVICE_NAME"
fi

# Check if service directory exists locally
if [ ! -d "$SERVICE_DIR" ]; then
    log_error "Service directory not found: $SERVICE_DIR"
    exit 1
fi

# Check if docker-compose.yml exists
if [ ! -f "$SERVICE_DIR/docker-compose.yml" ]; then
    log_error "docker-compose.yml not found in $SERVICE_DIR"
    exit 1
fi

log_info "Service directory: $SERVICE_DIR"
log_info "Deploy path: $DEPLOY_PATH"

# Navigate to service directory
cd "$DEPLOY_PATH" || {
    log_error "Failed to navigate to $DEPLOY_PATH"
    exit 1
}

# Pull latest changes from git
log_info "Pulling latest changes from git..."
if ! git pull origin main; then
    log_error "Failed to pull latest changes"
    exit 1
fi

# Pull latest Docker images
log_info "Pulling latest Docker images..."
if ! docker compose pull; then
    log_warn "Failed to pull some images (may be expected for custom builds)"
fi

# Restart the service
log_info "Restarting service..."
if ! docker compose up -d; then
    log_error "Failed to restart service"
    exit 1
fi

# Show service status
log_info "Service status:"
docker compose ps

# Show recent logs
log_info "Recent logs (last 10 lines):"
docker compose logs --tail=10

log_info "✓ Service $SERVICE_NAME deployed successfully!"

exit 0
