from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypeVar
from uuid import UUID

import typer

from cyberos import __version__
from cyberos.application.doctor import run_doctor
from cyberos.application.nmap_localhost import NmapLocalhostScanService
from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.application.services.common import execute_service
from cyberos.application.services.engagement import (
    EngagementService,
    parse_engagement_id,
)
from cyberos.application.services.scope import ScopeService, TargetService
from cyberos.application.services.task import TaskService, parse_task_id
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
from cyberos.domain.scope.matcher import MatchDecision
from cyberos.domain.scope.primitives import ScopeId, validate_scope_id
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.domain.workspace.model import WorkspaceStatus
from cyberos.logging.setup import bind_context, configure_logging
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner

app = typer.Typer(no_args_is_help=True, add_completion=False)
config_app = typer.Typer(no_args_is_help=True)
workspace_app = typer.Typer(no_args_is_help=True)
engagement_app = typer.Typer(no_args_is_help=True)
scope_app = typer.Typer(no_args_is_help=True)
target_app = typer.Typer(no_args_is_help=True)
task_app = typer.Typer(no_args_is_help=True)
recon_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(workspace_app, name="workspace")
app.add_typer(engagement_app, name="engagement")
app.add_typer(scope_app, name="scope")
app.add_typer(target_app, name="target")
app.add_typer(task_app, name="task")
app.add_typer(recon_app, name="recon")

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
    if isinstance(result.data, TaskRecord):
        data: object = _task_record_payload(result.data, include_output=True)
    elif isinstance(result.data, (list, tuple)) and all(
        isinstance(item, TaskRecord) for item in result.data
    ):
        data = [_task_record_payload(item, include_output=False) for item in result.data]
    else:
        return result.model_dump(mode="json")
    return {
        "ok": result.ok,
        "data": data if result.ok else None,
        "error": result.error.model_dump(mode="json") if result.error is not None else None,
        "meta": result.meta.model_dump(mode="json"),
    }


def _task_record_payload(record: TaskRecord, *, include_output: bool) -> dict[str, Any]:
    task = record.task
    payload: dict[str, Any] = {
        "id": str(task.id),
        "scope_id": str(task.scope_id),
        "target_id": str(task.target_id),
        "status": task.status.value,
        "version": task.version,
        "command": list(task.execution_spec.command),
        "timeout_seconds": task.execution_spec.timeout_seconds,
        "max_output_bytes": task.execution_spec.max_output_bytes,
        "env_policy": list(task.execution_spec.env_policy.allowed_keys),
        "authorization_expires_at": (
            task.authorization_expires_at.isoformat()
            if task.authorization_expires_at is not None
            else None
        ),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at is not None else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at is not None else None,
        "failed_at": task.failed_at.isoformat() if task.failed_at is not None else None,
        "cancelled_at": task.cancelled_at.isoformat() if task.cancelled_at is not None else None,
    }
    if record.result is not None:
        result = record.result
        result_payload: dict[str, Any] = {
            "exit_code": result.exit_code,
            "truncated": result.truncated,
            "duration_ms": round(result.duration_seconds * 1000),
            "timeout_exceeded": result.timeout_exceeded,
            "failure_reason": (
                result.failure_reason.value if result.failure_reason is not None else None
            ),
            "error_message": result.error_message,
        }
        if include_output:
            result_payload["stdout"] = result.stdout.decode("utf-8", errors="replace")
            result_payload["stderr"] = result.stderr.decode("utf-8", errors="replace")
        payload["result"] = result_payload
    else:
        payload["result"] = None
    return payload


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
        if "decision" in data:
            lines = [
                f"decision: {data['decision']}",
                f"reason: {data.get('reason', '')}",
            ]
            if data.get("matched_target_id") is not None:
                lines.append(f"matched_target_id: {data['matched_target_id']}")
            if data.get("matching_rule") is not None:
                lines.append(f"matching_rule: {data['matching_rule']}")
            return "\n".join(lines)
        if "scope_id" in data and "target_id" in data and "status" in data:
            lines = [
                f"id: {data['id']}",
                f"scope_id: {data['scope_id']}",
                f"target_id: {data['target_id']}",
                f"status: {data['status']}",
                f"version: {data['version']}",
            ]
            result = data.get("result")
            if isinstance(result, dict):
                lines.extend(
                    f"{key}: {result[key]}"
                    for key in ("exit_code", "truncated", "duration_ms", "timeout_exceeded")
                    if result.get(key) is not None
                )
                for key in ("stdout", "stderr"):
                    if key in result:
                        lines.append(f"{key}: {result[key]}")
            return "\n".join(lines)
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


def _invoke(
    operation: Callable[[OperationContext], OperationResult[T]],
    json_output: bool,
    *,
    error_exit_code: Callable[[CyberOSError], int] | None = None,
    failed_result_exit_code: int | None = None,
) -> None:
    context = OperationContext()
    started_at = time.perf_counter()
    try:
        result = operation(context)
    except CyberOSError as caught_error:
        result = OperationResult.failure(caught_error, context, started_at)
    _render_result(result, json_output)
    if not result.ok and result.error is not None:
        rendered_error = CyberOSError(ErrorCode(result.error.code), result.error.message)
        code = (
            error_exit_code(rendered_error)
            if error_exit_code is not None
            else EXIT_CODES[rendered_error.code]
        )
        raise typer.Exit(code=code)
    if (
        failed_result_exit_code is not None
        and result.ok
        and isinstance(result.data, TaskRecord)
        and result.data.task.status is TaskStatus.FAILED
    ):
        raise typer.Exit(code=failed_result_exit_code)


def _invoke_scope_evaluation(
    operation: Callable[[OperationContext], OperationResult[Any]], json_output: bool
) -> None:
    context = OperationContext()
    started_at = time.perf_counter()
    try:
        result = operation(context)
    except CyberOSError as caught_error:
        result = OperationResult.failure(caught_error, context, started_at)
    _render_result(result, json_output)
    if not result.ok:
        if result.error is None:
            raise typer.Exit(code=1)
        rendered_error = CyberOSError(ErrorCode(result.error.code), result.error.message)
        raise typer.Exit(code=_scope_cli_exit(rendered_error))
    if result.data is not None and result.data.decision is not MatchDecision.INCLUDED:
        raise typer.Exit(code=2)


def _scope_cli_exit(error: CyberOSError) -> int:
    if error.code in {
        ErrorCode.SCOPE_NOT_AUTHORIZED,
        ErrorCode.SCOPE_EXPIRED,
        ErrorCode.SCOPE_ARCHIVED,
        ErrorCode.TARGET_EXCLUDED,
        ErrorCode.TARGET_OUT_OF_SCOPE,
    }:
        return 2
    return 1


def _task_cli_exit(error: CyberOSError) -> int:
    if error.code in {
        ErrorCode.SCOPE_NOT_AUTHORIZED,
        ErrorCode.SCOPE_EXPIRED,
        ErrorCode.SCOPE_ARCHIVED,
        ErrorCode.TARGET_EXCLUDED,
        ErrorCode.TARGET_OUT_OF_SCOPE,
        ErrorCode.TASK_AUTHORIZATION_REQUIRED,
        ErrorCode.TASK_AUTHORIZATION_SCOPE_MISMATCH,
        ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH,
        ErrorCode.TASK_AUTHORIZATION_EXPIRED,
    }:
        return 2
    return 1


def parse_scope_id(value: str) -> ScopeId:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Scope ID must be a valid UUID4.") from exc
    return validate_scope_id(identifier)


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


@scope_app.command("create")
def scope_create(
    engagement_id: Annotated[str, typer.Argument()],
    name: Annotated[str, typer.Argument()],
    description: Annotated[str, typer.Option("--description")] = "",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Create a draft Scope for an Engagement."""
    _invoke(
        lambda context: ScopeService(_service_factory(file)).create(
            parse_engagement_id(engagement_id),
            name,
            description,
            context=context,
        ),
        json_output,
        error_exit_code=_scope_cli_exit,
    )


@scope_app.command("authorize")
def scope_authorize(
    scope_id: Annotated[str, typer.Argument()],
    authorization_reference: Annotated[str, typer.Option("--authorization-reference")],
    expires_at: Annotated[str | None, typer.Option("--expires-at")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Authorize a Scope with an explicit reference and optional expiry."""
    _invoke(
        lambda context: ScopeService(_service_factory(file)).authorize(
            parse_scope_id(scope_id),
            authorization_reference,
            _parse_datetime(expires_at, "expires_at"),
            context=context,
        ),
        json_output,
        error_exit_code=_scope_cli_exit,
    )


@target_app.command("add")
def target_add(
    scope_id: Annotated[str, typer.Argument()],
    rule: Annotated[str, typer.Option("--rule")],
    kind: Annotated[str, typer.Option("--kind")],
    value: Annotated[str, typer.Option("--value")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Add a Target with explicit rule, kind, and value."""
    _invoke(
        lambda context: TargetService(_service_factory(file)).add(
            parse_scope_id(scope_id),
            _parse_enum(rule, TargetRule, "rule"),
            _parse_enum(kind, TargetKind, "kind"),
            value,
            context=context,
        ),
        json_output,
        error_exit_code=_scope_cli_exit,
    )


@scope_app.command("evaluate")
def scope_evaluate(
    scope_id: Annotated[str, typer.Argument()],
    kind: Annotated[str, typer.Option("--kind")],
    value: Annotated[str, typer.Option("--value")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Evaluate an explicit TargetCandidate against a Scope without executing it."""
    _invoke_scope_evaluation(
        lambda context: _evaluate_cli_candidate(
            context,
            file,
            scope_id,
            kind,
            value,
        ),
        json_output,
    )


@task_app.command("run")
def task_run(
    scope_id: Annotated[str, typer.Argument()],
    target_id: Annotated[str, typer.Argument()],
    command: Annotated[list[str], typer.Argument()],
    kind: Annotated[str, typer.Option("--kind")],
    value: Annotated[str, typer.Option("--value")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Authorize and execute one explicit argv-bound Task."""
    if not command:
        raise typer.BadParameter("At least one command argv part is required.")
    _invoke(
        lambda context: TaskService(_service_factory(file)).run(
            parse_scope_id(scope_id),
            _parse_task_target_id(target_id),
            TargetCandidate(value, _parse_enum(kind, TargetKind, "kind")),
            ExecutionSpec(command=tuple(command)),
            context=context,
        ),
        json_output,
        error_exit_code=_task_cli_exit,
        failed_result_exit_code=2,
    )


@task_app.command("list")
def task_list(
    scope_id: Annotated[str | None, typer.Option("--scope-id")] = None,
    target_id: Annotated[str | None, typer.Option("--target-id")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """List Tasks by exactly one Scope or Target filter."""
    _invoke(
        lambda context: TaskService(_service_factory(file)).list(
            scope_id=parse_scope_id(scope_id) if scope_id else None,
            target_id=_parse_task_target_id(target_id) if target_id else None,
            context=context,
        ),
        json_output,
        error_exit_code=_task_cli_exit,
    )


@task_app.command("show")
def task_show(
    task_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Show one persisted Task snapshot and its execution result."""
    _invoke(
        lambda context: TaskService(_service_factory(file)).show(
            parse_task_id(task_id), context=context
        ),
        json_output,
        error_exit_code=_task_cli_exit,
    )


@recon_app.command("nmap-localhost")
def recon_nmap_localhost(
    scope_id: Annotated[str, typer.Argument()],
    target_id: Annotated[str, typer.Argument()],
    nmap_sha256: Annotated[str, typer.Option("--nmap-sha256", min=64, max=64)],
    nmap_version: Annotated[str, typer.Option("--nmap-version")],
    ports: Annotated[str, typer.Option("--ports")] = "22,80,443",
    nmap_path: Annotated[str, typer.Option("--nmap-path")] = "/usr/bin/nmap",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    file: Annotated[Path | None, typer.Option("--file", exists=True, dir_okay=False)] = None,
) -> None:
    """Run the approved localhost TCP Connect Nmap workflow."""
    try:
        parsed_ports = tuple(int(value.strip()) for value in ports.split(",") if value.strip())
    except ValueError as exc:
        raise typer.BadParameter("--ports must be a comma-separated integer list.") from exc
    _invoke(
        lambda context: NmapLocalhostScanService(_service_factory(file)).run(
            parse_scope_id(scope_id),
            _parse_task_target_id(target_id),
            binary_path=nmap_path,
            expected_sha256=nmap_sha256,
            expected_version=nmap_version,
            ports=parsed_ports,
            context=context,
        ),
        json_output,
        error_exit_code=_task_cli_exit,
    )


def _evaluate_cli_candidate(
    context: OperationContext,
    file: Path | None,
    scope_id: str,
    kind: str,
    value: str,
) -> OperationResult[Any]:
    target_kind = _parse_enum(kind, TargetKind, "kind")
    candidate = TargetCandidate(value, target_kind)
    return execute_service(
        lambda: ScopeValidationService(_service_factory(file)).evaluate_candidate(
            parse_scope_id(scope_id), candidate
        ),
        context=context,
    )


def _parse_task_target_id(value: str) -> TargetId:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Target ID must be a valid UUID4.") from exc
    if identifier.version != 4:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Target ID must be a valid UUID4.")
    return TargetId(identifier)


def main() -> None:
    app()
