CREATE TABLE vpn_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    public_ip INET NOT NULL,
    wireguard_public_key TEXT NOT NULL,
    endpoint_port INTEGER NOT NULL DEFAULT 51820,
    status vpn_server_status NOT NULL DEFAULT 'offline',
    last_heartbeat TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),

    -- Constraints
    CONSTRAINT unique_public_ip UNIQUE (public_ip),
    CONSTRAINT unique_wg_pubkey UNIQUE (wireguard_public_key),
    CONSTRAINT valid_port CHECK (endpoint_port > 0 AND endpoint_port < 65536)
);

CREATE TABLE server_metadata (
    server_id UUID PRIMARY KEY REFERENCES vpn_servers(id) ON DELETE CASCADE,
    country_code CHAR(2) NOT NULL, -- ISO 3166-1 alpha-2
    city TEXT,
    isp_name TEXT,
    max_clients INTEGER DEFAULT 100,
    is_premium BOOLEAN DEFAULT false
);