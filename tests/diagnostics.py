"""Root-owned, best-effort verifier diagnostics; never creates a reward."""
import atexit
import functools
import json
import os
from pathlib import Path
import threading
import time
import uuid

ACTIVE = None


class Diagnostics:
    def __init__(self, output):
        global ACTIVE
        self.started = self.case_started = self.phase_started = time.monotonic()
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.attempt = uuid.uuid4().hex[:12]
        self.folder = Path(output) / 'diagnostics' / self.attempt
        self.state = {'phase': 'initializing'}
        self.current_case = {}
        self.enabled = True
        try:
            self.folder.mkdir(parents=True, mode=0o700)
            self.folder.chmod(0o700)
            (self.folder / 'calls').mkdir(mode=0o700)
        except OSError as error:
            self.enabled = False
            print('DDI031_DIAG_WRITE_ERROR ' + repr(error), flush=True)
        ACTIVE = self
        self.emit('verifier_start', phase='initializing', score_policy='UNCHANGED')
        atexit.register(self.on_exit)
        threading.Thread(target=self.heartbeat, daemon=True).start()

    def write_json(self, path, obj):
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('w', encoding='utf8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(obj, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def emit(self, event, phase=None, **fields):
        with self.lock:
            now = time.monotonic()
            if phase is not None:
                self.phase_started = now
                self.state = {**self.current_case, 'phase': phase, **fields}
            entry = dict(attempt=self.attempt, event=event,
                         elapsed_seconds=round(now-self.started, 4),
                         case_elapsed_seconds=round(now-self.case_started, 4),
                         phase_elapsed_seconds=round(now-self.phase_started, 4),
                         state=self.state.copy(), **fields)
            print('DDI031_DIAG ' + json.dumps(entry, ensure_ascii=False, default=str), flush=True)
            if self.enabled:
                try:
                    with (self.folder / 'progress.jsonl').open('a', encoding='utf8') as stream:
                        os.chmod(self.folder / 'progress.jsonl', 0o600)
                        stream.write(json.dumps(entry, ensure_ascii=False, default=str)+'\n')
                        stream.flush()
                        os.fsync(stream.fileno())
                    self.write_json(self.folder / 'last_state.json', entry)
                except OSError as error:
                    self.enabled = False
                    print('DDI031_DIAG_WRITE_ERROR ' + repr(error), flush=True)

    def context(self, case_id, test_group):
        with self.lock:
            self.current_case = dict(case_id=case_id, test_group=test_group)
            self.case_started = time.monotonic()
            self.emit('case_begin', phase='case')

    def checkpoint(self, stem, log):
        if not self.enabled:
            return
        with self.lock:
            try:
                target = self.folder / 'calls'
                self.write_json(target / (stem.name+'.json'), log)
                for suffix, limit in (('.stdout', 2048), ('.stderr', 4096)):
                    source = Path(str(stem)+suffix)
                    with source.open('rb') as stream:
                        stream.seek(max(0, source.stat().st_size-limit))
                        raw = stream.read(limit)
                    path = target / (stem.name+suffix+'.tail.txt')
                    path.write_bytes(raw)
                    path.chmod(0o600)
            except OSError as error:
                self.emit('checkpoint_error', error=repr(error))

    def heartbeat(self):
        while not self.stopped.wait(30):
            self.emit('heartbeat')

    def close(self, status, reward, checks):
        self.stopped.set()
        self.emit('verifier_complete', phase='complete', execution_status=status,
                  reward=reward, checks=checks)

    def on_exit(self):
        if not self.stopped.is_set():
            self.stopped.set()
            self.emit('verifier_exit_before_complete')


def trace_check(function):
    @functools.wraps(function)
    def checked(query, row):
        diag = ACTIVE
        if diag is None:
            return function(query, row)
        diag.emit('graph_check_begin', phase='graph_check', query_id=query.get('id'))
        started = time.monotonic()
        try:
            result = function(query, row)
        except BaseException as error:
            diag.emit('graph_check_exception', phase='case', error=repr(error)[:500])
            raise
        diag.emit('graph_check_end', phase='case', query_id=query.get('id'),
                  check_seconds=round(time.monotonic()-started, 6),
                  okay=bool(result[0]), detail=str(result[1])[:500])
        return result
    return checked
