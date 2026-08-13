"""CLI integration and fail-closed tests for TaskService orchestration."""

from __future__ import annotations

import json
import sys
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


def setup_authorized_scope(tmp_path: Path) -> tuple[str, str, str]:
    workspace = invoke(tmp_path, ["workspace", "create", "Task CLI Workspace", "--json"])
    workspace_id = json.loads(workspace.stdout)["data"]["id"]
    engagement = invoke(
        tmp_path,
        [
            "engagement",
            "create",
            workspace_id,
            "Task CLI Engagement",
            "--kind",
            "learning",
            "--json",
        ],
    )
    engagement_id = json.loads(engagement.stdout)["data"]["id"]
    scope = invoke(tmp_path, ["scope", "create", engagement_id, "Task CLI Scope", "--json"])
    scope_id = json.loads(scope.stdout)["data"]["id"]
    include = invoke(
        tmp_path,
        [
            "target",
            "add",
            scope_id,
            "--rule",
            "include",
            "--kind",
            "fqdn",
            "--value",
            "api.example.com",
            "--json",
        ],
    )
    exclude = invoke(
        tmp_path,
        [
            "target",
            "add",
            scope_id,
            "--rule",
            "exclude",
            "--kind",
            "fqdn",
            "--value",
            "admin.example.com",
            "--json",
        ],
    )
    authorize = invoke(
        tmp_path,
        [
            "scope",
            "authorize",
            scope_id,
            "--authorization-reference",
            "approval-task-cli",
            "--json",
        ],
    )
    assert include.exit_code == 0
    assert exclude.exit_code == 0
    assert authorize.exit_code == 0
    return (
        scope_id,
        json.loads(include.stdout)["data"]["id"],
        json.loads(exclude.stdout)["data"]["id"],
    )


def invoke_task_run(
    tmp_path: Path,
    scope_id: str,
    target_id: str,
    value: str,
    *command: str,
) -> object:
    return runner.invoke(
        app,
        [
            "task",
            "run",
            scope_id,
            target_id,
            "--kind",
            "fqdn",
            "--value",
            value,
            "--json",
            "--file",
            str(config_file(tmp_path)),
            "--",
            *command,
        ],
    )


def test_task_cli_run_list_show_and_literal_argv(tmp_path: Path) -> None:
    scope_id, target_id, _ = setup_authorized_scope(tmp_path)
    payload = "; echo CLI_INJECTION && echo PIPE | echo REDIRECT"
    run_result = invoke_task_run(
        tmp_path,
        scope_id,
        target_id,
        "api.example.com",
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1])",
        payload,
    )

    assert run_result.exit_code == 0, (
        f"stdout={run_result.stdout!r} exception={run_result.exception!r}"
    )
    run_payload = json.loads(run_result.stdout)
    assert run_payload["ok"] is True
    assert run_payload["data"]["status"] == "completed"
    assert run_payload["data"]["result"]["stdout"] == f"{payload}\n"
    task_id = run_payload["data"]["id"]

    listed = invoke(
        tmp_path,
        ["task", "list", "--scope-id", scope_id, "--json"],
    )
    assert listed.exit_code == 0
    assert len(json.loads(listed.stdout)["data"]) == 1

    shown = invoke(tmp_path, ["task", "show", task_id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["data"]["result"]["exit_code"] == 0

    human = invoke(tmp_path, ["task", "show", task_id])
    assert human.exit_code == 0
    assert f"id: {task_id}" in human.stdout
    assert "correlation_id:" in human.stdout


def test_task_cli_excluded_target_is_fail_closed_and_does_not_create_task(
    tmp_path: Path,
) -> None:
    scope_id, _, excluded_target_id = setup_authorized_scope(tmp_path)
    rejected = invoke_task_run(
        tmp_path,
        scope_id,
        excluded_target_id,
        "admin.example.com",
        "echo",
        "should-not-run",
    )

    assert rejected.exit_code == 2
    payload = json.loads(rejected.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TARGET_EXCLUDED"

    listed = invoke(tmp_path, ["task", "list", "--scope-id", scope_id, "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["data"] == []


def test_task_cli_invalid_filter_is_clean_error(tmp_path: Path) -> None:
    listed = invoke(tmp_path, ["task", "list", "--json"])

    assert listed.exit_code == 1
    payload = json.loads(listed.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_INPUT"
    assert "Traceback" not in listed.stdout
