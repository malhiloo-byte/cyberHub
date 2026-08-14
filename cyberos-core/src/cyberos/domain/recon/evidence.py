from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import NewType, TypeAlias
from uuid import UUID, uuid4

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.recon.model import AssetAggregate, AssetObservation
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetRule
from cyberos.domain.task.model import ExecutionAuthorizationContract, Task

EvidenceId = NewType("EvidenceId", UUID)
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONMetadata: TypeAlias = Mapping[str, JSONPrimitive]


class EvidenceKind(StrEnum):
    OBSERVATION_SUMMARY = "observation_summary"
    SERVICE_METADATA = "service_metadata"
    HTTP_METADATA = "http_metadata"
    QUERY_DIGEST = "query_digest"


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def new_evidence_id() -> EvidenceId:
    return EvidenceId(uuid4())


def _uuid4(value: UUID, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(ErrorCode.RECON_EVIDENCE_INVALID, f"{field} must be UUID4.")


def _validate_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CyberOSError(ErrorCode.RECON_EVIDENCE_INVALID, f"{field} is invalid.")
    if any(ord(character) < 32 for character in value):
        raise CyberOSError(
            ErrorCode.RECON_EVIDENCE_INVALID, f"{field} contains control characters."
        )
    return value


def _canonical_metadata(metadata: Mapping[str, JSONPrimitive]) -> tuple[str, JSONMetadata]:
    if not isinstance(metadata, Mapping) or len(metadata) > 128:
        raise CyberOSError(ErrorCode.RECON_EVIDENCE_INVALID, "Evidence metadata is invalid.")
    normalized: dict[str, JSONPrimitive] = {}
    for key, value in metadata.items():
        _validate_text(key, "metadata key", 80)
        lowered = key.casefold()
        if any(
            marker in lowered
            for marker in ("password", "secret", "token", "credential", "cookie", "raw_query")
        ):
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID,
                "Evidence metadata contains a restricted field.",
            )
        if value is not None and type(value) not in {str, int, float, bool}:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "Evidence metadata value is invalid."
            )
        if isinstance(value, str):
            _validate_text(value, "metadata value", 4096)
        normalized[key] = value
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.RECON_EVIDENCE_INVALID, "Evidence metadata is not JSON-safe."
        ) from exc
    if len(encoded.encode("utf-8")) > 65536:
        raise CyberOSError(
            ErrorCode.RECON_EVIDENCE_INVALID, "Evidence metadata exceeds the size limit."
        )
    return encoded, MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: EvidenceId
    scope_id: ScopeId
    target_id: TargetId
    task_id: UUID
    asset_id: UUID
    observation_id: UUID | None
    kind: EvidenceKind
    title: str
    content_digest: str
    content_size_bytes: int
    metadata: JSONMetadata
    source_plugin_id: str
    source_plugin_version: str
    pipeline_id: str | None
    pipeline_version: str | None
    collected_at: datetime
    status: EvidenceStatus
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        for identifier, field in (
            (self.id, "evidence_id"),
            (self.scope_id, "scope_id"),
            (self.target_id, "target_id"),
            (self.task_id, "task_id"),
            (self.asset_id, "asset_id"),
        ):
            _uuid4(identifier, field)
        if self.observation_id is not None:
            _uuid4(self.observation_id, "observation_id")
        if not isinstance(self.kind, EvidenceKind) or not isinstance(self.status, EvidenceStatus):
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "Evidence kind or status is invalid."
            )
        _validate_text(self.title, "title", 200)
        encoded, normalized = _canonical_metadata(self.metadata)
        expected_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if self.content_digest != expected_digest or len(self.content_digest) != 64:
            raise CyberOSError(ErrorCode.RECON_EVIDENCE_INVALID, "Evidence digest is invalid.")
        if self.content_size_bytes != len(encoded.encode("utf-8")):
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "Evidence content size is invalid."
            )
        _validate_text(self.source_plugin_id, "source_plugin_id", 80)
        _validate_text(self.source_plugin_version, "source_plugin_version", 64)
        if self.pipeline_id is not None:
            _validate_text(self.pipeline_id, "pipeline_id", 200)
        if self.pipeline_version is not None:
            _validate_text(self.pipeline_version, "pipeline_version", 64)
        for value, _field in (
            (self.collected_at, "collected_at"),
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            ensure_utc(value)
        if self.archived_at is not None:
            ensure_utc(self.archived_at)
        if self.version < 1:
            raise CyberOSError(ErrorCode.RECON_EVIDENCE_INVALID, "Evidence version is invalid.")
        if self.status is EvidenceStatus.ACTIVE and self.archived_at is not None:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "Active evidence cannot be archived."
            )
        if self.status is EvidenceStatus.ARCHIVED and self.archived_at is None:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "Archived evidence requires archived_at."
            )
        if self.updated_at < self.created_at:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_INVALID, "updated_at cannot precede created_at."
            )
        object.__setattr__(self, "metadata", normalized)


class EvidenceFactory:
    """Creates evidence only from committed, authorization-bound Recon provenance."""

    @staticmethod
    def from_observation(
        task: Task,
        authorization: ExecutionAuthorizationContract,
        asset: AssetAggregate,
        observation: AssetObservation,
        *,
        kind: EvidenceKind,
        title: str,
        metadata: JSONMetadata,
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        collected_at: datetime | None = None,
        evidence_id: EvidenceId | None = None,
    ) -> EvidenceRecord:
        timestamp = ensure_utc(collected_at) if collected_at is not None else utc_now()
        if (
            task.scope_id != authorization.scope_id
            or task.target_id != authorization.matched_target_id
        ):
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence authorization does not match the Task context.",
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence requires an Include authorization.",
            )
        if authorization.expires_at is not None and authorization.expires_at <= timestamp:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence authorization has expired.",
            )
        if (
            asset.scope_id != task.scope_id
            or asset.target_id != task.target_id
            or observation.scope_id != task.scope_id
            or observation.target_id != task.target_id
            or observation.task_id != task.id
            or observation.asset_id != asset.id
        ):
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence provenance does not match the Task, Scope, and Target.",
            )
        encoded, _ = _canonical_metadata(metadata)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return EvidenceRecord(
            id=evidence_id or new_evidence_id(),
            scope_id=task.scope_id,
            target_id=task.target_id,
            task_id=task.id,
            asset_id=asset.id,
            observation_id=observation.id,
            kind=kind,
            title=title,
            content_digest=digest,
            content_size_bytes=len(encoded.encode("utf-8")),
            metadata=metadata,
            source_plugin_id=observation.plugin_id,
            source_plugin_version=observation.plugin_version,
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            collected_at=timestamp,
            status=EvidenceStatus.ACTIVE,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
