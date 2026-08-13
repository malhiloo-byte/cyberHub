from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode


@dataclass(frozen=True, slots=True)
class PreparedDatabasePath:
    """Validated database file path and whether this run created the file."""

    path: Path
    created: bool


def _reject_symlink(path: Path, *, code: ErrorCode, label: str) -> None:
    if path.is_symlink():
        raise CyberOSError(
            code, f"The database {label} must not be a symbolic link.", details={"path": str(path)}
        )


def _validate_private_directory(path: Path) -> None:
    if not path.exists() or not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
        raise CyberOSError(
            ErrorCode.DATABASE_PARENT_NOT_WRITABLE,
            "The database parent directory is not writable.",
            details={"path": str(path)},
        )
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o022:
            current_uid = getattr(os, "getuid", lambda: -1)()
            if path.stat().st_uid == current_uid:
                try:
                    os.chmod(path, 0o700)
                except OSError as exc:
                    raise CyberOSError(
                        ErrorCode.DATABASE_PERMISSION_POLICY_FAILED,
                        "The database parent directory could not be tightened.",
                        details={"path": str(path)},
                    ) from exc
            else:
                raise CyberOSError(
                    ErrorCode.DATABASE_PERMISSION_POLICY_FAILED,
                    "The database parent directory is group/world writable.",
                    details={"path": str(path)},
                )


def prepare_database_path(settings: DatabaseSettings) -> PreparedDatabasePath:
    """Create or validate a local database path under the approved file policy."""

    path = settings.path.expanduser()
    if not path.is_absolute() or not str(path) or "\x00" in str(path):
        raise CyberOSError(
            ErrorCode.DATABASE_PATH_INVALID,
            "The database path must be an absolute path without NUL bytes.",
            details={"path": str(path)},
        )
    if path.exists() and path.is_dir():
        raise CyberOSError(
            ErrorCode.DATABASE_PATH_INVALID,
            "The database path points to a directory.",
            details={"path": str(path)},
        )
    _reject_symlink(path, code=ErrorCode.DATABASE_SYMLINK_UNSAFE, label="file")

    parent = path.parent
    _reject_symlink(parent, code=ErrorCode.DATABASE_SYMLINK_UNSAFE, label="parent directory")
    if not parent.exists():
        if not settings.create_parent:
            raise CyberOSError(
                ErrorCode.DATABASE_PARENT_NOT_WRITABLE,
                "The database parent directory does not exist.",
                details={"path": str(parent)},
            )
        parent.mkdir(parents=True, mode=0o700, exist_ok=False)
    _validate_private_directory(parent)

    if path.exists():
        if not path.is_file() or not os.access(path, os.R_OK | os.W_OK):
            raise CyberOSError(
                ErrorCode.DATABASE_PERMISSION_POLICY_FAILED,
                "The database file is not readable and writable.",
                details={"path": str(path)},
            )
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise CyberOSError(
                ErrorCode.DATABASE_PERMISSION_POLICY_FAILED,
                "The database file permissions are broader than 0600.",
                details={"path": str(path)},
            )
        return PreparedDatabasePath(path=path, created=False)

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    mode = 0o600
    try:
        descriptor = os.open(path, flags, mode)
        os.close(descriptor)
    except FileExistsError:
        return prepare_database_path(settings)
    except OSError as exc:
        raise CyberOSError(
            ErrorCode.DATABASE_PERMISSION_POLICY_FAILED,
            "The database file could not be created safely.",
            details={"path": str(path)},
        ) from exc
    if os.name == "posix":
        os.chmod(path, 0o600)
    return PreparedDatabasePath(path=path, created=True)
