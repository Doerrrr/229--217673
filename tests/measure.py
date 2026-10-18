"""Root-owned bounded capture and descendant cleanup for one candidate call."""
import ctypes
import json
import os
from pathlib import Path
import selectors
import signal
import sys
import time

CAPTURE_LIMIT_BYTES = 64 * 1024 * 1024  # 32 MiB per stream; drain/discard excess, never kill for logging


def children(parent):
    try:
        return [int(v) for v in Path(f'/proc/{parent}/task/{parent}/children').read_text().split()]
    except (FileNotFoundError, ProcessLookupError):
        return []


def cleanup(group):
    """Reap this measuring parent's descendants, including detached sessions."""
    killed = set()
    deadline = time.monotonic() + 2
    while True:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        pending = children(os.getpid())
        descendants = set()
        while pending:
            ident = pending.pop()
            if ident in descendants:
                continue
            descendants.add(ident)
            pending.extend(children(ident))
        for ident in descendants:
            try:
                os.kill(ident, signal.SIGKILL)
                killed.add(ident)
            except ProcessLookupError:
                pass
        while True:
            try:
                ended, _, _ = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not ended:
                break
        remaining = children(os.getpid())
        if not remaining or time.monotonic() >= deadline:
            return dict(descendants_signalled=len(killed), descendants_remaining=len(remaining))
        time.sleep(.01)


def main():
    role, seconds, out, err, home, cwd, *command = sys.argv[1:]
    assert role in ('publish', 'read') and command
    seconds = int(seconds)
    assert 1 <= seconds <= 600
    # Adopt orphaned grandchildren so setsid() cannot evade this call's cleanup.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0):  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'cannot enable descendant reaping')
    identity = ['--reuid=10001', '--regid=10001'] if role == 'publish' else ['--reuid=10002', '--regid=10002']
    pipes = [os.pipe(), os.pipe()]
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            os.umask(0o077)
            for target, (read, write) in zip((1, 2), pipes):
                os.close(read)
                os.dup2(write, target)
                os.close(write)
            os.chdir(cwd)
            os.environ.update(HOME=home, TMPDIR=home, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
            os.execv('/usr/bin/setpriv', ['setpriv', *identity, '--clear-groups', '--no-new-privs', '--', *command])
        except BaseException as error:
            os.write(2, ('measurement launch failed: ' + repr(error) + '\n').encode())
            os._exit(125)
    print(json.dumps({'child_pid': pid, 'process_group': pid}), flush=True)
    selector = selectors.DefaultSelector()
    files = []
    try:
        for (read, write), target in zip(pipes, (out, err)):
            os.close(write)
            os.set_blocking(read, False)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            files.append(fd)
            selector.register(read, selectors.EVENT_READ, fd)
    except BaseException:
        cleanup(pid)
        for key in list(selector.get_map().values()):
            os.close(key.fd)
        selector.close()
        for fd in files:
            os.close(fd)
        raise
    begin = time.monotonic()
    timed_out = False
    log_truncated = False
    total_bytes = 0
    stream_bytes = {}
    stderr_tail = b''
    usage = status = None
    cleanup_result = None
    try:
        while True:
            for key, _ in selector.select(.01):
                try:
                    block = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(key.fd)
                    os.close(key.fd)
                    continue
                if key.fd == pipes[1][0]:
                    stderr_tail = (stderr_tail + block)[-2048:]
                remaining = max(0, CAPTURE_LIMIT_BYTES // 2 - stream_bytes.get(key.fd, 0))
                if len(block) > remaining:
                    log_truncated = True
                if remaining:
                    kept = block[:remaining]
                    view = memoryview(kept)
                    while view:
                        view = view[os.write(key.data, view):]
                    total_bytes += len(kept)
                    stream_bytes[key.fd] = stream_bytes.get(key.fd, 0) + len(kept)
            if status is None:
                ended, state, measured = os.wait4(pid, os.WNOHANG)
                if ended:
                    status, usage = state, measured
            if status is None and time.monotonic() - begin > seconds:
                timed_out = time.monotonic() - begin > seconds
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(pid, 0)
            if status is not None and cleanup_result is None:
                # The same cleanup applies to successful, failed and timed-out calls.
                cleanup_result = cleanup(pid)
            if cleanup_result and cleanup_result['descendants_remaining']:
                raise RuntimeError('candidate descendants could not be reaped')
            if status is not None and not selector.get_map():
                break
    finally:
        if cleanup_result is None:
            cleanup(pid)
        for key in list(selector.get_map().values()):
            os.close(key.fd)
        selector.close()
        for fd in files:
            os.close(fd)
    print(json.dumps({'returncode': os.waitstatus_to_exitcode(status), 'timed_out': timed_out,
                      'peak_rss_kib': usage.ru_maxrss, 'elapsed_seconds': round(time.monotonic() - begin, 4),
                      'log_truncated': log_truncated, 'captured_bytes': total_bytes,
                      'capture_limit_bytes': CAPTURE_LIMIT_BYTES, 'stderr_tail': stderr_tail.decode(errors='replace'), **cleanup_result}), flush=True)


if __name__ == '__main__':
    main()
