"""Root-owned measuring parent; candidate roles use fixed, in-range identities."""
import json
import os
from pathlib import Path
import signal
import sys
import time


def main():
    role, seconds, out, err, home, cwd, *command = sys.argv[1:]
    assert role in ('publish', 'read') and command
    seconds = int(seconds)
    assert 1 <= seconds <= 600
    identity = ['--reuid=10001', '--regid=10001'] if role == 'publish' else ['--reuid=10002', '--regid=10002']
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            os.umask(0o077)
            stdout = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            stderr = os.open(err, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.dup2(stdout, 1)
            os.dup2(stderr, 2)
            os.close(stdout)
            os.close(stderr)
            os.chdir(cwd)
            os.environ.update(HOME=home, TMPDIR=home, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
            os.execv('/usr/bin/setpriv', ['setpriv', *identity, '--clear-groups', '--no-new-privs', '--', *command])
        except BaseException as error:
            os.write(2, ('measurement launch failed: ' + repr(error) + '\n').encode())
            os._exit(125)
    print(json.dumps({'child_pid': pid, 'process_group': pid}), flush=True)
    begin = time.monotonic()
    timed_out = False
    while True:
        ended, status, usage = os.wait4(pid, os.WNOHANG)
        if ended:
            break
        if time.monotonic() - begin > seconds:
            timed_out = True
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status, usage = os.wait4(pid, 0)
            break
        time.sleep(.01)
    print(json.dumps({'returncode': os.waitstatus_to_exitcode(status), 'timed_out': timed_out,
                      'peak_rss_kib': usage.ru_maxrss, 'elapsed_seconds': round(time.monotonic() - begin, 4)}), flush=True)


if __name__ == '__main__':
    main()
