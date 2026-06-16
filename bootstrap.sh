#!/bin/bash

# --- CONFIGURATION ---
BASE_DIR="/root/EasyVPN-Backend"
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
echo -e "${BLUE}================================================${NC}"

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root.${NC}"
   exit 1
fi

echo -e "\n${YELLOW}[1/3] Checking system requirements...${NC}"

# Install Python3 if missing
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python3 not found. Installing...${NC}"
    apt-get update && apt-get install -y python3
else
    echo -e "${GREEN}✓ Python3 is installed.${NC}"
fi

# Install Pip3 if missing
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}python3-pip not found. Installing...${NC}"
    apt-get update && apt-get install -y python3-pip
else
    echo -e "${GREEN}✓ Pip3 is installed.${NC}"
fi

# NEW: Install Python Library Dependencies
echo -e "${YELLOW}Installing Python library dependencies (dotenv, requests, flask)...${NC}"
pip3 install python-dotenv requests flask gunicorn --quiet
echo -e "${GREEN}✓ Python libraries ready.${NC}"

echo -e "\n${YELLOW}[2/3] Checking configuration...${NC}"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Configuration file (.env) missing. Let's create it.${NC}\n"

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
    echo -e "\n${GREEN}✓ .env file created successfully.${NC}"
else
    echo -e "${GREEN}✓ .env file exists.${NC}"
fi

echo -e "\n${YELLOW}[3/3] Starting Provisioning Engine...${NC}"
if [ -f "$PROVISION_SCRIPT" ]; then
    chmod +x "$PROVISION_SCRIPT"
    python3 "$PROVISION_SCRIPT"
else
    echo -e "${RED}Error: provision.py not found in $BASE_DIR${NC}"
    exit 1
fi