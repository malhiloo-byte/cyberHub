from __future__ import annotations

from collections.abc import Callable

from cyberos.config.models import CyberOSConfig
from cyberos.core.errors import CyberOSError
from cyberos.infrastructure.environment import check_python_version
from cyberos.infrastructure.filesystem import check_directory
from cyberos.infrastructure.runtime import check_serialization


def run_doctor(config: CyberOSConfig) -> dict[str, object]:
    checks: list[dict[str, str | bool]] = []
    failures: list[dict[str, str]] = []
    checks_to_run: tuple[Callable[[], dict[str, str | bool]], ...] = (
        lambda: check_python_version(),
        lambda: check_directory(config.runtime.data_dir),
        lambda: check_directory(config.runtime.log_dir),
        check_serialization,
    )
    for check in checks_to_run:
        try:
            checks.append(check())
        except CyberOSError as error:
            checks.append({"name": error.code.value, "ok": False})
            failures.append({"code": error.code.value, "message": error.message})
    return {"ok": not failures, "checks": checks, "failures": failures}
