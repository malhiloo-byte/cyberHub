from pathlib import Path

import pytest

from cyberos.config.loader import load_config
from cyberos.core.errors import CyberOSError, ErrorCode


def test_defaults_are_safe_and_local() -> None:
    config = load_config(environ={})
    assert config.app.name == "cyberos"
    assert config.runtime.data_dir == Path("~/.cyberos").expanduser()


def test_environment_overrides_are_applied() -> None:
    config = load_config(environ={"CYBEROS_LOG_LEVEL": "DEBUG", "CYBEROS_COLOR": "false"})
    assert config.runtime.log_level == "DEBUG"
    assert config.cli.color is False


def test_invalid_toml_is_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text("[runtime\n", encoding="utf-8")
    with pytest.raises(CyberOSError) as captured:
        load_config(path, environ={})
    assert captured.value.code == ErrorCode.CONFIG_INVALID


def test_missing_toml_is_typed_error(tmp_path: Path) -> None:
    with pytest.raises(CyberOSError) as captured:
        load_config(tmp_path / "missing.toml", environ={})
    assert captured.value.code == ErrorCode.CONFIG_NOT_FOUND
