CREATE TABLE workspaces (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(name)) BETWEEN 1 AND 120),
    CHECK (length(description) <= 4000),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_workspaces_name_nocase
    ON workspaces (name COLLATE NOCASE);

CREATE TABLE engagements (
    id TEXT PRIMARY KEY NOT NULL,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    kind TEXT NOT NULL
        CHECK (kind IN ('learning', 'authorized_assessment', 'research')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    description TEXT NOT NULL DEFAULT '',
    authorization_reference TEXT,
    start_at TEXT,
    end_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(workspace_id)) = 36),
    CHECK (length(trim(name)) BETWEEN 1 AND 160),
    CHECK (length(description) <= 4000),
    CHECK (
        authorization_reference IS NULL
        OR length(authorization_reference) <= 1000
    ),
    CHECK (
        start_at IS NULL
        OR end_at IS NULL
        OR end_at >= start_at
    ),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (status <> 'archived' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    ),
    CHECK (
        NOT (
            kind = 'authorized_assessment'
            AND status = 'active'
            AND length(trim(coalesce(authorization_reference, ''))) = 0
        )
    ),
    CHECK (status <> 'completed' OR end_at IS NOT NULL)
);

CREATE INDEX idx_engagements_workspace_id
    ON engagements (workspace_id);

CREATE UNIQUE INDEX uq_engagements_workspace_name_nocase
    ON engagements (workspace_id, name COLLATE NOCASE);

CREATE INDEX idx_engagements_workspace_status
    ON engagements (workspace_id, status);

CREATE INDEX idx_engagements_created_at
    ON engagements (created_at);
