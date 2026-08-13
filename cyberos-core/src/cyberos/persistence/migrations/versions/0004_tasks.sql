CREATE TABLE tasks (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    command_json TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL
        CHECK (timeout_seconds BETWEEN 1 AND 3600),
    max_output_bytes INTEGER NOT NULL
        CHECK (max_output_bytes BETWEEN 1 AND 16777216),
    env_policy_json TEXT NOT NULL DEFAULT '[]',
    authorization_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    failed_at TEXT,
    cancelled_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    exit_code INTEGER,
    stdout BLOB,
    stderr BLOB,
    truncated INTEGER,
    duration_ms INTEGER,
    timeout_exceeded INTEGER,
    error_message TEXT,
    FOREIGN KEY (scope_id)
        REFERENCES scopes(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    FOREIGN KEY (target_id)
        REFERENCES targets(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(scope_id)) = 36),
    CHECK (length(trim(target_id)) = 36),
    CHECK (length(trim(command_json)) > 0 AND json_valid(command_json) = 1),
    CHECK (json_type(command_json) = 'array'),
    CHECK (length(trim(env_policy_json)) > 0 AND json_valid(env_policy_json) = 1),
    CHECK (json_type(env_policy_json) = 'array'),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        length(created_at) >= 25
        AND substr(created_at, 5, 1) = '-'
        AND substr(created_at, 8, 1) = '-'
        AND substr(created_at, 11, 1) = 'T'
        AND substr(created_at, 14, 1) = ':'
        AND substr(created_at, 17, 1) = ':'
        AND substr(created_at, -6) = '+00:00'
    ),
    CHECK (
        length(updated_at) >= 25
        AND substr(updated_at, 5, 1) = '-'
        AND substr(updated_at, 8, 1) = '-'
        AND substr(updated_at, 11, 1) = 'T'
        AND substr(updated_at, 14, 1) = ':'
        AND substr(updated_at, 17, 1) = ':'
        AND substr(updated_at, -6) = '+00:00'
    ),
    CHECK (
        authorization_expires_at IS NULL
        OR (
            length(authorization_expires_at) >= 25
            AND substr(authorization_expires_at, 5, 1) = '-'
            AND substr(authorization_expires_at, 8, 1) = '-'
            AND substr(authorization_expires_at, 11, 1) = 'T'
            AND substr(authorization_expires_at, 14, 1) = ':'
            AND substr(authorization_expires_at, 17, 1) = ':'
            AND substr(authorization_expires_at, -6) = '+00:00'
        )
    ),
    CHECK (
        started_at IS NULL
        OR (
            length(started_at) >= 25
            AND substr(started_at, 5, 1) = '-'
            AND substr(started_at, 8, 1) = '-'
            AND substr(started_at, 11, 1) = 'T'
            AND substr(started_at, 14, 1) = ':'
            AND substr(started_at, 17, 1) = ':'
            AND substr(started_at, -6) = '+00:00'
        )
    ),
    CHECK (
        completed_at IS NULL
        OR (
            length(completed_at) >= 25
            AND substr(completed_at, 5, 1) = '-'
            AND substr(completed_at, 8, 1) = '-'
            AND substr(completed_at, 11, 1) = 'T'
            AND substr(completed_at, 14, 1) = ':'
            AND substr(completed_at, 17, 1) = ':'
            AND substr(completed_at, -6) = '+00:00'
        )
    ),
    CHECK (
        failed_at IS NULL
        OR (
            length(failed_at) >= 25
            AND substr(failed_at, 5, 1) = '-'
            AND substr(failed_at, 8, 1) = '-'
            AND substr(failed_at, 11, 1) = 'T'
            AND substr(failed_at, 14, 1) = ':'
            AND substr(failed_at, 17, 1) = ':'
            AND substr(failed_at, -6) = '+00:00'
        )
    ),
    CHECK (
        cancelled_at IS NULL
        OR (
            length(cancelled_at) >= 25
            AND substr(cancelled_at, 5, 1) = '-'
            AND substr(cancelled_at, 8, 1) = '-'
            AND substr(cancelled_at, 11, 1) = 'T'
            AND substr(cancelled_at, 14, 1) = ':'
            AND substr(cancelled_at, 17, 1) = ':'
            AND substr(cancelled_at, -6) = '+00:00'
        )
    ),
    CHECK (truncated IS NULL OR truncated IN (0, 1)),
    CHECK (timeout_exceeded IS NULL OR timeout_exceeded IN (0, 1)),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (error_message IS NULL OR length(trim(error_message)) BETWEEN 1 AND 256),
    CHECK (stdout IS NULL OR length(stdout) <= max_output_bytes),
    CHECK (stderr IS NULL OR length(stderr) <= max_output_bytes),
    CHECK (
        (status = 'pending'
            AND started_at IS NULL
            AND completed_at IS NULL
            AND failed_at IS NULL
            AND cancelled_at IS NULL
            AND exit_code IS NULL
            AND stdout IS NULL
            AND stderr IS NULL
            AND truncated IS NULL
            AND duration_ms IS NULL
            AND timeout_exceeded IS NULL
            AND error_message IS NULL)
        OR
        (status = 'running'
            AND started_at IS NOT NULL
            AND completed_at IS NULL
            AND failed_at IS NULL
            AND cancelled_at IS NULL
            AND exit_code IS NULL
            AND stdout IS NULL
            AND stderr IS NULL
            AND truncated IS NULL
            AND duration_ms IS NULL
            AND timeout_exceeded IS NULL
            AND error_message IS NULL)
        OR
        (status = 'completed'
            AND started_at IS NOT NULL
            AND completed_at IS NOT NULL
            AND failed_at IS NULL
            AND cancelled_at IS NULL
            AND exit_code = 0
            AND stdout IS NOT NULL
            AND stderr IS NOT NULL
            AND truncated IS NOT NULL
            AND duration_ms IS NOT NULL
            AND timeout_exceeded = 0
            AND error_message IS NULL)
        OR
        (status = 'failed'
            AND started_at IS NOT NULL
            AND completed_at IS NULL
            AND failed_at IS NOT NULL
            AND cancelled_at IS NULL
            AND exit_code IS NOT NULL
            AND stdout IS NOT NULL
            AND stderr IS NOT NULL
            AND truncated IS NOT NULL
            AND duration_ms IS NOT NULL
            AND timeout_exceeded IS NOT NULL)
        OR
        (status = 'cancelled'
            AND cancelled_at IS NOT NULL
            AND completed_at IS NULL
            AND failed_at IS NULL)
    )
);

CREATE INDEX idx_tasks_scope_status
    ON tasks (scope_id, status);

CREATE INDEX idx_tasks_target_status
    ON tasks (target_id, status);
