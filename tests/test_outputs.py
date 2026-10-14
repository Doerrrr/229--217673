"""Harbor adapter; the frozen 33 business checks and weights remain unchanged."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from evaluate import Native, evaluate
from resource_cases import resource_checks

def demote():
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)

out = Path('/logs/verifier')
project = Path('/work/cohort-release')
os.chmod('/tests', 0o700)
os.chmod(out, 0o700)
guard = subprocess.run(['python3', '-c', "import os; assert not os.access('/tests',os.R_OK); assert not os.access('/logs/verifier',os.W_OK)"],
                       capture_output=True, preexec_fn=demote)
assert guard.returncode == 0
for path in (project, *project.rglob('*')):
    assert not path.is_symlink(), 'native project must contain regular files'
    os.chown(path, 10001, 10001)
build = subprocess.run(['make', '-B'], cwd=project, capture_output=True, timeout=180, preexec_fn=demote)
(out / 'build.stdout').write_bytes(build.stdout)
(out / 'build.stderr').write_bytes(build.stderr)
assert build.returncode == 0, 'candidate native build failed'
binary = project / 'cohort-release'
assert binary.is_file() and binary.read_bytes()[:4] == b'\x7fELF'
runner = out / 'rss-runner'
compiled = subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '/tests/rss_runner.c', '-o', runner], capture_output=True, timeout=30)
assert compiled.returncode == 0
with tempfile.TemporaryDirectory(prefix='ddi018-platform-') as temporary:
    root = Path(temporary)
    root.chmod(0o755)
    result = evaluate(Native(str(binary), '/work/bcftools-1.20/bcftools', root, str(runner), out), resource_checks)
result.update(native_build='PASS', private_guard='PASS', platform_version='v02')
(out / 'checks.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
if result['execution_status'] != 'NORMAL':
    raise RuntimeError('candidate runtime did not complete normally; inspect checks.json')
(out / 'reward.txt').write_text(f"{result['reward']:.6f}\n", encoding='ascii')
print(json.dumps({k: result[k] for k in ('execution_status', 'reward', 'platform_version')}), flush=True)
