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
        if descriptor is not None:
            if original_mode is not None:
                os.fchmod(descriptor, original_mode)
            os.close(descriptor)
        if uid == 0:
            os.seteuid(uid)
            os.setegid(gid)
            os.setgroups(groups)
