from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import (
    EvidenceId,
    EvidenceKind,
    EvidenceRecord,
    EvidenceStatus,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId


def _timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED, f"Invalid Evidence {field}."
        ) from exc


def evidence_to_params(record: EvidenceRecord) -> tuple[object, ...]:
    metadata_json = json.dumps(
        dict(record.metadata), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return (
        str(record.id),
        str(record.scope_id),
        str(record.target_id),
        str(record.task_id),
        str(record.asset_id),
        str(record.observation_id) if record.observation_id is not None else None,
        record.kind.value,
        record.title,
        record.content_digest,
        record.content_size_bytes,
        metadata_json,
        record.source_plugin_id,
        record.source_plugin_version,
        record.pipeline_id,
        record.pipeline_version,
        record.collected_at.isoformat(),
        record.status.value,
        record.version,
        record.created_at.isoformat(),
        record.updated_at.isoformat(),
        record.archived_at.isoformat() if record.archived_at is not None else None,
    )


def evidence_from_row(row: sqlite3.Row) -> EvidenceRecord:
    try:
        metadata = json.loads(row["metadata_json"])
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        return EvidenceRecord(
            id=EvidenceId(UUID(row["id"])),
            scope_id=ScopeId(UUID(row["scope_id"])),
            target_id=TargetId(UUID(row["target_id"])),
            task_id=UUID(row["task_id"]),
            asset_id=UUID(row["asset_id"]),
            observation_id=UUID(row["observation_id"]) if row["observation_id"] else None,
            kind=EvidenceKind(row["kind"]),
            title=row["title"],
            content_digest=row["content_digest"],
            content_size_bytes=int(row["content_size_bytes"]),
            metadata=metadata,
            source_plugin_id=row["source_plugin_id"],
            source_plugin_version=row["source_plugin_version"],
            pipeline_id=row["pipeline_id"],
            pipeline_version=row["pipeline_version"],
            collected_at=_timestamp(row["collected_at"], "collected_at"),
            status=EvidenceStatus(row["status"]),
            version=int(row["version"]),
            created_at=_timestamp(row["created_at"], "created_at"),
            updated_at=_timestamp(row["updated_at"], "updated_at"),
            archived_at=_timestamp(row["archived_at"], "archived_at")
            if row["archived_at"]
            else None,
        )
    except CyberOSError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "Stored Evidence could not be mapped safely.",
        ) from exc
