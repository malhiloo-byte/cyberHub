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


def create_scope(tmp_path: Path) -> str:
    workspace = invoke(tmp_path, ["workspace", "create", "Scope CLI Workspace", "--json"])
    workspace_id = json.loads(workspace.stdout)["data"]["id"]
    engagement = invoke(
        tmp_path,
        [
            "engagement",
            "create",
            workspace_id,
            "Scope CLI Engagement",
            "--kind",
            "learning",
            "--json",
        ],
    )
    engagement_id = json.loads(engagement.stdout)["data"]["id"]
    scope = invoke(
        tmp_path,
        ["scope", "create", engagement_id, "CLI Scope", "--json"],
    )
    assert scope.exit_code == 0
    return json.loads(scope.stdout)["data"]["id"]


def test_scope_target_cli_lifecycle_and_json_evaluation(tmp_path: Path) -> None:
    scope_id = create_scope(tmp_path)
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
    assert include.exit_code == 0
    assert exclude.exit_code == 0

    authorized = invoke(
        tmp_path,
        [
            "scope",
            "authorize",
            scope_id,
            "--authorization-reference",
            "approval-cli",
            "--json",
        ],
    )
    assert authorized.exit_code == 0
    assert json.loads(authorized.stdout)["data"]["status"] == "authorized"

    included = invoke(
        tmp_path,
        [
            "scope",
            "evaluate",
            scope_id,
            "--kind",
            "fqdn",
            "--value",
            "api.example.com",
            "--json",
        ],
    )
    assert included.exit_code == 0
    included_payload = json.loads(included.stdout)
    assert included_payload["ok"] is True
    assert included_payload["data"]["decision"] == "included"
    assert included_payload["data"]["reason"] == "included_by_authorized_rule"

    excluded = invoke(
        tmp_path,
        [
            "scope",
            "evaluate",
            scope_id,
            "--kind",
            "fqdn",
            "--value",
            "admin.example.com",
            "--json",
        ],
    )
    assert excluded.exit_code == 2
    excluded_payload = json.loads(excluded.stdout)
    assert excluded_payload["ok"] is True
    assert excluded_payload["data"]["decision"] == "excluded"


def test_scope_cli_denied_and_invalid_kind_are_safe(tmp_path: Path) -> None:
    scope_id = create_scope(tmp_path)
    denied = invoke(
        tmp_path,
        [
            "scope",
            "evaluate",
            scope_id,
            "--kind",
            "fqdn",
            "--value",
            "outside.example.com",
            "--json",
        ],
    )
    assert denied.exit_code == 2
    denied_payload = json.loads(denied.stdout)
    assert denied_payload["ok"] is True
    assert denied_payload["data"]["decision"] == "denied_out_of_scope"
    assert "traceback" not in denied.stdout.lower()

    invalid = invoke(
        tmp_path,
        [
            "target",
            "add",
            scope_id,
            "--rule",
            "include",
            "--kind",
            "unknown",
            "--value",
            "outside.example.com",
            "--json",
        ],
    )
    assert invalid.exit_code == 1
    invalid_payload = json.loads(invalid.stdout)
    assert invalid_payload["ok"] is False
    assert invalid_payload["error"]["code"] == "INVALID_INPUT"
    assert "traceback" not in invalid.stdout.lower()
    assert "sqlite" not in invalid.stdout.lower()


def test_scope_cli_text_evaluation_is_human_readable(tmp_path: Path) -> None:
    scope_id = create_scope(tmp_path)
    invoke(
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
            "text.example.com",
            "--json",
        ],
    )
    invoke(
        tmp_path,
        [
            "scope",
            "authorize",
            scope_id,
            "--authorization-reference",
            "approval-text",
            "--json",
        ],
    )
    result = invoke(
        tmp_path,
        [
            "scope",
            "evaluate",
            scope_id,
            "--kind",
            "fqdn",
            "--value",
            "text.example.com",
        ],
    )
    assert result.exit_code == 0
    assert "decision: included" in result.stdout
    assert "reason: included_by_authorized_rule" in result.stdout
    assert "correlation_id:" in result.stdout
