from pathlib import Path

from cyberos.application.doctor import run_doctor
from cyberos.config.models import CyberOSConfig, RuntimeSettings


def test_doctor_passes_with_writable_directories(tmp_path: Path) -> None:
    config = CyberOSConfig(runtime=RuntimeSettings(data_dir=tmp_path, log_dir=tmp_path))
    result = run_doctor(config)
    assert result["ok"] is True
    assert result["failures"] == []


def test_doctor_reports_missing_directory(tmp_path: Path) -> None:
    config = CyberOSConfig(runtime=RuntimeSettings(data_dir=tmp_path / "missing", log_dir=tmp_path))
    result = run_doctor(config)
    assert result["ok"] is False
    assert result["failures"]
