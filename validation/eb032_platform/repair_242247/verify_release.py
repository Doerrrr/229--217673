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
    current = root / 'validation/eb032_platform/evidence/current'
    for profile in ('general-reference', 'general-reference-repeat', 'nop'):
        result = json.loads((current / profile / 'eb032_math_k/result.json').read_bytes())
        reward = result.get('reward')
        valid_reward = isinstance(reward, (int, float))
        if result['execution_status'] != 'NORMAL' or not valid_reward:
            raise ValueError('abnormal control: ' + profile)
        if profile.startswith('general-reference') and reward != 1.0:
            raise ValueError('Oracle must score exactly 1.0')
        if profile == 'nop' and reward > 0.1:
            raise ValueError('NOP exceeds 0.1')
    sys.path.insert(0, str(root / 'tests'))
    from algebra import check
    cases = json.loads((root / 'tests/cases032.json').read_bytes())
    singular = [case for case in cases if case['group'] == 'singular_proof']
    if len(singular) != 6:
        raise ValueError('six singular fixtures required')
    for profile in ('general-reference', 'general-reference-repeat'):
        for case in singular:
            path = current / profile / 'singular-answers' / (case['query']['id'] + '.jsonl')
            answer = json.loads(path.read_bytes())
            point, proof, _ = check(case['query'], answer, case['optimum'])
            if answer['state'] != 'CERTIFIED' or not point or not proof:
                raise ValueError('singular certificate failed: ' + profile + ' ' + case['query']['id'])
    subprocess.run([sys.executable, '-B', str(root / 'validation/eb032_platform/preflight.py')], check=True)
    print(json.dumps(dict(status='RELEASE_CHECK_PASS', task=manifest['task'],
                          version=manifest['version'], files_checked=checked)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
