from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cyberos.cli.app import app

runner = CliRunner()


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[database]\n"
        f'path = "{tmp_path / "cyberos.sqlite3"}"\n'
        "[runtime]\n"
        f'data_dir = "{tmp_path}"\n'
        f'log_dir = "{tmp_path}"\n',
        encoding="utf-8",
    )
    return path


def invoke(tmp_path: Path, args: list[str]):
    return runner.invoke(app, [*args, "--file", str(config_file(tmp_path))])


def test_workspace_cli_create_list_show_archive_json(tmp_path: Path) -> None:
    created = invoke(tmp_path, ["workspace", "create", "CLI Workspace", "--json"])
    assert created.exit_code == 0
    created_payload = json.loads(created.stdout)
    assert created_payload["ok"] is True
    assert created_payload["meta"]["correlation_id"]
    workspace_id = created_payload["data"]["id"]

    listed = invoke(tmp_path, ["workspace", "list", "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["data"][0]["id"] == workspace_id

    shown = invoke(tmp_path, ["workspace", "show", workspace_id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["data"]["name"] == "CLI Workspace"

    archived = invoke(
        tmp_path, ["workspace", "archive", workspace_id, "--expected-version", "1", "--json"]
    )
    assert archived.exit_code == 0
    assert json.loads(archived.stdout)["data"]["status"] == "archived"


def test_workspace_cli_human_output_is_readable(tmp_path: Path) -> None:
    result = invoke(tmp_path, ["workspace", "create", "Human Workspace"])
    assert result.exit_code == 0
    assert "Human Workspace" in result.stdout
    assert "correlation_id:" in result.stdout


def test_engagement_cli_create_list_show_transition_archive_json(tmp_path: Path) -> None:
    workspace = invoke(tmp_path, ["workspace", "create", "CLI Workspace", "--json"])
    workspace_id = json.loads(workspace.stdout)["data"]["id"]
    created = invoke(
        tmp_path,
        [
            "engagement",
            "create",
            workspace_id,
            "CLI Engagement",
            "--kind",
            "learning",
            "--json",
        ],
    )
    assert created.exit_code == 0
    engagement_payload = json.loads(created.stdout)
    engagement_id = engagement_payload["data"]["id"]
    listed = invoke(tmp_path, ["engagement", "list", workspace_id, "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["data"][0]["id"] == engagement_id
    shown = invoke(tmp_path, ["engagement", "show", engagement_id, "--json"])
    assert shown.exit_code == 0
    active = invoke(
        tmp_path,
        ["engagement", "transition", engagement_id, "active", "--expected-version", "1", "--json"],
    )
    assert active.exit_code == 0
    assert json.loads(active.stdout)["data"]["version"] == 2
    archived = invoke(
        tmp_path,
        ["engagement", "archive", engagement_id, "--expected-version", "2", "--json"],
    )
    assert archived.exit_code == 0
    assert json.loads(archived.stdout)["data"]["status"] == "archived"


def test_cli_errors_have_envelope_exit_code_and_no_sql_leak(tmp_path: Path) -> None:
    missing = invoke(tmp_path, ["workspace", "show", "not-a-uuid", "--json"])
    assert missing.exit_code == 4
    payload = json.loads(missing.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"
    assert "sqlite" not in missing.stdout.lower()
    assert "traceback" not in missing.stdout.lower()


def test_cli_version_conflict_is_deterministic_error(tmp_path: Path) -> None:
    created = invoke(tmp_path, ["workspace", "create", "Concurrent", "--json"])
    workspace_id = json.loads(created.stdout)["data"]["id"]
    conflict = invoke(
        tmp_path,
        ["workspace", "archive", workspace_id, "--expected-version", "99", "--json"],
    )
    assert conflict.exit_code == 4
    payload = json.loads(conflict.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "CONCURRENCY_CONFLICT"
