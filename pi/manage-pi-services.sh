#!/bin/bash
# Raspberry Pi Docker Services Management Script
# Usage: ./manage-pi-services.sh [start|stop|restart|status|logs|update]

SERVICES=(
    "homebridge"
    "pi-hole"
    "watchtower"
    "cadvisor"
    "node-exporter"
    "glances"
)

SERVICE_DIRS=(
    "/home/rubiss/docker/pi/homebridge"
    "/home/rubiss/docker/pi/pi-hole"
    "/home/rubiss/docker/pi/watchtower"
    "/home/rubiss/docker/pi/cadvisor"
    "/home/rubiss/docker/pi/node-exporter"
    "/home/rubiss/docker/pi/glances"
)

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Please run as root or with sudo"
        exit 1
    fi
}

service_action() {
    local action=$1
    echo "=========================================="
    echo " ${action^^} ALL PI SERVICES"
    echo "=========================================="
    
    for i in "${!SERVICES[@]}"; do
        local service="${SERVICES[$i]}"
        local dir="${SERVICE_DIRS[$i]}"
        
        echo ""
        echo "➤ ${service}..."
        cd "$dir" || continue
        
        case $action in
            start)
                docker-compose up -d
                ;;
            stop)
                docker-compose down
                ;;
            restart)
                docker-compose restart
                ;;
            *)
                echo "Unknown action: $action"
                return 1
                ;;
        esac
    done
    
    echo ""
    echo "✓ ${action^^} complete for all services"
}

show_status() {
    echo "=========================================="
    echo " PI SERVICES STATUS"
    echo "=========================================="
    echo ""
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "homebridge|pihole|watchtower|cadvisor|node-exporter|glances-pi|NAMES"
    echo ""
    echo "=========================================="
    echo " RESOURCE USAGE"
    echo "=========================================="
    echo ""
    docker stats --no-stream homebridge pihole watchtower cadvisor node-exporter glances-pi \
        --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
    echo ""
    echo "=========================================="
    echo " SYSTEM INFO"
    echo "=========================================="
    echo "CPU Temperature: $(vcgencmd measure_temp)"
    echo "Memory: $(free -h | awk '/^Mem:/ {print $3 " / " $2}')"
    echo "Disk Usage: $(df -h / | awk 'NR==2 {print $3 " / " $2 " (" $5 " used)"}')"
}

show_logs() {
    local service=$1
    
    if [ -z "$service" ]; then
        echo "Available services:"
        for s in "${SERVICES[@]}"; do
            echo "  - $s"
        done
        echo ""
        echo "Usage: $0 logs <service-name>"
        exit 1
    fi
    
    echo "=========================================="
    echo " LOGS: $service"
    echo "=========================================="
    docker logs -f "$service"
}

update_images() {
    check_root
    echo "=========================================="
    echo " UPDATING ALL DOCKER IMAGES"
    echo "=========================================="
    
    for i in "${!SERVICES[@]}"; do
        local service="${SERVICES[$i]}"
        local dir="${SERVICE_DIRS[$i]}"
        
        echo ""
        echo "➤ Pulling latest image for ${service}..."
        cd "$dir" || continue
        docker-compose pull
    done
    
    echo ""
    echo "=========================================="
    echo " RECREATING CONTAINERS WITH NEW IMAGES"
    echo "=========================================="
    
    for i in "${!SERVICES[@]}"; do
        local service="${SERVICES[$i]}"
        local dir="${SERVICE_DIRS[$i]}"
        
        echo ""
        echo "➤ Recreating ${service}..."
        cd "$dir" || continue
        docker-compose up -d --force-recreate
    done
    
    echo ""
    echo "✓ Update complete!"
}

# Main script logic
case "$1" in
    start|stop|restart)
        check_root
        service_action "$1"
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$2"
        ;;
    update)
        update_images
        ;;
    *)
        echo "Raspberry Pi Docker Services Manager"
        echo ""
        echo "Usage: $0 [command] [options]"
        echo ""
        echo "Commands:"
        echo "  start      - Start all services"
        echo "  stop       - Stop all services"
        echo "  restart    - Restart all services"
        echo "  status     - Show status of all services"
        echo "  logs       - Show logs for a specific service"
        echo "               Usage: $0 logs <service-name>"
        echo "  update     - Update all Docker images and recreate containers"
        echo ""
        echo "Services:"
        for s in "${SERVICES[@]}"; do
            echo "  - $s"
        done
        exit 1
        ;;
esac
