#!/bin/bash
# VPS Setup Script for Mutual Funds Analyzing Tool
# Run as root on Ubuntu/Debian

set -e

APP_DIR="/opt/mutual-funds-tool"
APP_USER="www-data"

echo "=== Mutual Funds Tool - VPS Setup ==="

# 1. System packages
echo "[1/6] Installing system packages..."
apt update && apt install -y python3 python3-venv python3-pip git nginx

# 2. Clone or update repo
echo "[2/6] Setting up application..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone https://github.com/cerusofranco-thegoat/Mutual-Funds-Tool.git "$APP_DIR"
fi

cd "$APP_DIR"

# 3. Python virtual environment
echo "[3/6] Creating virtual environment..."
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# 4. Create directories
echo "[4/6] Creating data directories..."
mkdir -p uploads output input
chown -R "$APP_USER:$APP_USER" uploads output input

# 5. Install Claude Code CLI (user must authenticate separately)
echo "[5/6] Claude Code CLI..."
if ! command -v claude &> /dev/null; then
    echo "  Claude Code CLI not found."
    echo "  Install it with: npm install -g @anthropic-ai/claude-code"
    echo "  Then authenticate with: claude auth login"
fi

# 6. Systemd service
echo "[6/6] Setting up systemd service..."
cp deploy/mutual-funds.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mutual-funds
systemctl start mutual-funds

echo ""
echo "=== Setup Complete ==="
echo "  App running at: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "  IMPORTANT next steps:"
echo "  1. Edit auth.yaml to set your login credentials"
echo "  2. Edit /etc/systemd/system/mutual-funds.service to set FLASK_SECRET_KEY"
echo "  3. Install Claude Code: npm install -g @anthropic-ai/claude-code"
echo "  4. Authenticate Claude: sudo -u $APP_USER claude auth login"
echo "  5. (Optional) Set up nginx reverse proxy for HTTPS"
echo ""
