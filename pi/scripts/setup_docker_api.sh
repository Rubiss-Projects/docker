#!/bin/bash
set -e

echo "Configuring Docker to listen on TCP port 2375..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root (use sudo)"
  exit 1
fi

# Backup daemon.json if it exists
if [ -f /etc/docker/daemon.json ]; then
    echo "/etc/docker/daemon.json already exists. Backing up to /etc/docker/daemon.json.bak"
    cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
fi

# Create daemon.json
echo "Creating /etc/docker/daemon.json..."
cat <<EOF > /etc/docker/daemon.json
{
  "hosts": ["tcp://0.0.0.0:2375", "unix:///var/run/docker.sock"]
}
EOF

# Create override directory
echo "Creating /etc/systemd/system/docker.service.d directory..."
mkdir -p /etc/systemd/system/docker.service.d

# Create override.conf
echo "Creating /etc/systemd/system/docker.service.d/override.conf..."
cat <<EOF > /etc/systemd/system/docker.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd --containerd=/run/containerd/containerd.sock
EOF

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Restart Docker
echo "Restarting Docker..."
systemctl restart docker

echo "Done! Docker should now be listening on port 2375."
echo "Note: If you have a firewall enabled (like ufw), make sure to allow port 2375."
echo "Example: sudo ufw allow 2375"
