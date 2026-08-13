import os
import stat
from pathlib import Path

import pytest

from cyberos.config.loader import load_config
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.path_policy import prepare_database_path


def test_database_defaults_match_hardened_policy() -> None:
    config = load_config(environ={})
    assert config.database.path == Path("~/.cyberos/cyberos.sqlite3").expanduser()
    assert config.database.timeout_seconds == 5.0
    assert config.database.journal_mode == "wal"
    assert config.database.synchronous == "full"
    assert config.database.foreign_keys is True
    assert config.database.secure_delete is True
    assert config.database.create_parent is True


def test_database_environment_overrides_are_typed(tmp_path: Path) -> None:
    config = load_config(
        environ={
            "CYBEROS_DATABASE_PATH": str(tmp_path / "cyberos.sqlite3"),
            "CYBEROS_DATABASE_TIMEOUT_SECONDS": "7.5",
            "CYBEROS_DATABASE_FOREIGN_KEYS": "false",
        }
    )
    assert config.database.path == tmp_path / "cyberos.sqlite3"
    assert config.database.timeout_seconds == 7.5
    assert config.database.foreign_keys is False


def test_invalid_database_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="journal_mode"):
        DatabaseSettings(journal_mode="delete")
    with pytest.raises(ValueError, match="timeout_seconds"):
        DatabaseSettings(timeout_seconds=0)


def test_new_database_file_is_created_with_private_mode(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cyberos.sqlite3"
    prepared = prepare_database_path(DatabaseSettings(path=path))
    assert prepared.created is True
    assert path.is_file()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_existing_broad_file_permissions_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cyberos.sqlite3"
    path.touch()
    if os.name == "posix":
        path.chmod(0o644)
        with pytest.raises(CyberOSError) as captured:
            prepare_database_path(DatabaseSettings(path=path))
        assert captured.value.code == ErrorCode.DATABASE_PERMISSION_POLICY_FAILED


def test_directory_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CyberOSError) as captured:
        prepare_database_path(DatabaseSettings(path=tmp_path))
    assert captured.value.code == ErrorCode.DATABASE_PATH_INVALID


def test_symlink_database_path_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "cyberos.sqlite3"
    link.symlink_to(target)
    with pytest.raises(CyberOSError) as captured:
        prepare_database_path(DatabaseSettings(path=link))
    assert captured.value.code == ErrorCode.DATABASE_SYMLINK_UNSAFE


def test_missing_parent_is_rejected_when_creation_disabled(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "cyberos.sqlite3"
    with pytest.raises(CyberOSError) as captured:
        prepare_database_path(DatabaseSettings(path=path, create_parent=False))
    assert captured.value.code == ErrorCode.DATABASE_PARENT_NOT_WRITABLE
