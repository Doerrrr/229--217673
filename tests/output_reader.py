"""Read completed candidate output without privileged path traversal or FIFO waits."""
import json
import os
from pathlib import Path
import stat


def rows_from(path):
    # The verifier has no other threads, and all candidate processes from this
    # call have been reaped before this function. Never execute candidate code
    # while the effective identity is changed.
    uid, gid, groups = os.geteuid(), os.getegid(), os.getgroups()
    # Reject unsupported verifier identities before changing any credentials.
    # All dynamic values later passed to setegid/setgroups are bounded here.
    if not 0 <= uid <= 65535:
        raise RuntimeError('verifier effective UID must be in 0..65535')
    if not 0 <= gid <= 65535:
        raise RuntimeError('verifier effective GID must be in 0..65535')
    if not all(0 <= group <= 65535 for group in groups):
        raise RuntimeError('verifier supplementary GIDs must be in 0..65535')
    descriptor = None
    original_mode = None
    try:
        if uid == 0:
            os.setgroups([])
            os.setegid(10001)
            os.seteuid(10001)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            info = os.stat(path)
            if info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode):
                return []
            # A candidate-owned mode-000 ordinary file was readable by the old
            # root verifier. Preserve that behavior without reading root files.
            original_mode = stat.S_IMODE(info.st_mode)
            os.chmod(path, original_mode | stat.S_IRUSR)
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return []
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            raw = handle.read()
        return [json.loads(line) for line in raw.splitlines()]
    except (OSError, ValueError, RecursionError):
        return []
    finally:
        try:
            if descriptor is not None:
                try:
                    if original_mode is not None:
                        os.fchmod(descriptor, original_mode)
                finally:
                    os.close(descriptor)
        finally:
            if uid == 0:
                os.seteuid(0)
                os.setegid(gid)
                os.setgroups(groups)
