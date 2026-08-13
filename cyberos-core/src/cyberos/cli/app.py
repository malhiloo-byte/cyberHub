from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypeVar

import typer

from cyberos import __version__
from cyberos.application.doctor import run_doctor
from cyberos.application.services.engagement import (
    EngagementService,
    parse_engagement_id,
)
from cyberos.application.services.workspace import WorkspaceService, parse_workspace_id
from cyberos.application.version import get_version_info
from cyberos.config.loader import load_config
from cyberos.config.models import CyberOSConfig
from cyberos.config.redaction import redact
from cyberos.core.context import OperationContext
from cyberos.core.errors import EXIT_CODES, CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.core.serialization import dumps
from cyberos.domain.engagement.model import EngagementKind, EngagementStatus
from cyberos.domain.workspace.model import WorkspaceStatus
from cyberos.logging.setup import bind_context, configure_logging
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner

app = typer.Typer(no_args_is_help=True, add_completion=False)
config_app = typer.Typer(no_args_is_help=True)
workspace_app = typer.Typer(no_args_is_help=True)
engagement_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(workspace_app, name="workspace")
app.add_typer(engagement_app, name="engagement")

T = TypeVar("T")
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "persistence" / "migrations" / "versions"


def _emit(payload: object, output_format: str) -> None:
    typer.echo(dumps(payload))


def _load(path: Path | None) -> CyberOSConfig:
    config = load_config(path)
    configure_logging(config.runtime.log_level, config.runtime.log_format)
    context = OperationContext(environment=config.app.environment)
    bind_context(correlation_id=str(context.correlation_id), operation_id=str(context.operation_id))
    return config


def _service_factory(path: Path | None) -> SQLiteConnectionFactory:
    config = _load(path)
    factory = SQLiteConnectionFactory(config.database)
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def _parse_datetime(value: str | None, label: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CyberOSError(
            ErrorCode.INVALID_INPUT, f"{label} must be a valid ISO-8601 datetime."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CyberOSError(ErrorCode.INVALID_INPUT, f"{label} must include a timezone offset.")
    return parsed


def _parse_enum(value: str, enum_type: type[Any], label: str) -> Any:
    try:
        return enum_type(value.lower())
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise CyberOSError(ErrorCode.INVALID_INPUT, f"{label} must be one of: {allowed}.") from exc


def _result_payload(result: OperationResult[Any]) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _human_data(data: Any) -> str:
    if isinstance(data, list):
        if not data:
            return "No records found."
        lines = []
        for item in data:
            lines.append(
                f"{item['name']} | id={item['id']} | "
                f"status={item['status']} | version={item['version']}"
            )
        return "\n".join(lines)
    if isinstance(data, dict):
        preferred = (
            "id",
            "name",
            "workspace_id",
            "kind",
            "status",
            "version",
            "created_at",
            "updated_at",
            "archived_at",
            "end_at",
        )
        lines = [
            f"{key}: {data[key]}" for key in preferred if key in data and data[key] is not None
        ]
        return "\n".join(lines)
    return str(data)


def _render_result(result: OperationResult[Any], json_output: bool) -> None:
    payload = _result_payload(result)
    if json_output:
        _emit(payload, "json")
        return
    correlation_id = payload["meta"]["correlation_id"]
    if payload["ok"]:
        typer.echo(_human_data(payload.get("data")))
        typer.echo(f"correlation_id: {correlation_id}")
    else:
        error = payload["error"]
        typer.echo(f"Error [{error['code']}]: {error['message']}")
        typer.echo(f"correlation_id: {correlation_id}")


def _invoke(operation: Callable[[OperationContext], OperationResult[T]], json_output: bool) -> None:
    context = OperationContext()
    started_at = time.perf_counter()
    try:
        result = operation(context)
    except CyberOSError as error:
        result = OperationResult.failure(error, context, started_at)
    _render_result(result, json_output)
    if not result.ok and result.error is not None:
        raise typer.Exit(code=EXIT_CODES[ErrorCode(result.error.code)])


@app.command()
def version() -> None:
    """Print CyberOS core version and runtime information."""
    typer.echo(dumps({**get_version_info(), "core_version": __version__}))


@app.command()
def doctor(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Validate the local runtime without network or subprocess execution."""
    try:
        config = _load(file)
        result = run_doctor(config)
        _emit(result, "json" if json_output else "text")
        if not bool(result["ok"]):
            raise typer.Exit(code=3)
    except CyberOSError as error:
        _emit({"ok": False, "error": {"code": error.code.value, "message": error.message}}, "json")
        raise typer.Exit(code=error.exit_code) from error


@config_app.command("show")
def config_show(
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Show validated configuration without secret values."""
    try:
        config = _load(file)
        typer.echo(dumps(redact(config.model_dump(mode="json"))))
    except CyberOSError as error:
        typer.echo(
            dumps({"ok": False, "error": {"code": error.code.value, "message": error.message}})
        )
        raise typer.Exit(code=error.exit_code) from error


@config_app.command("validate")
def config_validate(
    file: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a TOML file without changing local state."""
    try:
        load_config(file)
        typer.echo("Configuration is valid.")
    except CyberOSError as error:
        typer.echo(
            dumps({"ok": False, "error": {"code": error.code.value, "message": error.message}})
        )
        raise typer.Exit(code=error.exit_code) from error


@workspace_app.command("create")
def workspace_create(
    name: Annotated[str, typer.Argument()],
    description: Annotated[str, typer.Option("--description")] = "",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Create a Workspace."""
    _invoke(
        lambda context: WorkspaceService(_service_factory(file)).create(
            name, description, context=context
        ),
        json_output,
    )


@workspace_app.command("list")
def workspace_list(
    status: Annotated[str | None, typer.Option("--status")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """List Workspaces in deterministic order."""
    _invoke(
        lambda context: WorkspaceService(_service_factory(file)).list(
            status=_parse_enum(status, WorkspaceStatus, "status") if status else None,
            context=context,
        ),
        json_output,
    )


@workspace_app.command("show")
def workspace_show(
    workspace_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Show one Workspace."""
    _invoke(
        lambda context: WorkspaceService(_service_factory(file)).show(
            parse_workspace_id(workspace_id), context=context
        ),
        json_output,
    )


@workspace_app.command("archive")
def workspace_archive(
    workspace_id: Annotated[str, typer.Argument()],
    expected_version: Annotated[int, typer.Option("--expected-version", min=1)] = 1,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Archive a Workspace; hard delete is intentionally unavailable."""
    _invoke(
        lambda context: WorkspaceService(_service_factory(file)).archive(
            parse_workspace_id(workspace_id), expected_version=expected_version, context=context
        ),
        json_output,
    )


@engagement_app.command("create")
def engagement_create(
    workspace_id: Annotated[str, typer.Argument()],
    name: Annotated[str, typer.Argument()],
    kind: Annotated[str, typer.Option("--kind")],
    description: Annotated[str, typer.Option("--description")] = "",
    authorization_reference: Annotated[
        str | None, typer.Option("--authorization-reference")
    ] = None,
    start_at: Annotated[str | None, typer.Option("--start-at")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Create an Engagement inside an active Workspace."""
    _invoke(
        lambda context: EngagementService(_service_factory(file)).create(
            parse_workspace_id(workspace_id),
            name,
            _parse_enum(kind, EngagementKind, "kind"),
            description,
            authorization_reference,
            start_at=_parse_datetime(start_at, "start_at"),
            context=context,
        ),
        json_output,
    )


@engagement_app.command("list")
def engagement_list(
    workspace_id: Annotated[str, typer.Argument()],
    status: Annotated[str | None, typer.Option("--status")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """List Engagements for a Workspace."""
    _invoke(
        lambda context: EngagementService(_service_factory(file)).list(
            parse_workspace_id(workspace_id),
            status=_parse_enum(status, EngagementStatus, "status") if status else None,
            context=context,
        ),
        json_output,
    )


@engagement_app.command("show")
def engagement_show(
    engagement_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Show one Engagement."""
    _invoke(
        lambda context: EngagementService(_service_factory(file)).show(
            parse_engagement_id(engagement_id), context=context
        ),
        json_output,
    )


@engagement_app.command("transition")
def engagement_transition(
    engagement_id: Annotated[str, typer.Argument()],
    target_status: Annotated[str, typer.Argument()],
    expected_version: Annotated[int, typer.Option("--expected-version", min=1)] = 1,
    at: Annotated[str | None, typer.Option("--at")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Transition an Engagement through its Domain lifecycle."""
    _invoke(
        lambda context: EngagementService(_service_factory(file)).transition(
            parse_engagement_id(engagement_id),
            _parse_enum(target_status, EngagementStatus, "target_status"),
            expected_version=expected_version,
            at=_parse_datetime(at, "at"),
            end_at=_parse_datetime(end_at, "end_at"),
            context=context,
        ),
        json_output,
    )


@engagement_app.command("archive")
def engagement_archive(
    engagement_id: Annotated[str, typer.Argument()],
    expected_version: Annotated[int, typer.Option("--expected-version", min=1)] = 1,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Archive an Engagement; hard delete is intentionally unavailable."""
    _invoke(
        lambda context: EngagementService(_service_factory(file)).archive(
            parse_engagement_id(engagement_id), expected_version=expected_version, context=context
        ),
        json_output,
    )


def main() -> None:
    app()
