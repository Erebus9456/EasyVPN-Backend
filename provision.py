import os
import sys
import json
import logging
import subprocess
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE = os.path.join(BASE_DIR, "vpn-setup.log")
ENV_FILE = os.path.join(BASE_DIR, ".env")
WG_CONF = "/etc/wireguard/wg0.conf"

class Colors:
    CYAN, GREEN, YELLOW, RED, BOLD, END = '\033[96m', '\033[92m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip()}"
    return result.stdout.strip()

def save_state(data):
    state = load_state()
    state.update(data)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def load_state():
    return json.load(open(STATE_FILE, 'r')) if os.path.exists(STATE_FILE) else {}

def setup_system():
    print(f"{Colors.CYAN}[1/5] Installing System & Python Dependencies...{Colors.END}")
    # We install python3-flask, python3-dotenv, python3-requests via APT to bypass PEP 668 restrictions
    run_command("apt update")
    run_command("apt install -y wireguard curl iptables gunicorn python3-flask python3-dotenv python3-requests")
    save_state({"deps_installed": True})
    print(f"{Colors.GREEN}[✓] Dependencies installed via APT.{Colors.END}")

def setup_networking():
    print(f"{Colors.CYAN}[2/5] Configuring NAT & Forwarding...{Colors.END}")
    run_command("sysctl -w net.ipv4.ip_forward=1")
    with open("/etc/sysctl.d/99-vpn.conf", "w") as f:
        f.write("net.ipv4.ip_forward=1\n")
    save_state({"networking_ready": True})

def setup_wireguard():
    print(f"{Colors.CYAN}[3/5] Initializing WireGuard...{Colors.END}")
    state = load_state()
    priv = state.get("private_key") or run_command("wg genkey")
    pub = state.get("public_key") or run_command(f"echo '{priv}' | wg pubkey")
    ip = run_command("curl -s https://icanhazip.com")
    
    iface = run_command(r"ip route get 8.8.8.8 | grep -Po '(?<=dev )(\S+)'")

    config = f"""[Interface]
PrivateKey = {priv}
Address = 10.0.0.1/24
ListenPort = 51820
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o {iface} -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -t nat -D POSTROUTING -o {iface} -j MASQUERADE
"""
    with open(WG_CONF, "w") as f: f.write(config)
    os.chmod(WG_CONF, 0o600)
    run_command("systemctl enable wg-quick@wg0 && systemctl restart wg-quick@wg0")
    save_state({"private_key": priv, "public_key": pub, "public_ip": ip, "wg_ready": True})

def setup_agent_service():
    print(f"{Colors.CYAN}[4/5] Deploying Flask Agent Service...{Colors.END}")
    gunicorn_path = run_command("which gunicorn") or "/usr/bin/gunicorn"

    service_content = f"""[Unit]
Description=EasyVPN Node Agent
After=network.target wg-quick@wg0.service

[Service]
User=root
WorkingDirectory={BASE_DIR}
ExecStart={gunicorn_path} --workers 2 --bind 0.0.0.0:5000 agent:app
Restart=always
EnvironmentFile={ENV_FILE}

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/easyvpn-agent.service", "w") as f:
        f.write(service_content)
    
    run_command("systemctl daemon-reload")
    run_command("systemctl enable easyvpn-agent")
    run_command("systemctl restart easyvpn-agent")
    print(f"{Colors.GREEN}[✓] Agent Service Active.{Colors.END}")

def register_supabase():
    print(f"{Colors.CYAN}[5/5] Syncing with Supabase (Upsert)...{Colors.END}")
    if not os.path.exists(ENV_FILE):
        print(f"{Colors.RED}Error: .env missing, cannot register.{Colors.END}")
        return

    load_dotenv(ENV_FILE)
    state = load_state()
    
    # Modern UTC timestamp
    now = datetime.now(timezone.utc).isoformat()
    
    payload = {
        "name": os.getenv("SERVER_NAME"),
        "region": os.getenv("SERVER_REGION"),
        "public_ip": state.get("public_ip"),
        "wireguard_public_key": state.get("public_key"),
        "status": "online",
        "last_heartbeat": now
    }
    
    # To perform an UPSERT in Supabase (PostgREST), we use POST with specific headers
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"), 
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}", 
        "Content-Type": "application/json", 
        "Prefer": "resolution=merge-duplicates" # This handles the 'Unique IP' constraint error
    }
    
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/vpn_servers"
    
    try:
        # We use on_conflict query param to tell Supabase which column to check for duplicates
        res = requests.post(f"{url}?on_conflict=public_ip", headers=headers, json=payload)
        if res.status_code not in [200, 201]:
            print(f"{Colors.RED}Supabase Error: {res.text}{Colors.END}")
        else:
            print(f"{Colors.GREEN}[✓] Server Registered/Updated successfully.{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Request failed: {e}{Colors.END}")

def main():
    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}⚡ EASYVPN-BACKEND CONTROL PANEL ⚡{Colors.END}")
        print("1. Full Setup (Fresh Install)")
        print("2. Run Diagnostics")
        print("3. View Logs")
        print("4. Exit")
        choice = input("\nSelect: ")
        
        try:
            if choice == '1':
                setup_system()
                setup_networking()
                setup_wireguard()
                setup_agent_service()
                register_supabase()
            elif choice == '2':
                print(f"WG: {run_command('systemctl is-active wg-quick@wg0')}")
                print(f"Agent: {run_command('systemctl is-active easyvpn-agent')}")
            elif choice == '3':
                os.system(f"tail -n 20 {LOG_FILE}")
            elif choice == '4':
                break
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.END}")

if __name__ == "__main__":
    main()