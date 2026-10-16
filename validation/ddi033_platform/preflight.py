"""Read-only platform payload, candidate/hidden boundary and identity preflight."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    payload = json.loads((ROOT / 'validation/ddi033_platform/payload.json').read_bytes())
    for name, expected in payload['files'].items():
        assert sha(ROOT / name) == expected, 'payload changed: ' + name
    visible = [p for d in ('app', 'bin', 'packet', 'clients', 'lib') for p in (ROOT / 'environment' / d).rglob('*') if p.is_file()]
    hidden = [p for d in ('solution', 'tests') for p in (ROOT / d).rglob('*') if p.is_file()]
    hashes = {sha(p) for p in hidden}
    assert all(sha(p) not in hashes for p in visible), 'full-file candidate/hidden duplicate'
    assert not (ROOT / 'reference_project').exists()
    for directory in ('environment', 'tests', 'solution'):
        for path in (ROOT / directory).rglob('*.py'):
            tree = ast.parse(path.read_bytes())
            if directory == 'tests':
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        assert node.func.attr not in ('setgroups', 'setuid', 'setgid'), 'dynamic identity operation'
                        if node.func.attr == 'chown':
                            assert all(isinstance(a, ast.Constant) and type(a.value) is int and 0 <= a.value <= 65535 for a in node.args[1:3])
    independent = ast.parse((ROOT / 'tests/business_check.py').read_bytes())
    for node in ast.walk(independent):
        if isinstance(node, ast.ImportFrom): assert node.module != 'phase_codec'
        if isinstance(node, ast.Import): assert all(a.name != 'phase_codec' for a in node.names)
    docker = (ROOT / 'environment/Dockerfile').read_text()
    assert 'COPY solution' not in docker and 'COPY tests' not in docker
    assert 'allow_internet = true' in (ROOT / 'task.toml').read_text()
    assert not (ROOT / 'solution/phase-lab').exists(), 'duplicate reference launcher'
    print(json.dumps(dict(status='PASS', checked_files=len(payload['files']), visible_files=len(visible), hidden_files=len(hidden), exact_hidden_duplicates=0, fixed_uid_gid=10001)))

if __name__ == '__main__': main()
