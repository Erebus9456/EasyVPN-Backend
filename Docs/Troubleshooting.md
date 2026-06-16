# ⚡ EasyVPN — Troubleshooting Guide

> This guide helps you diagnose and fix common issues in EasyVPN deployments.

**[← README](../README.md)** · [Getting Started](GettingStarted.md) · [Architecture](Architecture.md) · [Deployment](Deployment.md) · [API Reference](API_Reference.md) · [Security](Security.md)

---

## Overview

Most issues in EasyVPN fall into one of four categories:

* Networking / firewall misconfiguration
* WireGuard interface issues
* Agent service failures
* Peer provisioning problems

---

## 1. Node Not Appearing in Dashboard

### Symptoms

* VPS is running
* No entry in Supabase registry
* Dashboard shows no nodes

### Possible Causes

* `.env` not configured correctly
* Supabase connection failed
* `provision.py` did not complete

### Fix

Run provisioning again:

```bash id="tr01"
python3 provision.py
```

Check logs:

```bash id="tr02"
journalctl -u easyvpn-agent -f
```

---

## 2. Cannot Connect to VPN

### Symptoms

* WireGuard config generated
* Connection fails on client
* No internet access through tunnel

### Possible Causes

* UDP 51820 blocked
* NAT not configured
* IP forwarding disabled

### Fix

### Step 1 — Verify firewall

Ensure:

* UDP 51820 is open at VPS provider level

---

### Step 2 — Check WireGuard

```bash id="tr03"
wg show
```

If empty:

```bash id="tr04"
systemctl restart easyvpn-agent
```

---

### Step 3 — Check IP forwarding

```bash id="tr05"
sysctl net.ipv4.ip_forward
```

Expected:

```text id="tr06"
net.ipv4.ip_forward = 1
```

---

## 3. `/add-peer` Returns Error

### Symptoms

* API request fails
* Backend cannot create VPN user

### Possible Causes

* Missing `X-API-TOKEN`
* Invalid JSON payload
* No available IPs

### Fix

### Check request format:

```bash id="tr07"
curl -X POST http://<VPS_IP>:5000/add-peer \
  -H "X-API-TOKEN: your_token" \
  -H "Content-Type: application/json" \
  -d '{"public_key": "CLIENT_KEY"}'
```

---

## 4. WireGuard Interface Not Found

### Symptoms

* `wg0` missing
* `wg show` returns empty

### Fix

Restart agent:

```bash id="tr08"
systemctl restart easyvpn-agent
```

Then verify:

```bash id="tr09"
ip a | grep wg0
```

---

## 5. High Latency or Slow VPN

### Possible Causes

* VPS region far from user
* Network congestion
* CPU throttling on low-tier VPS

### Fixes

* Deploy nodes closer to users
* Use multiple VPS regions
* Upgrade VPS plan

---

## 6. Peer Not Connecting

### Symptoms

* Peer exists in `wg show`
* Client shows handshake failure

### Possible Causes

* Wrong public key
* Incorrect endpoint IP
* Firewall blocking UDP

### Fix

Check peer config:

```bash id="tr10"
wg show wg0
```

Re-generate client config from backend.

---

## 7. Agent Service Crashed

### Symptoms

* `/add-peer` stops responding
* No logs updating

### Fix

Check systemd service:

```bash id="tr11"
systemctl status easyvpn-agent
```

Restart if needed:

```bash id="tr12"
systemctl restart easyvpn-agent
```

Enable auto-restart:

```bash id="tr13"
systemctl enable easyvpn-agent
```

---

## 8. Supabase Sync Issues

### Symptoms

* Node not updating heartbeat
* Dashboard shows offline node incorrectly

### Possible Causes

* `.env` Supabase key invalid
* Network issue from VPS

### Fix

Verify environment:

```bash id="tr14"
cat .env
```

Restart provisioning service:

```bash id="tr15"
systemctl restart easyvpn-agent
```

---

## 9. No Internet Through VPN

### Symptoms

* VPN connects
* No browsing / traffic fails

### Most Likely Cause

NAT not configured properly

### Fix

Ensure provisioning script ran successfully:

```bash id="tr16"
python3 provision.py
```

Then verify iptables:

```bash id="tr17"
iptables -t nat -L -n -v
```

---

## 10. Complete Reset (Last Resort)

If everything breaks:

```bash id="tr18"
systemctl stop easyvpn-agent
rm -rf /root/EasyVPN-Backend/pb_data
rm -rf /root/EasyVPN-Backend/state.json
rm -rf /root/EasyVPN-Backend/peers.json
```

Then redeploy:

```bash id="tr19"
./bootstrap.sh
python3 provision.py
```

---

## Debug Checklist

* [ ] Port 5000 reachable (internal only)
* [ ] Port 51820 open (UDP)
* [ ] WireGuard interface exists
* [ ] systemd service running
* [ ] Supabase connection active
* [ ] IP forwarding enabled

---

## Key Command Reference

```bash id="tr20"
wg show
ip a
systemctl status easyvpn-agent
journalctl -u easyvpn-agent -f
```

---

## When All Else Fails

Rebuild the node:

> EasyVPN is designed to be fully reproducible.

A fresh VPS + bootstrap script will always restore a working node.

---

## Next Steps

Continue reading:

* [Getting Started](GettingStarted.md) — initial setup and provisioning
* [Deployment Guide](Deployment.md) — production architecture

---

## Documentation

| Guide | Description |
| ----- | ----------- |
| [README](../README.md) | Project overview |
| [Getting Started](GettingStarted.md) | Initial installation and setup |
| [Architecture](Architecture.md) | System architecture and design |
| [Deployment](Deployment.md) | Production deployment guide |
| [API Reference](API_Reference.md) | Agent API documentation |
| [Security](Security.md) | Security model and best practices |
| [Troubleshooting](Troubleshooting.md) | Common issues and fixes |
