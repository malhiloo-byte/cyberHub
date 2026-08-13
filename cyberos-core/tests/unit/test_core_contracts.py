from datetime import UTC, datetime
from uuid import UUID

import pytest

from cyberos.config.redaction import redact
from cyberos.core.context import OperationContext
from cyberos.core.plugins import PluginManifest
from cyberos.core.serialization import dumps
from cyberos.core.time import ensure_utc


def test_operation_context_generates_uuid4_ids() -> None:
    context = OperationContext()
    assert isinstance(context.correlation_id, UUID)
    assert context.correlation_id.version == 4
    assert context.correlation_id != context.operation_id


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        ensure_utc(datetime(2026, 1, 1))


def test_datetime_serializes_as_utc_iso_string() -> None:
    value = ensure_utc(datetime(2026, 1, 1, 12, tzinfo=UTC))
    assert "2026-01-01T12:00:00+00:00" in dumps({"timestamp": value})


def test_redaction_hides_sensitive_keys_recursively() -> None:
    result = redact({"api_key": "secret", "nested": {"password": "hidden", "safe": "yes"}})
    assert result == {"api_key": "[REDACTED]", "nested": {"password": "[REDACTED]", "safe": "yes"}}


def test_plugin_manifest_rejects_invalid_identifier() -> None:
    with pytest.raises(ValueError):
        PluginManifest(plugin_id="Bad Plugin", name="Invalid", version="0.1.0", api_version="0.1")
