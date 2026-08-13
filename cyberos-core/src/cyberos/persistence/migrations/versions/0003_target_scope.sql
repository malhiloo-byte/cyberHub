CREATE TABLE scopes (
    id TEXT PRIMARY KEY NOT NULL,
    engagement_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'authorized', 'archived')),
    authorization_reference TEXT,
    validated_at TEXT,
    authorized_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (engagement_id)
        REFERENCES engagements(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(engagement_id)) = 36),
    CHECK (length(trim(name)) BETWEEN 1 AND 160),
    CHECK (length(description) <= 4000),
    CHECK (
        authorization_reference IS NULL
        OR length(trim(authorization_reference)) BETWEEN 1 AND 1000
    ),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (
            length(created_at) >= 25
            AND substr(created_at, 5, 1) = '-'
            AND substr(created_at, 8, 1) = '-'
            AND substr(created_at, 11, 1) = 'T'
            AND substr(created_at, 14, 1) = ':'
            AND substr(created_at, 17, 1) = ':'
            AND substr(created_at, -6) = '+00:00'
        )
    ),
    CHECK (
        (
            length(updated_at) >= 25
            AND substr(updated_at, 5, 1) = '-'
            AND substr(updated_at, 8, 1) = '-'
            AND substr(updated_at, 11, 1) = 'T'
            AND substr(updated_at, 14, 1) = ':'
            AND substr(updated_at, 17, 1) = ':'
            AND substr(updated_at, -6) = '+00:00'
        )
    ),
    CHECK (
        validated_at IS NULL
        OR (
            length(validated_at) >= 25
            AND substr(validated_at, 5, 1) = '-'
            AND substr(validated_at, 8, 1) = '-'
            AND substr(validated_at, 11, 1) = 'T'
            AND substr(validated_at, 14, 1) = ':'
            AND substr(validated_at, 17, 1) = ':'
            AND substr(validated_at, -6) = '+00:00'
        )
    ),
    CHECK (
        authorized_at IS NULL
        OR (
            length(authorized_at) >= 25
            AND substr(authorized_at, 5, 1) = '-'
            AND substr(authorized_at, 8, 1) = '-'
            AND substr(authorized_at, 11, 1) = 'T'
            AND substr(authorized_at, 14, 1) = ':'
            AND substr(authorized_at, 17, 1) = ':'
            AND substr(authorized_at, -6) = '+00:00'
        )
    ),
    CHECK (
        expires_at IS NULL
        OR (
            length(expires_at) >= 25
            AND substr(expires_at, 5, 1) = '-'
            AND substr(expires_at, 8, 1) = '-'
            AND substr(expires_at, 11, 1) = 'T'
            AND substr(expires_at, 14, 1) = ':'
            AND substr(expires_at, 17, 1) = ':'
            AND substr(expires_at, -6) = '+00:00'
        )
    ),
    CHECK (
        archived_at IS NULL
        OR (
            length(archived_at) >= 25
            AND substr(archived_at, 5, 1) = '-'
            AND substr(archived_at, 8, 1) = '-'
            AND substr(archived_at, 11, 1) = 'T'
            AND substr(archived_at, 14, 1) = ':'
            AND substr(archived_at, 17, 1) = ':'
            AND substr(archived_at, -6) = '+00:00'
        )
    ),
    CHECK (
        (status = 'draft'
            AND validated_at IS NULL
            AND authorized_at IS NULL
            AND authorization_reference IS NULL
            AND expires_at IS NULL
            AND archived_at IS NULL)
        OR
        (status = 'validated'
            AND validated_at IS NOT NULL
            AND authorized_at IS NULL
            AND authorization_reference IS NULL
            AND expires_at IS NULL
            AND archived_at IS NULL)
        OR
        (status = 'authorized'
            AND validated_at IS NOT NULL
            AND authorized_at IS NOT NULL
            AND length(trim(coalesce(authorization_reference, ''))) > 0
            AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    ),
    CHECK (expires_at IS NULL OR authorized_at IS NOT NULL),
    CHECK (expires_at IS NULL OR expires_at > authorized_at)
);

CREATE UNIQUE INDEX uq_scopes_engagement_name_nocase
    ON scopes (engagement_id, name COLLATE NOCASE);

CREATE INDEX idx_scopes_engagement_status
    ON scopes (engagement_id, status);

CREATE INDEX idx_scopes_created_at
    ON scopes (created_at);

CREATE TABLE targets (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    rule TEXT NOT NULL
        CHECK (rule IN ('include', 'exclude')),
    kind TEXT NOT NULL
        CHECK (kind IN ('fqdn', 'wildcard', 'ipv4', 'ipv6', 'cidr', 'url')),
    value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (scope_id)
        REFERENCES scopes(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(scope_id)) = 36),
    CHECK (length(trim(value)) BETWEEN 1 AND 4096),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (
            length(created_at) >= 25
            AND substr(created_at, 5, 1) = '-'
            AND substr(created_at, 8, 1) = '-'
            AND substr(created_at, 11, 1) = 'T'
            AND substr(created_at, 14, 1) = ':'
            AND substr(created_at, 17, 1) = ':'
            AND substr(created_at, -6) = '+00:00'
        )
    ),
    CHECK (
        (
            length(updated_at) >= 25
            AND substr(updated_at, 5, 1) = '-'
            AND substr(updated_at, 8, 1) = '-'
            AND substr(updated_at, 11, 1) = 'T'
            AND substr(updated_at, 14, 1) = ':'
            AND substr(updated_at, 17, 1) = ':'
            AND substr(updated_at, -6) = '+00:00'
        )
    ),
    CHECK (
        archived_at IS NULL
        OR (
            length(archived_at) >= 25
            AND substr(archived_at, 5, 1) = '-'
            AND substr(archived_at, 8, 1) = '-'
            AND substr(archived_at, 11, 1) = 'T'
            AND substr(archived_at, 14, 1) = ':'
            AND substr(archived_at, 17, 1) = ':'
            AND substr(archived_at, -6) = '+00:00'
        )
    ),
    CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_targets_scope_rule_kind_value
    ON targets (scope_id, rule, kind, value);

CREATE INDEX idx_targets_scope_status_rule
    ON targets (scope_id, status, rule);

CREATE INDEX idx_targets_scope_kind
    ON targets (scope_id, kind);
