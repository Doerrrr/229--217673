"""Read output in a fixed-identity child without changing verifier credentials."""
import json
import os
from pathlib import Path
import stat


def _candidate_bytes(path):
    """Open only ordinary files using the caller's already restricted identity."""
    descriptor = None
    original_mode = None
    try:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            info = os.stat(path)
            if info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode):
                return b''
            # A candidate-owned mode-000 ordinary file was readable by the old
            # root verifier. Preserve that behavior without reading root files.
            original_mode = stat.S_IMODE(info.st_mode)
            os.chmod(path, original_mode | stat.S_IRUSR)
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return b''
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            return handle.read()
    except (OSError, ValueError):
        return b''
    finally:
        if descriptor is not None:
            try:
                if original_mode is not None:
                    os.fchmod(descriptor, original_mode)
            finally:
                os.close(descriptor)


def _child_bytes(path):
    read_fd, write_fd = os.pipe()
    try:
        pid = os.fork()
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    if pid == 0:
        exit_code = 1
        try:
            os.close(read_fd)
            try:
                # These are the only credential changes in this module.
                # The child irreversibly adopts literal IDs within 0..65535.
                os.setgroups([])
                os.setgid(10001)
                os.setuid(10001)
                payload = b'D' + _candidate_bytes(path)
                failed = False
            except BaseException as error:
                detail = (type(error).__name__ + ': ' + str(error))[:2048]
                payload = b'E' + detail.encode('utf-8', errors='replace')
                failed = True
            remaining = memoryview(payload)
            while remaining:
                written = os.write(write_fd, remaining)
                if written <= 0:
                    raise OSError('output reader pipe write failed')
                remaining = remaining[written:]
            exit_code = 1 if failed else 0
        finally:
            # Do not unwind into the verifier's code in this forked process.
            os._exit(exit_code)
    try:
        os.close(write_fd)
        chunks = []
        while True:
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b''.join(chunks)
    finally:
        try:
            os.close(read_fd)
        finally:
            _, status = os.waitpid(pid, 0)
    if os.waitstatus_to_exitcode(status) != 0 or not payload.startswith(b'D'):
        detail = payload[1:].decode('utf-8', errors='replace') if payload.startswith(b'E') else 'missing data or abnormal child exit'
        raise RuntimeError('output reader child failed: ' + detail)
    return payload[1:]


def rows_from(path):
    # All candidate processes have been reaped before this call. The verifier
    # is single-threaded; its own credentials are never changed, even on error.
    uid, gid, groups = os.geteuid(), os.getegid(), os.getgroups()
    if not 0 <= uid <= 65535:
        raise RuntimeError('verifier effective UID must be in 0..65535')
    if not 0 <= gid <= 65535:
        raise RuntimeError('verifier effective GID must be in 0..65535')
    if not all(0 <= group <= 65535 for group in groups):
        raise RuntimeError('verifier supplementary GIDs must be in 0..65535')
    raw = _child_bytes(path) if uid == 0 else _candidate_bytes(path)
    try:
        return [json.loads(line) for line in raw.splitlines()]
    except (ValueError, RecursionError):
        return []
