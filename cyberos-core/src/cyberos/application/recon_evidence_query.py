from __future__ import annotations

from cyberos.domain.recon.evidence_query import (
    EvidenceQuery,
    EvidenceQueryPage,
    EvidenceReadModel,
)
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.evidence_query_repository import SQLiteEvidenceQueryRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


class EvidenceQueryService:
    """Read-only application boundary for bounded, typed Evidence projections."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def query(self, query: EvidenceQuery) -> EvidenceQueryPage:
        with SQLiteUnitOfWork(self.factory) as unit:
            page = SQLiteEvidenceQueryRepository(unit).query(query)
            unit.rollback()
        return EvidenceQueryPage(
            items=tuple(
                EvidenceReadModel.from_record(record, query.metadata_mode)
                for record in page.records
            ),
            next_cursor=page.next_cursor,
            has_more=page.has_more,
            returned=len(page.records),
        )
