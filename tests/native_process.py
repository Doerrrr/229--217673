"""Root-owned observation channel; candidate receives only output file FDs."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

class Call:
    def __init__(self, runner, receipts, label, command, seconds=180, size_limit=-1):
        self.seconds = seconds
        self.stdout = receipts / (label+'.stdout')
        self.stderr = receipts / (label+'.stderr')
        self.process = subprocess.Popen([str(runner), str(seconds), str(self.stdout),
            str(self.stderr), str(size_limit), *map(str, command)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as select:
            select.register(self.process.stdout, selectors.EVENT_READ)
            if not select.select(10):
                self.process.kill(); self.process.wait()
                raise RuntimeError('author launcher did not deliver child identity')
            line = self.process.stdout.readline()
        self.started = json.loads(line)
        assert self.started['child_pid'] == self.started['process_group'] > 1
        self.finished = None

    def kill_candidate(self):
        try:
            os.killpg(self.started['process_group'], signal.SIGKILL)
            return True
        except ProcessLookupError: return False

    def finish(self):
        if self.finished is not None: return self.finished
        output, errors = self.process.communicate(timeout=self.seconds+15)
        if self.process.returncode:
            raise RuntimeError('author measuring process failed: '+errors.decode(errors='replace'))
        self.finished = json.loads(output)
        self.finished.update(stdout_path=str(self.stdout), stderr_path=str(self.stderr),
            stdout_bytes=self.stdout.stat().st_size, stderr_bytes=self.stderr.stat().st_size,
            stderr=self.stderr.read_text(errors='replace')[:8192])
        return self.finished

    def ready(self, gate, seconds=15):
        deadline = time.monotonic()+seconds
        while not (gate/'ready').exists():
            if self.process.poll() is not None:
                raise AssertionError('candidate exited before PREPARED: '+str(self.finish()))
            if time.monotonic() > deadline:
                raise AssertionError('candidate did not reach PREPARED in controlled small case')
            time.sleep(.01)
        return json.loads((gate/'ready').read_bytes())

class Native:
    def __init__(self, binary, runner, root, receipts, codec):
        self.binary, self.runner = str(binary), Path(runner)
        self.root, self.receipts, self.codec = Path(root), Path(receipts), str(codec)
        self.active, self.calls, self.abnormal = [], [], []
        self.counter = 0

    def start(self, label, arguments, seconds=180, size_limit=-1, binary=None):
        self.counter += 1
        call = Call(self.runner, self.receipts, f'{self.counter:03d}_{label}',
                    [binary or self.binary, *arguments], seconds, size_limit)
        self.active.append(call)
        return call

    def finish(self, call, controlled_kill=False):
        result = call.finish()
        if call not in self.active: return result
        self.active.remove(call)
        self.calls.append(result)
        expected_kill=controlled_kill and result['returncode']==-signal.SIGKILL
        if result['timed_out'] or (result['returncode'] < 0 and not expected_kill):
            self.abnormal.append(result)
        return result

    def cleanup(self):
        for call in list(self.active):
            killed=call.kill_candidate()
            self.finish(call, controlled_kill=killed)

    def invoke(self, label, arguments, seconds=180, size_limit=-1):
        return self.finish(self.start(label, arguments, seconds, size_limit))
