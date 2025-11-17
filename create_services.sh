#!/bin/bash
# Script to create and start systemd services for facial recognition app

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Python executable (adjust if using a virtual environment)
PYTHON_PATH="${SCRIPT_DIR}/venv/bin/python3"
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${YELLOW}Virtual environment not found at ${PYTHON_PATH}${NC}"
    echo -e "${YELLOW}Using system python3${NC}"
    PYTHON_PATH="/usr/bin/python3"
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run this script with sudo${NC}"
    exit 1
fi

echo -e "${GREEN}Creating systemd service files...${NC}"

# Create webrtc_receiver service
cat > /etc/systemd/system/webrtc-receiver.service << EOF
[Unit]
Description=WebRTC Receiver for Facial Recognition
After=network.target

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PYTHON_PATH $SCRIPT_DIR/webrtc_receiver.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Restart on failure
StartLimitInterval=200
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}Created /etc/systemd/system/webrtc-receiver.service${NC}"

# Create main app service
cat > /etc/systemd/system/facial-recognition-app.service << EOF
[Unit]
Description=Facial Recognition Main Application
After=network.target webrtc-receiver.service
Wants=webrtc-receiver.service

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PYTHON_PATH $SCRIPT_DIR/app/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Restart on failure
StartLimitInterval=200
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}Created /etc/systemd/system/facial-recognition-app.service${NC}"

# Reload systemd to recognize new services
echo -e "${YELLOW}Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable services to start on boot
echo -e "${YELLOW}Enabling services to start on boot...${NC}"
systemctl enable webrtc-receiver.service
systemctl enable facial-recognition-app.service

# Start the services
echo -e "${YELLOW}Starting services...${NC}"
systemctl start webrtc-receiver.service
systemctl start facial-recognition-app.service

# Wait a moment for services to start
sleep 2

# Check status
echo -e "\n${GREEN}=== Service Status ===${NC}"
echo -e "\n${YELLOW}WebRTC Receiver:${NC}"
systemctl status webrtc-receiver.service --no-pager -l

echo -e "\n${YELLOW}Facial Recognition App:${NC}"
systemctl status facial-recognition-app.service --no-pager -l

echo -e "\n${GREEN}=== Setup Complete ===${NC}"
echo -e "${GREEN}Services have been created and started.${NC}"
echo -e "\n${YELLOW}Useful commands:${NC}"
echo -e "  View WebRTC logs:    sudo journalctl -u webrtc-receiver.service -f"
echo -e "  View App logs:       sudo journalctl -u facial-recognition-app.service -f"
echo -e "  Restart services:    sudo systemctl restart webrtc-receiver.service facial-recognition-app.service"
echo -e "  Stop services:       sudo systemctl stop webrtc-receiver.service facial-recognition-app.service"
echo -e "  Check status:        sudo systemctl status webrtc-receiver.service facial-recognition-app.service"
