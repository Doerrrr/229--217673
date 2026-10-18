"""Exact algebra checker in a disposable process; exhaustion is not a wrong proof."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
from algebra import check as _algebra_check

CHECK_TIMEOUT_SECONDS = 300
CHECK_TOTAL_SECONDS = 2400
_results = None
_number = 0
_spent_seconds = 0


class CheckerFailure(RuntimeError):
    pass


def configure_results(folder):
    global _results, _number, _spent_seconds
    _number = 0
    _spent_seconds = 0
    _results = Path(folder) / 'checker'
    _results.mkdir(parents=True, exist_ok=True, mode=0o700)


def _record(path, record):
    if path is not None:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        os.replace(temporary, path)


def _worker(connection, q, row, optimum):
    try:
        os.setsid()
        connection.send(('ok', _algebra_check(q, row, optimum)))
    except BaseException as error:
        connection.send(('error', type(error).__name__ + ': ' + str(error)))
    finally:
        connection.close()


def check(q, row, optimum):
    global _number, _spent_seconds
    _number += 1
    path = None if _results is None else _results / f'{_number:04d}.json'
    timeout = min(CHECK_TIMEOUT_SECONDS, CHECK_TOTAL_SECONDS - _spent_seconds)
    record = dict(query_id=q.get('id'), phase='exact_checker', status='RUNNING', timeout_seconds=max(0, timeout),
                  total_budget_seconds=CHECK_TOTAL_SECONDS, spent_seconds=_spent_seconds)
    if timeout <= 0:
        record.update(status='VERIFIER_CHECKER_ERROR', reward=None, error='aggregate exact checker budget exhausted')
        _record(path, record)
        raise CheckerFailure(record['error'])
    _record(path, record)
    context = multiprocessing.get_context('fork')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, q, row, optimum))
    begin = time.monotonic()
    process.start()
    send.close()
    failure = None
    try:
        if not receive.poll(timeout):
            failure = 'exact checker exceeded its independent time budget'
        else:
            try:
                state, result = receive.recv()
            except EOFError:
                failure = 'exact checker exited without a result'
            else:
                if state != 'ok':
                    failure = 'exact checker failed: ' + result
        if failure:
            record.update(status='VERIFIER_CHECKER_ERROR', elapsed_seconds=time.monotonic() - begin,
                          reward=None, error=failure)
            _record(path, record)
            raise CheckerFailure(failure)
        record.update(status='COMPLETED', elapsed_seconds=time.monotonic() - begin)
        _record(path, record)
        return result
    finally:
        _spent_seconds += time.monotonic() - begin
        receive.close()
        if process.is_alive():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.kill()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        process.close()
