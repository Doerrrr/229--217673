"""Private judging harness. Never copied to public projects."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from diagnostics import Diagnostics

class Runner:
    def __init__(self, project, command, result_dir):
        self.base = Path(tempfile.mkdtemp(prefix='ddi-night-', dir='/tmp'))
        os.chmod(self.base, 0o755)
        self.home = self.base / 'candidate'
        self.home.mkdir(mode=0o700)
        self.project = self.home / 'project'
        shutil.copytree(project, self.project, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.output = Path(result_dir)
        self.output.mkdir(parents=True, exist_ok=True)
        self.diagnostics = Diagnostics(self.output)
        self.private = self.base / 'measurements'
        self.private.mkdir(mode=0o700)
        launcher = self.project / 'bin' / command
        launcher.chmod(0o755)
        self.command = [str(launcher)]
        self.number = 0
        self.jobs = []
        self.cases = []
        self.infrastructure = []
        self.own(self.home)
        build = self.project / 'build.sh'
        if build.exists():
            got = self.call(['bash', str(build)], absolute=True)
            if got['returncode'] != 0:
                raise RuntimeError('candidate build failure')

    def own(self, path):
        os.chown(path, 10001, 10001, follow_symlinks=False)
        if path.is_dir() and not path.is_symlink():
            for child in path.rglob('*'):
                os.chown(child, 10001, 10001, follow_symlinks=False)

    def directory(self, name):
        path = self.home / name
        path.mkdir(parents=True, exist_ok=True)
        self.own(path)
        return path

    def file(self, name, raw):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        self.own(path.parent)
        return path

    def start(self, args, absolute=False):
        self.number += 1
        stem = self.private / f'{self.number:04d}'
        stdout, stderr = str(stem) + '.stdout', str(stem) + '.stderr'
        cmd = list(map(str, args)) if absolute else self.command + list(map(str, args))
        self.diagnostics.emit('candidate_begin', phase='candidate', call=self.number, command=cmd)
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('measure.py')),
            'publish', '300', stdout, stderr, str(self.home), str(self.project), *cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        job = {'process': process, 'stdout': stdout, 'stderr': stderr, 'command': cmd, 'stem': stem}
        self.jobs.append(job)
        return job

    def finish(self, job, expected_kill=False):
        if 'result' in job:
            return job['result']
        try:
            raw, diagnostics = job['process'].communicate(timeout=315)
        except BaseException as error:
            self.diagnostics.emit('measurement_exception', call=int(job['stem'].name), error=repr(error)[:500])
            raise
        try:
            records = [json.loads(line) for line in raw.splitlines()]
            value = records[-1]
            if job['process'].returncode != 0 or 'peak_rss_kib' not in value:
                raise ValueError('measurement failed')
        except Exception:
            self.infrastructure.append({'command': job['command'], 'error': diagnostics.decode(errors='replace')})
            raise RuntimeError('measurement infrastructure failure')
        value['stdout'] = Path(job['stdout']).read_bytes()
        value['stderr'] = Path(job['stderr']).read_bytes()
        log = {k: v for k, v in value.items() if k not in ('stdout', 'stderr')}
        log.update(command=job['command'], expected_kill=expected_kill)
        Path(str(job['stem']) + '.json').write_text(json.dumps(log, indent=2))
        self.diagnostics.checkpoint(job['stem'], log)
        self.diagnostics.emit('candidate_end', phase='case', call=int(job['stem'].name),
                              returncode=value['returncode'], timed_out=value['timed_out'],
                              command_seconds=value['elapsed_seconds'], peak_rss_kib=value['peak_rss_kib'],
                              stdout_bytes=len(value['stdout']), stderr_bytes=len(value['stderr']))
        if (value['timed_out'] or value['returncode'] < 0) and not expected_kill:
            self.infrastructure.append({'candidate_runtime': log})
        job['result'] = value
        return value

    def call(self, args, absolute=False):
        return self.finish(self.start(args, absolute))

    def ready(self, job, path):
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if path.is_file():
                return True
            if job['process'].poll() is not None:
                return False
            time.sleep(.02)
        return False

    def kill(self, job):
        # The measuring parent reports the actual candidate process group first.
        line = job['process'].stdout.readline()
        try:
            pg = json.loads(line)['process_group']
            os.killpg(pg, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # communicate now has only the final measurement line, which is sufficient.
        return self.finish(job, expected_kill=True)

    def check(self, group, name, passed, evidence=None):
        self.cases.append({'group': group, 'name': name, 'passed': bool(passed), 'evidence': evidence})
        self.diagnostics.emit('assertion', phase='case', group=group, name=name, passed=bool(passed))

    def save(self, task, weights, all_required=()):
        self.diagnostics.emit('save_begin', phase='saving_results')
        groups = []
        for name, weight in weights.items():
            cases = [c for c in self.cases if c['group'] == name]
            assert cases, name
            passed = sum(c['passed'] for c in cases)
            fraction = int(passed == len(cases)) if name in all_required else passed / len(cases)
            groups.append({'name': name, 'weight': weight, 'passed': passed, 'total': len(cases),
                           'aggregation': 'ALL_REQUIRED' if name in all_required else 'PROPORTIONAL',
                           'earned': weight * fraction})
        status = 'CANDIDATE_RUNTIME_ERROR' if self.infrastructure else 'NORMAL'
        result = {'task': task, 'version': 'v01', 'execution_status': status,
                  'reward': None if self.infrastructure else round(sum(g['earned'] for g in groups), 6),
                  'groups': groups, 'cases': self.cases, 'runtime_issues': self.infrastructure,
                  'formal_platform_t1': False, 'model_calls': 0}
        shutil.copytree(self.private, self.output / 'runtime', dirs_exist_ok=False)
        (self.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        self.diagnostics.close(status, result['reward'], len(self.cases))
        print(json.dumps({k: v for k, v in result.items() if k not in ('cases', 'runtime_issues')}, ensure_ascii=False), flush=True)
        return result

def decoded(result):
    try:
        return json.loads(result['stdout'])
    except Exception:
        return None

def success(result):
    return result['returncode'] == 0 and not result['timed_out']

def failure(result, code):
    return result['returncode'] == code and not result['stdout'] and bool(result['stderr'].strip())
