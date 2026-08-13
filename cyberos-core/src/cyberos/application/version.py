from __future__ import annotations

import platform

from cyberos import __version__


def get_version_info() -> dict[str, str]:
    return {
        "name": "cyberos-core",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.system().lower(),
    }
