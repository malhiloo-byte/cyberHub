CREATE UNIQUE INDEX uq_asset_observations_context_bridge
    ON asset_observations (scope_id, target_id, task_id, id);

CREATE TABLE evidence_records (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    observation_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN (
        'observation_summary',
        'service_metadata',
        'http_metadata',
        'query_digest'
    )),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    content_digest TEXT NOT NULL CHECK (
        length(content_digest) = 64 AND
        content_digest NOT GLOB '*[^0-9a-f]*'
    ),
    content_size_bytes INTEGER NOT NULL CHECK (
        content_size_bytes BETWEEN 0 AND 1048576
    ),
    metadata_json TEXT NOT NULL CHECK (
        length(metadata_json) BETWEEN 2 AND 65536 AND
        json_valid(metadata_json) = 1 AND
        json_type(metadata_json) = 'object'
    ),
    source_plugin_id TEXT NOT NULL CHECK (length(trim(source_plugin_id)) BETWEEN 1 AND 80),
    source_plugin_version TEXT NOT NULL CHECK (
        length(trim(source_plugin_version)) BETWEEN 1 AND 64
    ),
    pipeline_id TEXT CHECK (pipeline_id IS NULL OR length(trim(pipeline_id)) BETWEEN 1 AND 200),
    pipeline_version TEXT CHECK (
        pipeline_version IS NULL OR length(trim(pipeline_version)) BETWEEN 1 AND 64
    ),
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (scope_id, target_id, task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, asset_id)
        REFERENCES assets(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id, observation_id)
        REFERENCES asset_observations(scope_id, target_id, task_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(scope_id)) = 36),
    CHECK (length(trim(target_id)) = 36),
    CHECK (length(trim(task_id)) = 36),
    CHECK (length(trim(asset_id)) = 36),
    CHECK (observation_id IS NULL OR length(trim(observation_id)) = 36),
    CHECK (length(collected_at) >= 25 AND substr(collected_at, -6) = '+00:00'),
    CHECK (length(created_at) >= 25 AND substr(created_at, -6) = '+00:00'),
    CHECK (length(updated_at) >= 25 AND substr(updated_at, -6) = '+00:00'),
    CHECK (
        archived_at IS NULL OR
        (length(archived_at) >= 25 AND substr(archived_at, -6) = '+00:00')
    ),
    CHECK (
        status = 'active' AND archived_at IS NULL OR
        status = 'archived' AND archived_at IS NOT NULL
    )
);

CREATE UNIQUE INDEX uq_evidence_idempotency
    ON evidence_records (
        task_id, asset_id, ifnull(observation_id, ''), kind, content_digest
    );

CREATE INDEX idx_evidence_scope_target_status
    ON evidence_records (scope_id, target_id, status, collected_at DESC);

CREATE INDEX idx_evidence_task_collected
    ON evidence_records (task_id, collected_at DESC, id ASC);

CREATE INDEX idx_evidence_asset_collected
    ON evidence_records (asset_id, collected_at DESC, id ASC);
