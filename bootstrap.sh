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
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}    🚀 EasyVPN-Backend Bootstrapper           ${NC}"
echo -e "${BLUE}================================================${NC}"

# 1. Check for Root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root.${NC}"
   exit 1
fi

# 2. Check for Python & Pip
echo -e "\n${YELLOW}[1/3] Checking system requirements...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python3 not found. Installing...${NC}"
    apt-get update && apt-get install -y python3
else
    echo -e "${GREEN}✓ Python3 is installed.${NC}"
fi

if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}python3-pip not found. Installing...${NC}"
    apt-get update && apt-get install -y python3-pip
else
    echo -e "${GREEN}✓ Pip3 is installed.${NC}"
fi

# 3. Check for .env File
echo -e "\n${YELLOW}[2/3] Checking configuration...${NC}"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Configuration file (.env) missing. Let's create it.${NC}\n"

    echo -e "${BLUE}--- FIELD 1: SUPABASE_URL ---${NC}"
    echo -e "Description: The API URL for your Supabase project."
    echo -e "Why: This allows the server to register itself so clients can find it."
    read -p "Enter SUPABASE_URL: " sb_url

    echo -e "\n${BLUE}--- FIELD 2: SUPABASE_KEY ---${NC}"
    echo -e "Description: Your Supabase Service Role Key."
    echo -e "Why: Used to securely authenticate writes to the vpn_servers table."
    read -p "Enter SUPABASE_KEY: " sb_key

    echo -e "\n${BLUE}--- FIELD 3: SERVER_REGION ---${NC}"
    echo -e "Description: Geographic location (e.g., 'us-east-1', 'frankfurt')."
    echo -e "Why: Helps users select the closest server in the UI."
    read -p "Enter SERVER_REGION: " srv_region

    echo -e "\n${BLUE}--- FIELD 4: SERVER_NAME ---${NC}"
    echo -e "Description: A friendly name for this node (e.g., 'atlanta-prod-01')."
    echo -e "Why: Identification for logs and monitoring."
    read -p "Enter SERVER_NAME: " srv_name

    echo -e "\n${BLUE}--- FIELD 5: API_TOKEN ---${NC}"
    echo -p "Description: A secret string of your choice."
    echo -e "Why: Secures the Flask API so only YOUR backend can add VPN peers."
    read -p "Enter API_TOKEN (or press enter for random): " api_token
    
    if [ -z "$api_token" ]; then
        api_token=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
        echo -e "Generated Token: $api_token"
    fi

    # Write to .env
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

# 4. Handover to Provision.py
echo -e "\n${YELLOW}[3/3] Starting Provisioning Engine...${NC}"
if [ -f "$PROVISION_SCRIPT" ]; then
    chmod +x "$PROVISION_SCRIPT"
    python3 "$PROVISION_SCRIPT"
else
    echo -e "${RED}Error: provision.py not found in $BASE_DIR${NC}"
    exit 1
fi