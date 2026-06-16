import os
import json
import logging
import subprocess
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load env from the current directory
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"))

app = Flask(__name__)

# --- CONFIGURATION ---
STATE_FILE = os.path.join(base_dir, "state.json")
PEERS_DATA_FILE = os.path.join(base_dir, "peers.json")
WG_CONF_PATH = "/etc/wireguard/wg0.conf"
API_TOKEN = os.getenv("API_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(os.path.join(base_dir, "vpn-agent.log")), logging.StreamHandler()]
)

def load_server_metadata():
    """Loads server keys and public IP from the state file."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load state.json: {e}")
        return None

def get_next_ip():
    """Assigns 10.0.0.x IPs. Avoids .1 (Server)."""
    if not os.path.exists(PEERS_DATA_FILE):
        with open(PEERS_DATA_FILE, "w") as f:
            json.dump({"assigned_ips": [1]}, f)
    
    with open(PEERS_DATA_FILE, "r+") as f:
        data = json.load(f)
        last_ip = max(data["assigned_ips"])
        if last_ip >= 254:
            raise Exception("Subnet full (10.0.0.254 reached)")
        
        next_ip = last_ip + 1
        data["assigned_ips"].append(next_ip)
        f.seek(0)
        json.dump(data, f)
        f.truncate()
        return f"10.0.0.{next_ip}"

@app.route('/add-peer', methods=['POST'])
def add_peer():
    token = request.headers.get("X-API-TOKEN")
    if not token or token != API_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    client_pubkey = data.get("public_key")
    if not client_pubkey:
        return jsonify({"error": "Missing public_key"}), 400

    state = load_server_metadata()
    if not state:
        return jsonify({"error": "Server not provisioned"}), 500

    try:
        client_ip = get_next_ip()
        
        # 1. Update Runtime
        subprocess.run(["wg", "set", "wg0", "peer", client_pubkey, "allowed-ips", f"{client_ip}/32"], check=True)
        
        # 2. Update Config for persistence
        with open(WG_CONF_PATH, "a") as f:
            f.write(f"\n[Peer]\nPublicKey = {client_pubkey}\nAllowedIPs = {client_ip}/32\n")

        return jsonify({
            "status": "success",
            "client_ip": client_ip,
            "server_public_key": state["public_key"],
            "endpoint": f"{state['public_ip']}:51820",
            "dns": "1.1.1.1",
            "allowed_ips": "0.0.0.0/0"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "online", "region": os.getenv("SERVER_REGION")})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)