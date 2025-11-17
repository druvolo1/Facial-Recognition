#!/bin/bash
# Script to stop and remove systemd services for facial recognition app

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run this script with sudo${NC}"
    exit 1
fi

echo -e "${YELLOW}Stopping services...${NC}"

# Stop the services
systemctl stop facial-recognition-app.service 2>/dev/null
systemctl stop webrtc-receiver.service 2>/dev/null

echo -e "${GREEN}Services stopped.${NC}"

# Disable services from starting on boot
echo -e "${YELLOW}Disabling services...${NC}"
systemctl disable facial-recognition-app.service 2>/dev/null
systemctl disable webrtc-receiver.service 2>/dev/null

echo -e "${GREEN}Services disabled.${NC}"

# Remove service files
echo -e "${YELLOW}Removing service files...${NC}"

if [ -f /etc/systemd/system/facial-recognition-app.service ]; then
    rm /etc/systemd/system/facial-recognition-app.service
    echo -e "${GREEN}Removed facial-recognition-app.service${NC}"
else
    echo -e "${YELLOW}facial-recognition-app.service not found${NC}"
fi

if [ -f /etc/systemd/system/webrtc-receiver.service ]; then
    rm /etc/systemd/system/webrtc-receiver.service
    echo -e "${GREEN}Removed webrtc-receiver.service${NC}"
else
    echo -e "${YELLOW}webrtc-receiver.service not found${NC}"
fi

# Reload systemd to recognize removed services
echo -e "${YELLOW}Reloading systemd daemon...${NC}"
systemctl daemon-reload
systemctl reset-failed

echo -e "\n${GREEN}=== Cleanup Complete ===${NC}"
echo -e "${GREEN}All services have been stopped and removed.${NC}"
echo -e "\n${YELLOW}You can verify with:${NC}"
echo -e "  systemctl status webrtc-receiver.service"
echo -e "  systemctl status facial-recognition-app.service"
