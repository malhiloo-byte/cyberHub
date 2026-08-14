from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID, uuid4

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.recon.contracts import ReconResult

AssetId = NewType("AssetId", UUID)
AssetObservationId = NewType("AssetObservationId", UUID)


class AssetKind(StrEnum):
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP_ADDRESS = "ip_address"
    HOST = "host"
    URL = "url"
    SERVICE = "service"


class AssetStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, f"{field} must be UTC-aware.")
    normalized = value.astimezone(UTC)
    return normalized


def _uuid4(value: UUID, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, f"{field} must be UUID4.")


def new_asset_id() -> AssetId:
    return AssetId(uuid4())


def new_observation_id() -> AssetObservationId:
    return AssetObservationId(uuid4())


@dataclass(frozen=True, slots=True)
class DiscoveredSubdomain:
    fqdn: str
    parent_domain: str

    def __post_init__(self) -> None:
        if not self.fqdn or not self.parent_domain:
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "Subdomain values cannot be empty.")


@dataclass(frozen=True, slots=True)
class DiscoveredService:
    transport: str
    port: int
    service_name: str | None = None
    product: str | None = None
    service_version: str | None = None

    def __post_init__(self) -> None:
        if self.transport not in {"tcp", "udp"} or not 1 <= self.port <= 65535:
            raise CyberOSError(
                ErrorCode.RECON_RECORD_INVALID, "Service transport or port is invalid."
            )


@dataclass(frozen=True, slots=True)
class DiscoveredHttpEndpoint:
    scheme: str
    port: int
    path: str
    query_fingerprint: str | None = None
    status_code: int | None = None
    title: str | None = None
    technologies_json: str = "[]"

    def __post_init__(self) -> None:
        if self.scheme not in {"http", "https"} or not 1 <= self.port <= 65535:
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "HTTP scheme or port is invalid.")
        if not self.path.startswith("/"):
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "HTTP path must start with '/'.")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "HTTP status code is invalid.")


ReconRecord = DiscoveredSubdomain | DiscoveredService | DiscoveredHttpEndpoint | None


@dataclass(frozen=True, slots=True)
class AssetObservation:
    id: AssetObservationId
    asset_id: AssetId
    scope_id: ScopeId
    target_id: TargetId
    task_id: UUID
    plugin_id: str
    plugin_version: str
    contract_version: str
    result_digest: str
    observed_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid4(self.id, "observation_id")
        _uuid4(self.asset_id, "asset_id")
        _uuid4(self.scope_id, "scope_id")
        _uuid4(self.target_id, "target_id")
        _uuid4(self.task_id, "task_id")
        for field in ("plugin_id", "plugin_version", "contract_version", "result_digest"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, f"{field} cannot be empty.")
        if len(self.result_digest) != 64:
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "result_digest must be SHA-256 hex.")
        _utc(self.observed_at, "observed_at")
        _utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class AssetAggregate:
    id: AssetId
    scope_id: ScopeId
    target_id: TargetId
    asset_kind: AssetKind
    canonical_value: str
    display_value: str
    status: AssetStatus
    first_seen_at: datetime
    last_seen_at: datetime
    first_seen_task_id: UUID
    last_seen_task_id: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int
    record: ReconRecord = None

    def __post_init__(self) -> None:
        _uuid4(self.id, "asset_id")
        _uuid4(self.scope_id, "scope_id")
        _uuid4(self.target_id, "target_id")
        _uuid4(self.first_seen_task_id, "first_seen_task_id")
        _uuid4(self.last_seen_task_id, "last_seen_task_id")
        if not self.canonical_value or not self.display_value:
            raise CyberOSError(ErrorCode.RECON_RECORD_INVALID, "Asset values cannot be empty.")
        if not isinstance(self.status, AssetStatus) or self.version < 1:
            raise CyberOSError(
                ErrorCode.RECON_RECORD_INVALID, "Asset status or version is invalid."
            )
        first = _utc(self.first_seen_at, "first_seen_at")
        last = _utc(self.last_seen_at, "last_seen_at")
        if last < first:
            raise CyberOSError(
                ErrorCode.RECON_RECORD_INVALID, "last_seen_at cannot precede first_seen_at."
            )
        if self.status is AssetStatus.ACTIVE and self.archived_at is not None:
            raise CyberOSError(
                ErrorCode.RECON_RECORD_INVALID, "Active asset cannot have archived_at."
            )


@dataclass(frozen=True, slots=True)
class ReconIngestion:
    task_id: UUID
    scope_id: ScopeId
    target_id: TargetId
    plugin_id: str
    plugin_version: str
    contract_version: str
    result: ReconResult
    asset: AssetAggregate
    observation: AssetObservation

    def __post_init__(self) -> None:
        _uuid4(self.task_id, "task_id")
        if (
            self.result.task_id != self.task_id
            or self.result.scope_id != self.scope_id
            or self.result.target_id != self.target_id
        ):
            raise CyberOSError(
                ErrorCode.RECON_RESULT_INVALID, "Recon result identity does not match ingestion."
            )
        if self.asset.scope_id != self.scope_id or self.asset.target_id != self.target_id:
            raise CyberOSError(
                ErrorCode.RECON_RESULT_INVALID, "Asset boundary does not match ingestion."
            )
        if self.observation.task_id != self.task_id or self.observation.asset_id != self.asset.id:
            raise CyberOSError(
                ErrorCode.RECON_RESULT_INVALID, "Observation boundary does not match ingestion."
            )


@dataclass(frozen=True, slots=True)
class ReconIngestionReceipt:
    task_id: UUID
    inserted_assets: int
    inserted_observations: int
    updated_assets: int
