"""Record actual Harbor control results and the final execution-file digest."""
from pathlib import Path
import argparse
import hashlib
import json


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    controls = []
    for name, expected in (('oracle', 1.0), ('nop', 0.0)):
        folder = root/'.trials/ddi008-platform'/name/name
        result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
        details = json.loads((folder/'verifier/details.json').read_text(encoding='utf-8'))
        assert result['exception_info'] is None and result['verifier_result']['rewards']['reward'] == expected
        assert len(details['checks']) == 20 and details['reward'] == expected
        assert sum(c['weight'] for c in details['checks'] if c['passed']) == expected or abs(sum(c['weight'] for c in details['checks'] if c['passed'])-expected)<1e-9
        controls.append({'name': name, 'trial_id': result['id'], 'reward': expected,
                         'passed_checks': sum(c['passed'] for c in details['checks']),
                         'total_checks': 20, 'exception': None,
                         'harbor_task_checksum': result['task_checksum'],
                         'result_sha256': sha(folder/'result.json'),
                         'details_sha256': sha(folder/'verifier/details.json')})
    execution = ['task.toml','instruction.md','solution/solve.sh','solution/oracle_lineage.py']
    execution += [p.relative_to(root).as_posix() for area in ('environment','tests')
                  for p in sorted((root/area).rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    hashes = {name: sha(root/name) for name in sorted(execution)}
    receipt = {'client_date':'2026-10-13','harbor_version':'0.5.0','docker_context':'desktop-linux',
               'controls':controls,'execution_files':hashes,
               'execution_digest':hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
               'public_rules_changed':False,'weights_changed':False,'model_calls':0,
               'formal_platform_validated':False,'github_actions_validated':False,
               'checksum_note':'First local controls differ in full task checksum because README was updated; execution files and frozen tests were unchanged. Final committed validation is recorded separately.'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:
        json.dump(receipt,f,ensure_ascii=False,indent=2); f.write('\n')
    print(json.dumps({'out':str(a.out),'oracle':1.0,'nop':0.0,'execution_digest':receipt['execution_digest']}))


if __name__ == '__main__':
    main()
