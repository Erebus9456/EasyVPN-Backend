-- For UI filtering by region
CREATE INDEX idx_vpn_servers_region ON vpn_servers(region);

-- For UI filtering only available servers
CREATE INDEX idx_vpn_servers_status ON vpn_servers(status);

-- For the backend to find "dead" servers that stopped heartbeating
CREATE INDEX idx_vpn_servers_heartbeat ON vpn_servers(last_heartbeat);