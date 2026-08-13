from __future__ import annotations

import sys

from cyberos.core.errors import CyberOSError, ErrorCode


def check_python_version(min_major: int = 3, min_minor: int = 11) -> dict[str, str | bool]:
    version = sys.version_info
    supported = (version.major, version.minor) >= (min_major, min_minor)
    result: dict[str, str | bool] = {
        "name": "python_version",
        "ok": supported,
        "value": f"{version.major}.{version.minor}.{version.micro}",
    }
    if not supported:
        raise CyberOSError(
            ErrorCode.RUNTIME_UNSUPPORTED,
            "Python 3.11 or newer is required.",
            details={"detected": result["value"]},
        )
    return result
