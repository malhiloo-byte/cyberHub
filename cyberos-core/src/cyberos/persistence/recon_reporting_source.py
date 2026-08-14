from __future__ import annotations

import sqlite3

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.reporting import ReconAssetReadBundle, ReconReportSourcePort
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


class SQLiteReconReportSource(ReconReportSourcePort):
    """Read-only reporting source composed from the existing Recon repository port."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def read_assets(
        self, scope_id: ScopeId, target_id: TargetId | None = None
    ) -> tuple[ReconAssetReadBundle, ...]:
        try:
            with SQLiteUnitOfWork(self.factory) as unit:
                repository = SQLiteReconRepository(unit)
                assets = repository.list_assets(scope_id, target_id)
                bundles = tuple(
                    ReconAssetReadBundle(
                        asset=asset,
                        observations=repository.list_observations(asset.id),
                    )
                    for asset in assets
                )
                unit.rollback()
                return bundles
        except CyberOSError:
            raise
        except sqlite3.Error as exc:
            raise CyberOSError(
                ErrorCode.REPORT_DATA_INCONSISTENT,
                "Reporting source could not be read safely.",
            ) from exc
