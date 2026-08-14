from typing import Protocol

from cyberos.domain.recon.model import (
    AssetAggregate,
    AssetId,
    AssetKind,
    AssetObservation,
    ReconIngestion,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId


class ReconRepositoryPort(Protocol):
    def ingest(self, ingestion: ReconIngestion) -> AssetAggregate: ...

    def find_asset(
        self,
        scope_id: ScopeId,
        target_id: TargetId,
        asset_kind: AssetKind,
        canonical_value: str,
    ) -> AssetAggregate | None: ...

    def get_asset(self, asset_id: AssetId) -> AssetAggregate | None: ...

    def list_assets(
        self, scope_id: ScopeId, target_id: TargetId | None = None
    ) -> tuple[AssetAggregate, ...]: ...

    def list_observations(self, asset_id: AssetId) -> tuple[AssetObservation, ...]: ...

    def archive_asset(self, asset_id: AssetId, *, expected_version: int) -> AssetAggregate: ...
