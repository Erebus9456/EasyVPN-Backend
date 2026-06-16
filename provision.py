import os
import sys
import json
import logging
import subprocess
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# --- DYNAMIC PATH INITIALIZATION ---
# Get the absolute path of the directory containing this script
DEFAULT_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Colors:
    CYAN, GREEN, YELLOW, RED, BOLD, END = '\033[96m', '\033[92m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'

# We will set these globally after path validation
BASE_DIR = DEFAULT_BASE_DIR
STATE_FILE = ""
LOG_FILE = ""
ENV_FILE = ""
WG_CONF = "/etc/wireguard/wg0.conf"

def initialize_paths(custom_env_path=None):
    global BASE_DIR, STATE_FILE, LOG_FILE, ENV_FILE
    if custom_env_path:
        ENV_FILE = custom_env_path
        BASE_DIR = os.path.dirname(os.path.abspath(ENV_FILE))
    else:
        ENV_FILE = os.path.join(DEFAULT_BASE_DIR, ".env")
        BASE_DIR = DEFAULT_BASE_DIR

    STATE_FILE = os.path.join(BASE_DIR, "state.json")
    LOG_FILE = os.path.join(BASE_DIR, "vpn-setup.log")

def ensure_env_exists():
    global ENV_FILE
    # Try default path first
    initialize_paths()
    
    if os.path.exists(ENV_FILE):
        print(f"{Colors.GREEN}[✓] Found .env at: {ENV_FILE}{Colors.END}")
        return True

    print(f"{Colors.YELLOW}[!] .env file not found at default path: {ENV_FILE}{Colors.END}")
    print("How would you like to proceed?")
    print("1. Enter absolute path to existing .env file")
    print("2. Create a new .env file interactively")
    print("3. Exit")
    
    choice = input("Select (1-3): ")
    
    if choice == '1':
        path = input("Enter full path (e.g. /root/EasyVPN-Backend/.env): ").strip()
        if os.path.exists(path):
            initialize_paths(path)
            return True
        else:
            print(f"{Colors.RED}Path does not exist. Exiting.{Colors.END}")
            sys.exit(1)
            
    elif choice == '2':
        sb_url = input("Enter SUPABASE_URL: ").strip()
        sb_key = input("Enter SUPABASE_KEY: ").strip()
        region = input("Enter SERVER_REGION: ").strip()
        name = input("Enter SERVER_NAME: ").strip()
        token = input("Enter API_TOKEN (or press enter for random): ").strip()
        if not token:
            import secrets
            token = secrets.token_urlsafe(24)
            print(f"Generated Token: {token}")
        
        # Determine where to save it
        save_dir = input(f"Enter directory to save .env [default: {DEFAULT_BASE_DIR}]: ").strip() or DEFAULT_BASE_DIR
        os.makedirs(save_dir, exist_ok=True)
        ENV_FILE = os.path.join(save_dir, ".env")
        
        with open(ENV_FILE, "w") as f:
            f.write(f"SUPABASE_URL={sb_url}\n")
            f.write(f"SUPABASE_KEY={sb_key}\n")
            f.write(f"SERVER_REGION={region}\n")
            f.write(f"SERVER_NAME={name}\n")
            f.write(f"API_TOKEN={token}\n")
        
        initialize_paths(ENV_FILE)
        print(f"{Colors.GREEN}[✓] .env created at {ENV_FILE}{Colors.END}")
        return True
    else:
        sys.exit(0)

# Initialize paths immediately
ensure_env_exists()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])

# --- UTILITIES ---

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

# --- CORE PROVISIONING LOGIC ---

def setup_system():
    print(f"{Colors.CYAN}[1/5] Installing System & Python Dependencies...{Colors.END}")
    run_command("apt update")
    run_command("apt install -y wireguard curl iptables gunicorn python3-flask python3-dotenv python3-requests")
    save_state({"deps_installed": True})

def setup_networking():
    print(f"{Colors.CYAN}[2/5] Configuring NAT & Azure Firewall Rules...{Colors.END}")
    run_command("sysctl -w net.ipv4.ip_forward=1")
    
    # OS level firewall rules (Iptables)
    run_command("iptables -I INPUT 1 -p tcp --dport 5000 -j ACCEPT")
    run_command("iptables -I INPUT 1 -p udp --dport 51820 -j ACCEPT")
    
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
    with open("/etc/systemd/system/easyvpn-agent.service", "w") as f: f.write(service_content)
    run_command("systemctl daemon-reload && systemctl enable easyvpn-agent && systemctl restart easyvpn-agent")

def register_supabase():
    print(f"{Colors.CYAN}[5/5] Syncing with Supabase (Upsert)...{Colors.END}")
    load_dotenv(ENV_FILE)
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "name": os.getenv("SERVER_NAME"),
        "region": os.getenv("SERVER_REGION"),
        "public_ip": state.get("public_ip"),
        "wireguard_public_key": state.get("public_key"),
        "status": "online",
        "last_heartbeat": now
    }
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"), 
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}", 
        "Content-Type": "application/json", 
        "Prefer": "resolution=merge-duplicates"
    }
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/vpn_servers"
    try:
        res = requests.post(f"{url}?on_conflict=public_ip", headers=headers, json=payload, timeout=10)
        if res.status_code in [200, 201]:
            print(f"{Colors.GREEN}[✓] Supabase Registered Successfully.{Colors.END}")
        else:
            print(f"{Colors.RED}Supabase Error: {res.text}{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Request to Supabase failed: {e}{Colors.END}")

# --- DASHBOARD FEATURES ---

def check_local_status():
    print(f"\n{Colors.BOLD}🔍 Checking Local Server Status...{Colors.END}")
    try:
        res = requests.get("http://127.0.0.1:5000/health", timeout=3)
        if res.status_code == 200:
            print(f"Status: {Colors.GREEN}ONLINE (Localhost Responding){Colors.END}")
            return True
    except:
        print(f"Status: {Colors.RED}OFFLINE (Internal API not reachable){Colors.END}")
    return False

def check_network_diagnostics():
    state = load_state()
    public_ip = state.get("public_ip") or run_command("curl -s https://icanhazip.com")
    
    print(f"\n{Colors.BOLD}🌎 Checking Global Connectivity Diagnostics...{Colors.END}")
    
    local_ok = check_local_status()

    # 2. Global Check
    global_ok = False
    try:
        requests.get(f"http://{public_ip}:5000/health", timeout=3)
        global_ok = True
        print(f" - Global API ({public_ip}:5000): {Colors.GREEN}OK{Colors.END}")
    except:
        print(f" - Global API ({public_ip}:5000): {Colors.RED}FAIL{Colors.END}")

    if local_ok and not global_ok:
        print(f"\n{Colors.YELLOW}[!] ALERT: Firewall Block Detected!{Colors.END}")
        print(f"The service is running fine locally, but cannot be reached from the internet.")
        print(f"👉 {Colors.BOLD}ACTION REQUIRED:{Colors.END} Go to your Azure NSG (Network Security Group)")
        print(f"and fix the Inbound rule for {Colors.BOLD}Port 5000 (Source: Any, Port: *, Dest: 5000){Colors.END}")
    elif not local_ok:
        print(f"\n{Colors.RED}[!] Service Issue: The API server is down.{Colors.END}")
    else:
        print(f"\n{Colors.GREEN}[✓] Global connection confirmed!{Colors.END}")

def manage_service(action):
    print(f"\n{Colors.BOLD}[*] Performing {action} on Agent Server...{Colors.END}")
    if action == "START":
        run_command("systemctl start easyvpn-agent")
        print(f"{Colors.GREEN}Start command sent.{Colors.END}")
    elif action == "STOP":
        run_command("systemctl stop easyvpn-agent")
        print(f"{Colors.YELLOW}Stop command sent.{Colors.END}")

# --- MAIN MENU ---

def main():
    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}⚡ EASYVPN-BACKEND CONTROL PANEL ⚡{Colors.END}")
        print(f"Config: {ENV_FILE}")
        print("1. Full Setup (Fresh Install)")
        print("2. Run General Diagnostics")
        print("3. View Logs")
        print("----------------------------")
        print("4. Check Server Status (Local)")
        print("5. Firewall / Global Access Check")
        print("6. Start Agent Server")
        print("7. Stop Agent Server")
        print("----------------------------")
        print("8. Exit")
        
        choice = input("\nSelect: ")
        
        try:
            if choice == '1':
                setup_system(); setup_networking(); setup_wireguard(); setup_agent_service(); register_supabase()
            elif choice == '2':
                print(f"WG: {run_command('systemctl is-active wg-quick@wg0')}")
                print(f"Agent: {run_command('systemctl is-active easyvpn-agent')}")
            elif choice == '3':
                if os.path.exists(LOG_FILE):
                    os.system(f"tail -n 20 {LOG_FILE}")
                else:
                    print(f"{Colors.YELLOW}Log file not found.{Colors.END}")
            elif choice == '4':
                check_local_status()
            elif choice == '5':
                check_network_diagnostics()
            elif choice == '6':
                manage_service("START")
            elif choice == '7':
                manage_service("STOP")
            elif choice == '8':
                break
            
            if choice in ['4', '5', '6', '7']:
                input(f"\n{Colors.CYAN}Press Enter to return to menu...{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.END}")

if __name__ == "__main__":
    main()