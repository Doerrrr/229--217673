"""Private judging harness. Never copied to public projects."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

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
        parts = Path(name).parts
        fd = self._input_parent(parts)
        os.close(fd)
        return self.home / name

    def _input_parent(self, parts):
        if any(p in ('', '.', '..') for p in parts) or any('/' in p for p in parts):
            raise ValueError('invalid author input path')
        fd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.chown(part, 10001, 10001, dir_fd=fd, follow_symlinks=False)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def file(self, name, raw):
        parts = Path(name).parts
        if not parts or Path(name).is_absolute():
            raise ValueError('invalid author input path')
        fd = self._input_parent(parts[:-1])
        temporary = '.author-input-' + uuid.uuid4().hex
        try:
            target = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(target, 'wb') as handle:
                handle.write(raw)
                os.fchown(handle.fileno(), 10001, 10001)
            os.replace(temporary, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)
        return self.home / name

    def start(self, args, absolute=False):
        self.number += 1
        stem = self.private / f'{self.number:04d}'
        stdout, stderr = str(stem) + '.stdout', str(stem) + '.stderr'
        cmd = list(map(str, args)) if absolute else self.command + list(map(str, args))
        input_sha256 = None
        input_read_error = None
        if '--input' in cmd:
            try:
                input_path = Path(cmd[cmd.index('--input') + 1])
                input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
            except (OSError, IndexError) as error:
                input_read_error = str(error)
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('measure.py')),
            'publish', '300', stdout, stderr, str(self.home), str(self.project), *cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        job = {'process': process, 'stdout': stdout, 'stderr': stderr, 'command': cmd, 'stem': stem, 'input_sha256': input_sha256, 'input_read_error': input_read_error}
        self.jobs.append(job)
        return job

    def finish(self, job, expected_kill=False):
        if 'result' in job:
            value = dict(job['result'])
            value['stdout'] = Path(job['stdout']).read_bytes()
            value['stderr'] = Path(job['stderr']).read_bytes()
            return value
        raw, diagnostics = job['process'].communicate(timeout=315)
        try:
            records = [json.loads(line) for line in raw.splitlines()]
            value = records[-1]
            if job['process'].returncode != 0 or 'peak_rss_kib' not in value:
                raise ValueError('measurement failed')
        except Exception:
            self.infrastructure.append({'command': job['command'], 'error': diagnostics.decode(errors='replace')})
            detail = dict(call=job['stem'].name, input_sha256=job['input_sha256'],
                          measure_exit=job['process'].returncode,
                          stderr_tail=diagnostics[-1200:].decode(errors='replace'))
            raise RuntimeError('VERIFIER_MEASUREMENT_ERROR ' + json.dumps(detail, ensure_ascii=True))
        value['stdout'] = Path(job['stdout']).read_bytes()
        value['stderr'] = Path(job['stderr']).read_bytes()
        log = {k: v for k, v in value.items() if k not in ('stdout', 'stderr')}
        log.update(command=job['command'], expected_kill=expected_kill, input_sha256=job['input_sha256'], input_read_error=job['input_read_error'])
        Path(str(job['stem']) + '.json').write_text(json.dumps(log, indent=2))
        if value.get('log_limit_exceeded', False) or ((value['timed_out'] or value['returncode'] < 0) and not expected_kill):
            self.infrastructure.append({'candidate_runtime': log})
        # Retain metadata, not every call's potentially large diagnostic bytes.
        # Repeated finish() calls rehydrate the same root-owned capture files.
        job['result'] = {k: v for k, v in value.items() if k not in ('stdout', 'stderr')}
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

    def save(self, task, weights, all_required=()):
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
