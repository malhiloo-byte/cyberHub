from __future__ import annotations

import os
from pathlib import Path

from cyberos.core.errors import CyberOSError, ErrorCode


def check_directory(path: Path, create: bool = False) -> dict[str, str | bool]:
    expanded = path.expanduser()
    if create:
        try:
            expanded.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CyberOSError(
                ErrorCode.PATH_NOT_WRITABLE,
                "The runtime directory could not be created.",
                details={"path": str(expanded)},
            ) from exc
    if not expanded.exists() or not expanded.is_dir() or not os.access(expanded, os.W_OK):
        raise CyberOSError(
            ErrorCode.PATH_NOT_WRITABLE,
            "The runtime directory is not writable.",
            details={"path": str(expanded)},
        )
    return {"name": f"writable:{expanded}", "ok": True, "value": str(expanded)}
