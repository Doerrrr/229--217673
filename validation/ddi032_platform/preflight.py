"""Read-only release boundary and fixed payload validation (Python stdlib only)."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / 'validation/ddi032_platform/payload.json').read_bytes())
    for relative, expected in manifest['files'].items():
        assert digest(ROOT / relative) == expected, 'payload changed: ' + relative
    public = [p for directory in ('app', 'bin', 'packet')
              for p in (ROOT / 'environment' / directory).rglob('*') if p.is_file()]
    hidden = [p for directory in ('solution', 'tests')
              for p in (ROOT / directory).rglob('*') if p.is_file()]
    hidden_hashes = {digest(p): p for p in hidden}
    for path in public:
        assert digest(path) not in hidden_hashes, 'image/hidden full-file duplicate: ' + str(path)
    assert not (ROOT / 'reference_project').exists(), 'author reference project leaked'
    for directory in ('environment/app', 'solution', 'tests'):
        for path in (ROOT / directory).rglob('*.py'):
            ast.parse(path.read_bytes(), filename=str(path))
    docker = (ROOT / 'environment/Dockerfile').read_text()
    copies = [s.strip() for s in docker.splitlines() if s.startswith('COPY ')]
    assert copies == ['COPY app/ app/', 'COPY bin/ bin/', 'COPY packet/ packet/'], copies
    assert 'allow_internet = true' in (ROOT / 'task.toml').read_text()
    assert not any((ROOT / 'solution').glob('certified-minimum')), 'duplicate reference launcher'
    print(json.dumps(dict(status='PASS', payload_files=len(manifest['files']),
                          visible_files=len(public), hidden_files=len(hidden),
                          exact_hidden_duplicates=0, registered_oracle=False)))


if __name__ == '__main__':
    main()
