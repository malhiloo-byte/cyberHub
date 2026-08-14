from __future__ import annotations

from typing import Protocol

from cyberos.domain.recon.evidence import EvidenceId, EvidenceRecord
from cyberos.domain.recon.model import AssetId
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.task.primitives import TaskId


class ReconEvidenceRepositoryPort(Protocol):
    def add(self, record: EvidenceRecord) -> EvidenceRecord: ...

    def get(self, evidence_id: EvidenceId) -> EvidenceRecord | None: ...

    def list_by_task(
        self, task_id: TaskId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]: ...

    def list_by_asset(
        self, asset_id: AssetId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]: ...

    def list_by_scope(
        self, scope_id: ScopeId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]: ...

    def archive(self, evidence_id: EvidenceId, *, expected_version: int) -> EvidenceRecord: ...
