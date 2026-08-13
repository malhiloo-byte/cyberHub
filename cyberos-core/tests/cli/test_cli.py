from pathlib import Path

from typer.testing import CliRunner

from cyberos.cli.app import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "cyberos-core" in result.stdout
    assert "0.1.0" in result.stdout


def test_doctor_json_failure_is_machine_readable(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f'[runtime]\ndata_dir = "{tmp_path / "missing"}"\nlog_dir = "{tmp_path}"\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["doctor", "--json", "--file", str(config)])
    assert result.exit_code == 3
    assert '"ok": false' in result.stdout


def test_config_validate_command(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[app]\nenvironment = "test"\n', encoding="utf-8")
    result = runner.invoke(app, ["config", "validate", "--file", str(config)])
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()
