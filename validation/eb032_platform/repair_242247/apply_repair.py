"""Apply the task-242247 repair with a reversible backup and bounded paths."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def target_path(root, relative):
    path = root / relative
    assert path.resolve().is_relative_to(root), 'path leaves project: ' + relative
    assert not path.is_symlink(), 'linked target: ' + relative
    if path.exists():
        assert path.is_file() and path.stat().st_nlink == 1, 'unexpected target node: ' + relative
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--payload-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.project.resolve()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / 'repair_manifest.json').read_bytes())
    assert (root / '.git').exists(), 'select the platform Git project directory'
    assert sha((root / 'tests/cases032.json').read_bytes().replace(b'\r\n',b'\n')) == manifest['unchanged_cases_sha256'], 'different mathematical task data'
    operations = []
    for item in manifest['changes']:
        relative = item['path']
        path = target_path(root, relative)
        old = path.read_bytes() if path.exists() else None
        if old is None and item.get('optional_when_missing'):
            continue
        new = None if item['status'] == 'D' else (args.payload_root.resolve() / relative).read_bytes()
        if new is not None:
            assert sha(new) == item['after_sha256'], 'repair payload changed: ' + relative
        if old == new:
            continue
        if item['status'] != 'D' and old is not None:
            assert sha(old.replace(b'\r\n', b'\n')) in item['accepted_before_sha256'], 'review a conflicting edited file: ' + relative
        if item['status'] != 'D' and old is None and item['before_sha256'] is not None:
            if relative == '.gitattributes':
                alias = target_path(root, 'gitattributes.txt')
                assert alias.exists() and sha(alias.read_bytes().replace(b'\r\n', b'\n')) in item['accepted_before_sha256'], 'unexpected attributes content'
            else:
                raise AssertionError('required original file absent: ' + relative)
        operations.append((relative, old, new, item['executable']))
    alias = target_path(root, 'gitattributes.txt')
    if alias.exists():
        operations.append(('gitattributes.txt', alias.read_bytes(), None, False))
    if args.check:
        print(json.dumps(dict(status='CHECK_PASS', task=manifest['task'], changes=len(operations)), ensure_ascii=False))
        return
    if not operations:
        print('ALREADY_APPLIED')
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = root.parent / ('eb032-242247-backup-' + stamp + '.zip')
    with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as z:
        state = []
        for relative, old, new, executable in operations:
            state.append(dict(path=relative, existed=old is not None,
                              sha256=sha(old) if old is not None else None))
            if old is not None:
                z.writestr('original/' + relative, old)
        z.writestr('backup_manifest.json', json.dumps(state, ensure_ascii=False, indent=2))
    applied = []
    try:
        for relative, old, new, executable in operations:
            path = target_path(root, relative)
            applied.append((path, old))
            if new is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + '.242247-' + stamp)
                with temporary.open('xb') as handle:
                    handle.write(new)
                os.replace(temporary, path)
                if executable:
                    path.chmod(0o755)
        subprocess.run([sys.executable,'-B',str(root / 'validation/eb032_platform/preflight.py')], check=True)
        token = 'MATH' + '-M'
        for path in root.rglob('*'):
            if '.git' in path.relative_to(root).parts or not path.is_file() or path.is_symlink():
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeError:
                continue
            assert token not in text, 'legacy identity remains: ' + str(path.relative_to(root))
    except BaseException:
        for path, old in reversed(applied):
            if old is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(old)
        raise
    paths = [relative for relative, old, new, executable in operations]
    tracked = set(subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0'))
    stage = [relative for relative in paths if (root / relative).exists() or relative in tracked]
    with tempfile.NamedTemporaryFile(prefix='eb032-stage-', delete=False) as handle:
        handle.write(b'\0'.join(relative.encode() for relative in stage) + b'\0')
        pathspec = Path(handle.name)
    try:
        subprocess.run(['git','-C',str(root),'add','-A',
                        '--pathspec-from-file='+str(pathspec),'--pathspec-file-nul'], check=True)
    finally:
        pathspec.unlink()
    print(json.dumps(dict(status='APPLIED_AND_STAGED', task=manifest['task'],
                         backup=str(backup), changed_files=len(operations)), ensure_ascii=False))


if __name__ == '__main__':
    main()
