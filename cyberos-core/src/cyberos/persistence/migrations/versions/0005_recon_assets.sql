CREATE UNIQUE INDEX uq_tasks_scope_target_id_bridge
    ON tasks (scope_id, target_id, id);

CREATE UNIQUE INDEX uq_targets_scope_id_bridge
    ON targets (scope_id, id);

CREATE TABLE assets (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    asset_kind TEXT NOT NULL CHECK (asset_kind IN ('domain', 'subdomain', 'ip_address', 'host', 'url', 'service')),
    canonical_value TEXT NOT NULL,
    display_value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    first_seen_task_id TEXT NOT NULL,
    last_seen_task_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id) REFERENCES targets(scope_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, first_seen_task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, last_seen_task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(scope_id)) = 36),
    CHECK (length(trim(target_id)) = 36),
    CHECK (length(trim(first_seen_task_id)) = 36),
    CHECK (length(trim(last_seen_task_id)) = 36),
    CHECK (length(trim(canonical_value)) BETWEEN 1 AND 4096),
    CHECK (length(trim(display_value)) BETWEEN 1 AND 4096),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (status = 'active' AND archived_at IS NULL OR status = 'archived' AND archived_at IS NOT NULL),
    CHECK (length(first_seen_at) >= 25 AND substr(first_seen_at, -6) = '+00:00'),
    CHECK (length(last_seen_at) >= 25 AND substr(last_seen_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00'),
    CHECK (length(updated_at) >= 25 AND substr(updated_at, -6) = '+00:00'),
    CHECK (archived_at IS NULL OR (length(archived_at) >= 25 AND substr(archived_at, -6) = '+00:00'))
);

CREATE UNIQUE INDEX uq_assets_scope_target_kind_value ON assets (scope_id, target_id, asset_kind, canonical_value);
CREATE UNIQUE INDEX uq_assets_scope_target_id_bridge ON assets (scope_id, target_id, id);
CREATE INDEX idx_assets_scope_status_kind ON assets (scope_id, status, asset_kind);
CREATE INDEX idx_assets_target_last_seen ON assets (target_id, last_seen_at DESC);

CREATE TABLE asset_observations (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    result_digest TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scope_id, target_id, asset_id) REFERENCES assets(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id) REFERENCES targets(scope_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(asset_id)) = 36),
    CHECK (length(trim(plugin_id)) BETWEEN 1 AND 80),
    CHECK (length(trim(plugin_version)) BETWEEN 1 AND 64),
    CHECK (length(trim(contract_version)) BETWEEN 1 AND 16),
    CHECK (length(trim(result_digest)) = 64),
    CHECK (length(observed_at) >= 25 AND substr(observed_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00')
);
CREATE UNIQUE INDEX uq_asset_observations_idempotency ON asset_observations (asset_id, task_id, plugin_id, result_digest);
CREATE INDEX idx_asset_observations_target_seen ON asset_observations (target_id, observed_at DESC);

CREATE TABLE subdomain_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    fqdn TEXT NOT NULL,
    parent_domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id) REFERENCES assets(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id) REFERENCES targets(scope_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(fqdn)) BETWEEN 1 AND 4096),
    CHECK (length(trim(parent_domain)) BETWEEN 1 AND 4096),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (length(first_seen_at) >= 25 AND substr(first_seen_at, -6) = '+00:00'),
    CHECK (length(last_seen_at) >= 25 AND substr(last_seen_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00'),
    CHECK (length(updated_at) >= 25 AND substr(updated_at, -6) = '+00:00'),
    CHECK (archived_at IS NULL OR (length(archived_at) >= 25 AND substr(archived_at, -6) = '+00:00')),
    CHECK (status = 'active' AND archived_at IS NULL OR status = 'archived' AND archived_at IS NOT NULL)
);
CREATE UNIQUE INDEX uq_subdomains_scope_target_fqdn ON subdomain_records (scope_id, target_id, fqdn);
CREATE INDEX idx_subdomains_scope_status ON subdomain_records (scope_id, status, last_seen_at DESC);

CREATE TABLE port_service_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    transport TEXT NOT NULL CHECK (transport IN ('tcp', 'udp')),
    port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    service_name TEXT,
    product TEXT,
    service_version TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id) REFERENCES assets(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id) REFERENCES targets(scope_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (service_name IS NULL OR length(trim(service_name)) BETWEEN 1 AND 160),
    CHECK (product IS NULL OR length(trim(product)) BETWEEN 1 AND 256),
    CHECK (service_version IS NULL OR length(trim(service_version)) BETWEEN 1 AND 128),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (length(first_seen_at) >= 25 AND substr(first_seen_at, -6) = '+00:00'),
    CHECK (length(last_seen_at) >= 25 AND substr(last_seen_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00'),
    CHECK (length(updated_at) >= 25 AND substr(updated_at, -6) = '+00:00'),
    CHECK (archived_at IS NULL OR (length(archived_at) >= 25 AND substr(archived_at, -6) = '+00:00')),
    CHECK (status = 'active' AND archived_at IS NULL OR status = 'archived' AND archived_at IS NOT NULL)
);
CREATE UNIQUE INDEX uq_services_scope_target_asset_transport_port ON port_service_records (scope_id, target_id, asset_id, transport, port);
CREATE INDEX idx_services_scope_status_port ON port_service_records (scope_id, status, port);

CREATE TABLE http_endpoint_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    scheme TEXT NOT NULL CHECK (scheme IN ('http', 'https')),
    port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    path TEXT NOT NULL,
    query_fingerprint TEXT,
    status_code INTEGER,
    title TEXT,
    technologies_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id) REFERENCES assets(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id) REFERENCES targets(scope_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id) REFERENCES tasks(scope_id, target_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(path)) BETWEEN 1 AND 4096),
    CHECK (substr(path, 1, 1) = '/'),
    CHECK (query_fingerprint IS NULL OR length(trim(query_fingerprint)) = 64),
    CHECK (status_code IS NULL OR status_code BETWEEN 100 AND 599),
    CHECK (title IS NULL OR length(title) <= 512),
    CHECK (json_valid(technologies_json) = 1 AND json_type(technologies_json) = 'array'),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (length(first_seen_at) >= 25 AND substr(first_seen_at, -6) = '+00:00'),
    CHECK (length(last_seen_at) >= 25 AND substr(last_seen_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00'),
    CHECK (length(updated_at) >= 25 AND substr(updated_at, -6) = '+00:00'),
    CHECK (archived_at IS NULL OR (length(archived_at) >= 25 AND substr(archived_at, -6) = '+00:00')),
    CHECK (status = 'active' AND archived_at IS NULL OR status = 'archived' AND archived_at IS NOT NULL)
);
CREATE UNIQUE INDEX uq_http_scope_target_asset_scheme_port_path ON http_endpoint_records (scope_id, target_id, asset_id, scheme, port, path);
CREATE INDEX idx_http_scope_status_last_seen ON http_endpoint_records (scope_id, status, last_seen_at DESC);
