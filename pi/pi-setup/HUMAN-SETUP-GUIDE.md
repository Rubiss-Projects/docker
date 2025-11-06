# Raspberry Pi 3 Setup - Manual Steps

These are the **manual steps for you** to get the Raspberry Pi ready. After completing these steps, an AI agent will handle the rest of the configuration automatically.

## What You Need

- **Hardware:**
  - Raspberry Pi 3
  - 32GB microSD card
  - USB SD card reader
  - Micro-USB power supply (5V/2.5A minimum)
  - Ethernet cable

- **On Your PC:**
  - Raspberry Pi Imager (download from https://downloads.raspberrypi.com/imager/imager_latest.exe)
  - This git repository cloned locally

## Step 1: Flash Ubuntu Server to SD Card (10 minutes)

1. **Insert microSD card** into your USB SD card reader
2. **Open Raspberry Pi Imager**
3. Click **"Choose Device"** → Select **"Raspberry Pi 3"**
4. Click **"Choose OS"** → **"Other general-purpose OS"** → **"Ubuntu"** → **"Ubuntu Server 24.04.3 LTS (64-bit)"**
5. Click **"Choose Storage"** → Select your microSD card
6. Click **"Next"**
7. **Click "Edit Settings"** when prompted for customization:

   **General tab:**
   - Set hostname: `ben-pi`
   - Set username: `rubiss`
   - Set password: (choose a secure password)
   - Configure WiFi: (optional - ethernet is recommended)
   - Set timezone: `America/New_York` (or your timezone)
   - Set locale settings: `en_US`

   **Services tab:**
   - ✅ Enable SSH
   - Use password authentication

8. Click **"Save"** → **"Yes"** to apply → **"Yes"** to confirm erase
9. Wait for write and verification (~10 minutes)

## Step 2: First Boot (5 minutes)

1. **Remove microSD card** from reader
2. **Insert microSD card** into Raspberry Pi
3. **Connect ethernet cable** to Pi (recommended over WiFi)
4. **Connect power** to Pi (it will boot automatically)
5. **Wait 2-3 minutes** for first boot to complete

## Step 3: SSH Connection (2 minutes)

From your Windows PC PowerShell:

```powershell
# SSH using hostname (if mDNS works)
ssh rubiss@ben-pi.local

# Or find Pi's IP from your router and use that:
ssh rubiss@192.168.50.216
```

**Note:** If you don't know the IP, check your router's DHCP client list for "ben-pi".

## Step 4: Set Static IP (5 minutes)

### Option A: Router DHCP Reservation (Recommended)

1. Find your Pi's MAC address:
   ```bash
   ip addr show
   ```
   Look for the ethernet interface (usually `eth0`) MAC address

2. Log into your router admin panel
3. Create DHCP reservation:
   - MAC Address: (from step 1)
   - IP Address: `192.168.50.216`
   - Hostname: `ben-pi`

**Note:** Since you've already configured the DHCP reservation before the Pi's first boot, it should already have the correct IP. You can verify with:
```bash
ip addr show eth0
```

### Option B: Netplan Configuration (Alternative)

If you can't access router settings:

```bash
# Edit netplan config
sudo nano /etc/netplan/50-cloud-init.yaml

# Add this configuration (adjust to your network):
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.50.216/24
      routes:
        - to: default
          via: 192.168.50.1  # Your router IP
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4

# Apply changes
sudo netplan apply

# Verify
ip addr show eth0
```

## Step 5: Update System (5 minutes)

```bash
sudo apt update && sudo apt upgrade -y
```

**Note:** This may take 5-10 minutes on first run.

## Step 6: Install Git (1 minute)

```bash
sudo apt install git -y

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## Step 7: Clone This Repository (2 minutes)

```bash
cd ~
git clone https://github.com/Rubiss/docker.git
cd docker/pi
```

**Verify you have these directories:**
```bash
ls -la
```

You should see: `homebridge`, `pi-hole`, `watchtower`, `cadvisor`, `node-exporter`, etc.

## Step 8: Install VS Code Tunnel (5 minutes)

```bash
# Download VS Code CLI for ARM64
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-arm64' --output vscode_cli.tar.gz

# Extract
tar -xf vscode_cli.tar.gz

# Move to PATH
sudo mv code /usr/local/bin/

# Cleanup
rm vscode_cli.tar.gz

# Start tunnel
code tunnel
```

**Follow the prompts:**
1. You'll get a URL to visit in your browser
2. Sign in with your GitHub account
3. Authorize VS Code
4. Give your tunnel a name (e.g., `raspberry-pi`)
5. The tunnel will start running

**To keep tunnel running in background:**
```bash
# Press Ctrl+C to stop
# Then run as a service:
sudo code tunnel service install
sudo code tunnel service start
```

## Step 9: Hand Off to AI Agent

You're done with manual setup! Now:

1. **Open VS Code** on your Windows PC
2. **Connect to tunnel:** Remote Explorer → Connect to Tunnel → Select `raspberry-pi`
3. **Open this file:** `~/docker/pi/AI-SETUP-INSTRUCTIONS.md`
4. **Copy all instructions** and give them to your AI agent (like GitHub Copilot or Claude)

The AI agent will:
- Install Docker
- Deploy all services (Homebridge, Pi-hole, Watchtower, cAdvisor, node-exporter)
- Configure everything automatically
- Verify all services are running

## Summary of What You Did

✅ Flashed Ubuntu Server to SD card  
✅ Booted Pi and connected via SSH  
✅ Configured static IP (192.168.50.216)  
✅ Installed Git and cloned this repository  
✅ Set up VS Code tunnel for remote access  

## What's Next

The AI agent (following `AI-SETUP-INSTRUCTIONS.md`) will handle:
- Docker installation
- All container deployments
- Service configuration
- Verification and testing

## Troubleshooting

### Can't SSH to Pi
- Check Pi is powered on (green LED)
- Verify ethernet cable connected
- Find Pi's IP in router admin panel
- Try IP address instead of hostname: `ssh rubiss@192.168.50.216`

### Wrong IP Address Assigned
- Check DHCP reservation is correct in router
- Reboot Pi: `sudo reboot`
- Verify with: `ip addr show`

### VS Code Tunnel Won't Start
- Ensure you have internet connectivity: `ping google.com`
- Check for errors in output
- Try manual authentication: Follow URL in output

### Git Clone Fails
- Verify internet connection
- Check GitHub is accessible: `ping github.com`
- Ensure repository is public or you have access

## Notes

- **Static IP:** Critical for monitoring and proxy configuration. Prometheus and NPM are already configured for `192.168.50.216`
- **VS Code Tunnel:** This is the recommended way to access the Pi remotely. It works even when you're not on the same network
- **Don't install Docker yet:** The AI agent will handle this in the next phase

---

**Estimated Total Time:** 30-35 minutes

**Once complete, proceed to `AI-SETUP-INSTRUCTIONS.md` and hand it to your AI agent.**
