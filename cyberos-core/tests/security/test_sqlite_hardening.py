import sqlite3
from pathlib import Path

from cyberos.config.models import DatabaseSettings
from cyberos.persistence.connection import SQLiteConnectionFactory


def test_connection_does_not_use_network_or_subprocess(tmp_path: Path) -> None:
    with SQLiteConnectionFactory(
        DatabaseSettings(path=tmp_path / "cyberos.sqlite3")
    ).connect() as managed:
        assert isinstance(managed.raw, sqlite3.Connection)
        assert managed.pragma_state.foreign_keys is True
