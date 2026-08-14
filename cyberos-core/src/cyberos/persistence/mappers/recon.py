from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.model import AssetAggregate, AssetId, AssetKind, AssetStatus
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId


def _dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED, "Recon timestamp is invalid."
        ) from exc


def asset_to_params(asset: AssetAggregate) -> tuple[object, ...]:
    return (
        str(asset.id),
        str(asset.scope_id),
        str(asset.target_id),
        asset.asset_kind.value,
        asset.canonical_value,
        asset.display_value,
        asset.status.value,
        asset.first_seen_at.isoformat(),
        asset.last_seen_at.isoformat(),
        str(asset.first_seen_task_id),
        str(asset.last_seen_task_id),
        asset.created_at.isoformat(),
        asset.updated_at.isoformat(),
        asset.archived_at.isoformat() if asset.archived_at else None,
        asset.version,
    )


def asset_from_row(row: Any) -> AssetAggregate:
    try:
        return AssetAggregate(
            id=AssetId(UUID(row["id"])),
            scope_id=ScopeId(UUID(row["scope_id"])),
            target_id=TargetId(UUID(row["target_id"])),
            asset_kind=AssetKind(row["asset_kind"]),
            canonical_value=row["canonical_value"],
            display_value=row["display_value"],
            status=AssetStatus(row["status"]),
            first_seen_at=_dt(row["first_seen_at"]),
            last_seen_at=_dt(row["last_seen_at"]),
            first_seen_task_id=UUID(row["first_seen_task_id"]),
            last_seen_task_id=UUID(row["last_seen_task_id"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
            archived_at=_dt(row["archived_at"]) if row["archived_at"] else None,
            version=int(row["version"]),
        )
    except CyberOSError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED, "Recon asset row is invalid."
        ) from exc


def technologies_json(value: str) -> tuple[str, ...]:
    try:
        raw = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED, "Technology JSON is invalid."
        ) from exc
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED, "Technology JSON must be a string array."
        )
    return tuple(raw)
