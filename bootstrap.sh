#!/bin/bash

# --- DYNAMIC PATH DETECTION ---
# This ensures the script works even if the folder isn't exactly /root/EasyVPN-Backend
if [ -d "/content" ]; then
    DEFAULT_DIR="/content/EasyVPN-Backend"
else
    # Get the directory where the script is actually located
    DEFAULT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
fi

BASE_DIR=$DEFAULT_DIR
ENV_FILE="$BASE_DIR/.env"
PROVISION_SCRIPT="$BASE_DIR/provision.py"

# Colors for UI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}    🚀 EasyVPN-Backend Bootstrapper           ${NC}"
echo -e "${BLUE}    Location: $BASE_DIR                         ${NC}"
echo -e "${BLUE}================================================${NC}"

# Ensure we are root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root.${NC}"
   exit 1
fi

echo -e "\n${YELLOW}[1/3] Checking system requirements...${NC}"

# Install Python3 if missing
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python3 not found. Installing...${NC}"
    apt-get update -qq && apt-get install -y python3 -qq
else
    echo -e "${GREEN}✓ Python3 is installed.${NC}"
fi

# Install Pip3 if missing
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}python3-pip not found. Installing...${NC}"
    apt-get update -qq && apt-get install -y python3-pip -qq
else
    echo -e "${GREEN}✓ Pip3 is installed.${NC}"
fi

# Install Python Library Dependencies
echo -e "${YELLOW}Installing Python library dependencies (dotenv, requests, flask)...${NC}"
pip3 install python-dotenv requests flask gunicorn --quiet --break-system-packages
echo -e "${GREEN}✓ Python libraries ready.${NC}"

echo -e "\n${YELLOW}[2/3] Checking configuration...${NC}"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[!] .env file missing at $ENV_FILE${NC}"
    echo -e "1) Create a new .env file now"
    echo -e "2) Provide path to an existing .env file"
    echo -e "3) Exit and fix manually"
    read -p "Select option (1-3): " env_choice

    case $env_choice in
        1)
            read -p "Enter SUPABASE_URL: " sb_url
            read -p "Enter SUPABASE_KEY: " sb_key
            read -p "Enter SERVER_REGION: " srv_region
            read -p "Enter SERVER_NAME: " srv_name
            read -p "Enter API_TOKEN (or enter for random): " api_token
            
            if [ -z "$api_token" ]; then
                api_token=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
                echo -e "Generated Token: $api_token"
            fi

            cat <<EOF > "$ENV_FILE"
SUPABASE_URL=$sb_url
SUPABASE_KEY=$sb_key
SERVER_REGION=$srv_region
SERVER_NAME=$srv_name
API_TOKEN=$api_token
EOF
            echo -e "${GREEN}✓ .env file created.${NC}"
            ;;
        2)
            read -p "Enter absolute path to your .env: " custom_path
            if [ -f "$custom_path" ]; then
                cp "$custom_path" "$ENV_FILE"
                echo -e "${GREEN}✓ .env copied to $BASE_DIR${NC}"
            else
                echo -e "${RED}File not found at $custom_path. Exiting.${NC}"
                exit 1
            fi
            ;;
        *)
            echo -e "Exiting."
            exit 0
            ;;
    esac
else
    echo -e "${GREEN}✓ .env file exists at $ENV_FILE${NC}"
fi

# 3. Final Handover
echo -e "\n${YELLOW}[3/3] Starting Provisioning Engine...${NC}"
if [ -f "$PROVISION_SCRIPT" ]; then
    chmod +x "$PROVISION_SCRIPT"
    # Execute provision.py using the specific python path
    python3 "$PROVISION_SCRIPT"
else
    echo -e "${RED}Error: provision.py not found in $BASE_DIR${NC}"
    echo -e "Please ensure provision.py is in the same folder as this script."
    exit 1
fi