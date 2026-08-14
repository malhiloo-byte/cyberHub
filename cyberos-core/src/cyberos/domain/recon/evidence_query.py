from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import EvidenceId, EvidenceKind, EvidenceRecord, EvidenceStatus
from cyberos.domain.recon.model import AssetId
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.primitives import TaskId

DEFAULT_EVIDENCE_QUERY_LIMIT = 50
MAX_EVIDENCE_QUERY_LIMIT = 200
MAX_CURSOR_BYTES = 2048


class EvidenceSort(StrEnum):
    COLLECTED_AT_DESC = "collected_at_desc"
    CREATED_AT_DESC = "created_at_desc"
    KIND_ASC = "kind_asc"
    STATUS_ASC = "status_asc"


class MetadataMode(StrEnum):
    SUMMARY = "summary"
    SAFE_METADATA = "safe_metadata"


def _validate_uuid(value: UUID | None, field: str) -> None:
    if value is not None and (not isinstance(value, UUID) or value.version != 4):
        raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, f"{field} must be UUID4.")


def _encode_cursor(value: Mapping[str, object]) -> str:
    try:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CyberOSError(
            ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence query cursor is invalid."
        ) from exc
    if len(encoded) > MAX_CURSOR_BYTES:
        raise CyberOSError(ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is too large.")
    return encoded


def _decode_cursor(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or not value or len(value) > MAX_CURSOR_BYTES:
        raise CyberOSError(ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid.")
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise CyberOSError(
            ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
        ) from exc
    if not isinstance(decoded, dict):
        raise CyberOSError(ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid.")
    return decoded


@dataclass(frozen=True, slots=True)
class EvidenceCursor:
    version: int
    fingerprint: str
    sort: EvidenceSort
    position: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version != 1 or len(self.fingerprint) != 64:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )
        if any(character not in "0123456789abcdef" for character in self.fingerprint):
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )
        if not isinstance(self.sort, EvidenceSort) or not self.position:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )
        if any(not isinstance(value, str) or len(value) > 256 for value in self.position):
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )

    def encode(self) -> str:
        return _encode_cursor(
            {
                "v": self.version,
                "f": self.fingerprint,
                "s": self.sort.value,
                "p": self.position,
            }
        )

    @classmethod
    def decode(cls, value: str) -> EvidenceCursor:
        payload = _decode_cursor(value)
        try:
            version = payload["v"]
            fingerprint = payload["f"]
            sort = EvidenceSort(payload["s"])
            position = payload["p"]
            if not isinstance(version, int) or isinstance(version, bool):
                raise ValueError("version")
            if not isinstance(fingerprint, str) or not isinstance(position, list):
                raise ValueError("cursor fields")
            return cls(version, fingerprint, sort, tuple(position))
        except (KeyError, TypeError, ValueError) as exc:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            ) from exc


@dataclass(frozen=True, slots=True)
class EvidenceQuery:
    scope_id: ScopeId | None = None
    target_id: TargetId | None = None
    task_id: TaskId | None = None
    asset_id: AssetId | None = None
    kind: EvidenceKind | None = None
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    sort: EvidenceSort = EvidenceSort.COLLECTED_AT_DESC
    limit: int = DEFAULT_EVIDENCE_QUERY_LIMIT
    cursor: EvidenceCursor | None = None
    metadata_mode: MetadataMode = MetadataMode.SUMMARY

    def __post_init__(self) -> None:
        _validate_uuid(self.scope_id, "scope_id")
        _validate_uuid(self.target_id, "target_id")
        _validate_uuid(self.task_id, "task_id")
        _validate_uuid(self.asset_id, "asset_id")
        if not any(
            value is not None
            for value in (self.scope_id, self.target_id, self.task_id, self.asset_id)
        ):
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_UNBOUNDED,
                "Evidence query requires a scope, target, task, or asset context.",
            )
        if not isinstance(self.kind, (EvidenceKind, type(None))):
            raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence kind is invalid.")
        if not isinstance(self.status, EvidenceStatus):
            raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence status is invalid.")
        if not isinstance(self.sort, EvidenceSort):
            raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence sort is invalid.")
        if not isinstance(self.metadata_mode, MetadataMode):
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence metadata mode is invalid."
            )
        if self.cursor is not None and not isinstance(self.cursor, EvidenceCursor):
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit < 1:
            raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence query limit is invalid.")
        if self.limit > MAX_EVIDENCE_QUERY_LIMIT:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_LIMIT_EXCEEDED,
                f"Evidence query limit cannot exceed {MAX_EVIDENCE_QUERY_LIMIT}.",
            )

    def fingerprint(self) -> str:
        payload = {
            "scope": str(self.scope_id) if self.scope_id is not None else None,
            "target": str(self.target_id) if self.target_id is not None else None,
            "task": str(self.task_id) if self.task_id is not None else None,
            "asset": str(self.asset_id) if self.asset_id is not None else None,
            "kind": self.kind.value if self.kind is not None else None,
            "status": self.status.value,
            "sort": self.sort.value,
            "metadata": self.metadata_mode.value,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceReadModel:
    id: EvidenceId
    scope_id: ScopeId
    target_id: TargetId
    task_id: TaskId
    asset_id: AssetId
    observation_id: UUID | None
    kind: EvidenceKind
    title: str
    content_digest: str
    content_size_bytes: int
    source_plugin_id: str
    source_plugin_version: str
    pipeline_id: str | None
    pipeline_version: str | None
    collected_at: datetime
    status: EvidenceStatus
    version: int
    metadata: Mapping[str, str | int | float | bool | None] | None

    @classmethod
    def from_record(cls, record: EvidenceRecord, mode: MetadataMode) -> EvidenceReadModel:
        metadata = (
            MappingProxyType(dict(record.metadata)) if mode is MetadataMode.SAFE_METADATA else None
        )
        return cls(
            id=record.id,
            scope_id=record.scope_id,
            target_id=record.target_id,
            task_id=TaskId(record.task_id),
            asset_id=AssetId(record.asset_id),
            observation_id=record.observation_id,
            kind=record.kind,
            title=record.title,
            content_digest=record.content_digest,
            content_size_bytes=record.content_size_bytes,
            source_plugin_id=record.source_plugin_id,
            source_plugin_version=record.source_plugin_version,
            pipeline_id=record.pipeline_id,
            pipeline_version=record.pipeline_version,
            collected_at=record.collected_at,
            status=record.status,
            version=record.version,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class EvidenceQueryPage:
    items: tuple[EvidenceReadModel, ...]
    next_cursor: EvidenceCursor | None
    has_more: bool
    returned: int

    def __post_init__(self) -> None:
        if self.returned != len(self.items) or self.returned > MAX_EVIDENCE_QUERY_LIMIT:
            raise CyberOSError(ErrorCode.EVIDENCE_QUERY_INVALID, "Evidence query page is invalid.")


@dataclass(frozen=True, slots=True)
class EvidenceRecordPage:
    records: tuple[EvidenceRecord, ...]
    next_cursor: EvidenceCursor | None
    has_more: bool


class EvidenceQueryPort(Protocol):
    def query(self, query: EvidenceQuery) -> EvidenceRecordPage: ...
