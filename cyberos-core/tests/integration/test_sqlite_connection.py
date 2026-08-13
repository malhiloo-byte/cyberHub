from pathlib import Path
from typing import Any, cast

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.health import run_quick_check


def make_settings(tmp_path: Path) -> DatabaseSettings:
    return DatabaseSettings(path=tmp_path / "cyberos.sqlite3")


def test_connection_factory_applies_required_pragmas(tmp_path: Path) -> None:
    factory = SQLiteConnectionFactory(make_settings(tmp_path))
    with factory.connect() as managed:
        assert managed.pragma_state.foreign_keys is True
        assert managed.pragma_state.journal_mode == "wal"
        assert managed.pragma_state.synchronous == "full"
        assert managed.pragma_state.busy_timeout_ms == 5000
        assert managed.pragma_state.secure_delete is True
        assert managed.raw.execute("SELECT 1").fetchone()[0] == 1


def test_connection_lifecycle_closes_and_is_idempotent(tmp_path: Path) -> None:
    managed = SQLiteConnectionFactory(make_settings(tmp_path)).open()
    managed.close()
    managed.close()
    with pytest.raises(CyberOSError) as captured:
        managed.quick_check()
    assert captured.value.code == ErrorCode.DATABASE_CONNECTION_CLOSED


def test_context_manager_closes_on_exception(tmp_path: Path) -> None:
    managed = SQLiteConnectionFactory(make_settings(tmp_path)).open()
    with pytest.raises(RuntimeError):
        with managed:
            raise RuntimeError("test failure")
    with pytest.raises(CyberOSError) as captured:
        _ = managed.raw
    assert captured.value.code == ErrorCode.DATABASE_CONNECTION_CLOSED


def test_quick_check_reports_healthy_database(tmp_path: Path) -> None:
    with SQLiteConnectionFactory(make_settings(tmp_path)).connect() as managed:
        result = managed.quick_check()
        assert result.healthy is True
        assert result.check == "quick_check"
        assert result.details["result"] == "ok"


def test_quick_check_reports_unhealthy_result_without_repair() -> None:
    class FakeResult:
        def fetchone(self) -> tuple[str]:
            return ("not an ok result",)

    class FakeConnection:
        def execute(self, statement: str) -> FakeResult:
            assert statement == "PRAGMA quick_check"
            return FakeResult()

    result = run_quick_check(cast(Any, FakeConnection()))
    assert result.healthy is False
    assert result.details["result"] == "not an ok result"


def test_factory_rejects_unsupported_policy_before_connection(tmp_path: Path) -> None:
    settings = DatabaseSettings(path=tmp_path / "cyberos.sqlite3")
    object.__setattr__(settings, "journal_mode", "delete")
    with pytest.raises(CyberOSError):
        SQLiteConnectionFactory(settings).open()


def test_database_open_failure_is_typed(tmp_path: Path) -> None:
    directory = tmp_path / "database.sqlite3"
    directory.mkdir()
    with pytest.raises(CyberOSError) as captured:
        SQLiteConnectionFactory(DatabaseSettings(path=directory)).open()
    assert captured.value.code == ErrorCode.DATABASE_PATH_INVALID
