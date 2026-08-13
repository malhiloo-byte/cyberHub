from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cyberos.application.doctor import run_doctor
from cyberos.application.version import get_version_info
from cyberos.config.loader import load_config
from cyberos.config.models import CyberOSConfig
from cyberos.config.redaction import redact
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError
from cyberos.core.serialization import dumps
from cyberos.logging.setup import bind_context, configure_logging

app = typer.Typer(no_args_is_help=True, add_completion=False)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")


def _emit(payload: object, output_format: str) -> None:
    if output_format == "json":
        typer.echo(dumps(payload))
    else:
        typer.echo(dumps(payload))


def _load(path: Path | None) -> CyberOSConfig:
    config = load_config(path)
    configure_logging(config.runtime.log_level, config.runtime.log_format)
    context = OperationContext(environment=config.app.environment)
    bind_context(correlation_id=str(context.correlation_id), operation_id=str(context.operation_id))
    return config


@app.command()
def version() -> None:
    """Print CyberOS core version and runtime information."""
    typer.echo(dumps(get_version_info()))


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
        _emit(
            {"ok": False, "error": {"code": error.code.value, "message": error.message}},
            "json" if json_output else "text",
        )
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


def main() -> None:
    app()
