#!/bin/bash
set -e

echo "=========================================================="
echo "    Oracle Always Free ARM Hunter - Setup Script (Linux) "
echo "=========================================================="

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "1. Checking Python 3 and system packages..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv curl
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip curl
elif command -v yum &>/dev/null; then
    sudo yum install -y python3 python3-pip curl
fi

echo "2. Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "3. Securing SSH and OCI key permissions..."
mkdir -p ~/.oci ~/.ssh
chmod 700 ~/.oci ~/.ssh 2>/dev/null || true

# Auto-generate SSH key if neither id_rsa nor oraclehost_id_rsa exists
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/oraclehost_id_rsa ]; then
    echo "🔑 Generating default SSH key pair (~/.ssh/id_rsa)..."
    ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa -N "" -q
fi

chmod 600 ~/.oci/*.pem 2>/dev/null || true
chmod 600 ~/.ssh/*id_rsa 2>/dev/null || true
chmod 644 ~/.ssh/*id_rsa.pub 2>/dev/null || true

echo "4. Testing configuration (Preflight Check)..."
if [ -f "config.json" ]; then
    python3 hunter.py --dry-run || {
        echo "⚠️ Preflight returned an error. Please verify your config.json and PEM files."
    }
else
    echo "⚠️ config.json not found! Please copy config.json.example to config.json and configure your keys."
fi

echo "5. Background Runner Setup (PM2 or Systemd)..."
if ! command -v pm2 &>/dev/null; then
    read -p "PM2 is not installed. Do you want to install Node.js & PM2 now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing Node.js and PM2..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y nodejs npm
        fi
        sudo npm install -g pm2
    fi
fi

if command -v pm2 &>/dev/null; then
    read -p "Do you want to launch Oracle Hunter with PM2 right now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pm2 start ecosystem.config.js
        pm2 save
        echo ""
        echo "✅ Oracle Hunter is now RUNNING with PM2!"
        echo "Useful PM2 commands:"
        echo "  - Check status: pm2 status"
        echo "  - Stream live logs: pm2 logs oracle-hunter"
        echo "  - Stop hunter:  pm2 stop oracle-hunter"
        echo "  - Restart hunter: pm2 restart oracle-hunter"
        echo "  - Enable autostart on reboot: pm2 startup"
        exit 0
    fi
fi

read -p "Do you want to enable Oracle Hunter as a 24/7 systemd background service? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_PATH="/etc/systemd/system/oracle-hunter.service"
    CURRENT_USER=$(whoami)
    
    sudo bash -c "cat <<EOF > $SERVICE_PATH
[Unit]
Description=Oracle Always Free ARM Hunter Daemon
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python3 $APP_DIR/hunter.py
Restart=always
RestartSec=15
StandardOutput=append:$APP_DIR/oracle_hunter.log
StandardError=append:$APP_DIR/oracle_hunter.log

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload
    sudo systemctl enable oracle-hunter
    sudo systemctl restart oracle-hunter

    echo ""
    echo "✅ Service oracle-hunter is now RUNNING 24/7 in background with systemd!"
    echo "Useful commands:"
    echo "  - Check status: sudo systemctl status oracle-hunter"
    echo "  - View live logs: tail -f oracle_hunter.log"
    echo "  - Stop hunter:  sudo systemctl stop oracle-hunter"
    echo "  - Start hunter: sudo systemctl start oracle-hunter"
else
    echo ""
    echo "You can run the hunter manually anytime using:"
    echo "  source .venv/bin/activate && python3 hunter.py"
    echo "Or if you have PM2:"
    echo "  pm2 start ecosystem.config.js"
fi

echo "=========================================================="
echo " Setup complete! "
echo "=========================================================="
