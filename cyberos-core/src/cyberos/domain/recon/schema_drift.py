"""Synthetic, deterministic schema-drift fixture contracts.

Style note: these contracts are bounded compatibility-test data. They are
ephemeral, explicitly offline, and never represent live HTTP or persisted
Evidence.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now


class SchemaDriftCaseKind(StrEnum):
    DEPRECATED_FIELD_REMOVED = "deprecated_field_removed"
    UNEXPECTED_CONTRACT_SHIFT = "unexpected_contract_shift"
    SYNTHETIC_API_VERSION_MISMATCH = "synthetic_api_version_mismatch"
    STRUCTURAL_ENVELOPE_CHANGED = "structural_envelope_changed"


class EnvelopeKind(StrEnum):
    DATA = "data"
    RESULT = "result"
    ITEMS = "items"
    ERROR = "error"


class ContractShiftKind(StrEnum):
    TYPE_CHANGED = "type_changed"
    REQUIRED_OPTIONAL = "required_optional"
    UNSUPPORTED_ENUM = "unsupported_enum"


def _bounded(value: str, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise CyberOSError(
            ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, f"Schema drift {field} is invalid."
        )
    return value.strip()


@dataclass(frozen=True, slots=True)
class MultiWebApiSchemaDriftScenario:
    scenario_id: str
    fixture_version: str
    case_kind: SchemaDriftCaseKind
    expected_schema_version: str
    presented_schema_version: str
    expected_envelope: EnvelopeKind
    presented_envelope: EnvelopeKind
    drift_marker: str
    expected_contract_version: str = "1.0"
    presented_contract_version: str = "1.0"
    target_value: str = "api.example.com"
    now: datetime | None = None
    contract_shift: ContractShiftKind | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_kind, SchemaDriftCaseKind):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Schema drift case is invalid."
            )
        if not isinstance(self.expected_envelope, EnvelopeKind) or not isinstance(
            self.presented_envelope, EnvelopeKind
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Schema drift envelope is invalid."
            )
        for field, value, maximum in (
            ("scenario_id", self.scenario_id, 100),
            ("fixture_version", self.fixture_version, 32),
            ("expected_schema_version", self.expected_schema_version, 32),
            ("presented_schema_version", self.presented_schema_version, 32),
            ("expected_contract_version", self.expected_contract_version, 32),
            ("presented_contract_version", self.presented_contract_version, 32),
            ("drift_marker", self.drift_marker, 128),
            ("target_value", self.target_value, 253),
        ):
            _bounded(value, field, maximum)
        if self.case_kind is SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT and not isinstance(
            self.contract_shift, ContractShiftKind
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Contract shift kind is required."
            )
        if (
            self.case_kind is not SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT
            and self.contract_shift is not None
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Contract shift kind is not applicable."
            )
        if self.case_kind is SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH and (
            self.expected_schema_version == self.presented_schema_version
            and self.expected_contract_version == self.presented_contract_version
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Version mismatch is not represented."
            )
        if self.case_kind is SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED and (
            self.expected_envelope is self.presented_envelope
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Envelope drift is not represented."
            )
        object.__setattr__(self, "now", ensure_utc(self.now) if self.now else utc_now())


@dataclass(frozen=True, slots=True)
class SchemaDriftReceipt:
    scenario_id: str
    fixture_version: str
    step_id: str
    case_kind: SchemaDriftCaseKind
    synthetic: bool
    offline_fixture: bool
    expected_schema_version: str
    presented_schema_version: str
    expected_contract_version: str
    presented_contract_version: str
    expected_envelope: EnvelopeKind
    presented_envelope: EnvelopeKind
    outcome_code: str
    committed_assets_before: int
    committed_observations_before: int
    committed_assets_after: int
    committed_observations_after: int

    def __post_init__(self) -> None:
        if not self.synthetic or not self.offline_fixture:
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Receipt labels are invalid."
            )
        if (
            not isinstance(self.case_kind, SchemaDriftCaseKind)
            or not isinstance(self.expected_envelope, EnvelopeKind)
            or not isinstance(self.presented_envelope, EnvelopeKind)
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Receipt vocabulary is invalid."
            )
        _bounded(self.scenario_id, "scenario_id", 100)
        _bounded(self.fixture_version, "fixture_version", 32)
        _bounded(self.step_id, "step_id", 64)
        _bounded(self.outcome_code, "outcome_code", 96)
        for field, value in (
            ("expected_schema_version", self.expected_schema_version),
            ("presented_schema_version", self.presented_schema_version),
            ("expected_contract_version", self.expected_contract_version),
            ("presented_contract_version", self.presented_contract_version),
        ):
            _bounded(value, field, 32)
        counts = (
            self.committed_assets_before,
            self.committed_observations_before,
            self.committed_assets_after,
            self.committed_observations_after,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Receipt counters are invalid."
            )
        if (
            self.committed_assets_after != self.committed_assets_before
            or self.committed_observations_after != self.committed_observations_before
        ):
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_EXPECTATION_FAILED, "Drift step changed committed state."
            )
