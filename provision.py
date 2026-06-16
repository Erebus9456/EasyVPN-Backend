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
    with open("/etc/systemd/system/easyvpn-agent.service", "w") as f: f.write(service_content)
    run_command("systemctl daemon-reload && systemctl enable easyvpn-agent && systemctl restart easyvpn-agent")

def register_supabase():
    print(f"{Colors.CYAN}[5/5] Syncing with Supabase (Upsert)...{Colors.END}")
    if not os.path.exists(ENV_FILE): return
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
    headers = {"apikey": os.getenv("SUPABASE_KEY"), "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/vpn_servers"
    try:
        requests.post(f"{url}?on_conflict=public_ip", headers=headers, json=payload, timeout=5)
    except: pass

# --- NEW DASHBOARD FEATURES ---

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
    
    # 1. Local Check
    local_ok = False
    try:
        requests.get("http://127.0.0.1:5000/health", timeout=2)
        local_ok = True
        print(f" - Local API (127.0.0.1:5000): {Colors.GREEN}OK{Colors.END}")
    except:
        print(f" - Local API (127.0.0.1:5000): {Colors.RED}FAIL{Colors.END}")

    # 2. Global Check
    global_ok = False
    try:
        requests.get(f"http://{public_ip}:5000/health", timeout=3)
        global_ok = True
        print(f" - Global API ({public_ip}:5000): {Colors.GREEN}OK{Colors.END}")
    except:
        print(f" - Global API ({public_ip}:5000): {Colors.RED}FAIL{Colors.END}")

    # 3. Interpretation
    if local_ok and not global_ok:
        print(f"\n{Colors.YELLOW}[!] ALERT: Firewall Block Detected!{Colors.END}")
        print(f"The service is running fine locally, but cannot be reached from the internet.")
        print(f"👉 {Colors.BOLD}ACTION REQUIRED:{Colors.END} Go to your VPS Provider Dashboard (AWS, GCP, etc.)")
        print(f"and open {Colors.BOLD}TCP Port 5000{Colors.END} in the Security Group/Firewall settings.")
    elif not local_ok:
        print(f"\n{Colors.RED}[!] Service Issue: The API server itself is down or crashing.{Colors.END}")
    else:
        print(f"\n{Colors.GREEN}[✓] Everything is working perfectly!{Colors.END}")

def manage_service(action):
    print(f"\n{Colors.BOLD}[*] Performing {action} on Agent Server...{Colors.END}")
    
    if action == "START":
        is_active = run_command("systemctl is-active easyvpn-agent")
        if is_active == "active":
            print(f"{Colors.GREEN}Server is already UP.{Colors.END}")
        else:
            run_command("systemctl start easyvpn-agent")
            print(f"{Colors.GREEN}Server STARTED.{Colors.END}")
            
    elif action == "STOP":
        is_active = run_command("systemctl is-active easyvpn-agent")
        if is_active == "active":
            run_command("systemctl stop easyvpn-agent")
            print(f"{Colors.YELLOW}Server STOPPED.{Colors.END}")
        else:
            print(f"{Colors.YELLOW}Server is already DOWN.{Colors.END}")

# --- MAIN MENU ---

def main():
    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}⚡ EASYVPN-BACKEND CONTROL PANEL ⚡{Colors.END}")
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
                os.system(f"tail -n 20 {LOG_FILE}")
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