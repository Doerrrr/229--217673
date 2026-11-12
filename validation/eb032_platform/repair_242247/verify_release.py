"""Verify installed release bytes against the accompanying frozen manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    root = args.project.resolve()
    manifest = json.loads(Path(__file__).with_name('repair_manifest.json').read_bytes())
    errors = []
    checked = 0
    for item in manifest['changes']:
        path = root / item['path']
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            errors.append('UNSAFE_PATH ' + item['path'])
            continue
        if item['status'] == 'D':
            if path.exists():
                errors.append('OLD_FILE_REMAINS ' + item['path'])
            continue
        if not path.exists() and item.get('optional_when_missing'):
            continue
        if not path.is_file():
            errors.append('MISSING ' + item['path'])
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['after_sha256']:
            errors.append('HASH_MISMATCH ' + item['path'])
        checked += 1
    if (root / 'gitattributes.txt').exists():
        errors.append('OLD_FILENAME gitattributes.txt')
    adaptation = json.loads((root / 'validation/eb032_platform/adaptation.json').read_bytes())
    if adaptation['version'] != manifest['version']:
        errors.append('ADAPTATION_VERSION_MISMATCH')
    results = list((root / 'validation/eb032_platform/evidence/current').rglob('result.json'))
    if not results:
        errors.append('CURRENT_RESULTS_MISSING')
    for path in results:
        result = json.loads(path.read_bytes())
        if result['task'] != manifest['task'] or result['version'] != manifest['version']:
            errors.append('RESULT_IDENTITY_MISMATCH ' + str(path.relative_to(root)))
        if len(result['cases']) != manifest['scored_checks']:
            errors.append('RESULT_CHECK_COUNT_MISMATCH ' + str(path.relative_to(root)))
    if errors:
        print('RELEASE_CHECK_FAIL', len(errors))
        print('\n'.join(errors[:30]))
        return 1
    subprocess.run([sys.executable, '-B', str(root / 'validation/eb032_platform/preflight.py')], check=True)
    print(json.dumps(dict(status='RELEASE_CHECK_PASS', task=manifest['task'],
                          version=manifest['version'], files_checked=checked)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
