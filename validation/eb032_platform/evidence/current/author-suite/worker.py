"""Production local test.sh control. Run only inside the frozen Linux image."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('oracle','nop'),required=True);mode=parser.parse_args().mode
    began=time.monotonic();os.chmod('/root',0o700);os.chmod('/logs',0o700)
    expected=dict(numpy='2.2.6',scipy='1.15.3',sympy='1.13.3',cvxpy='1.7.2',scs='3.2.8',clarabel='0.11.1',ortools='9.14.6206')
    actual={k:importlib.metadata.version(k) for k in expected}
    assert actual==expected and sys.version_info[:3]==(3,11,17)
    assert Path('/sys/fs/cgroup/cpu.max').read_text().split()==['200000','100000']
    assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='2147483648'
    shutil.copytree('/root/repo/tests','/tests');os.chmod('/tests',0o700)
    project=Path('/work/certificate')
    if project.exists():
        assert str(project.resolve())=='/work/certificate' and not project.is_symlink()
        backup=Path('/root/image_initial_project');assert not backup.exists()
        shutil.copytree(project,backup);shutil.rmtree(project)
    os.chdir('/root')
    source=Path('/root/repo/environment')
    shutil.copytree(source,project,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (project/'bin/certified-minimum').chmod(0o755)
    if mode=='oracle':
        shutil.copytree('/root/repo/solution','/solution')
        subprocess.run(['bash','/solution/solve.sh'],check=True)
    os.chdir(project)
    got=subprocess.run(['bash','/tests/test.sh'],capture_output=True,timeout=17950)
    results=Path('/logs/verifier')
    (results/'test-stdout.txt').write_bytes(got.stdout);(results/'test-stderr.txt').write_bytes(got.stderr)
    receipt=dict(mode=mode,actual_test_sh=True,test_exit=got.returncode,seconds=time.monotonic()-began,packages=actual,formal_platform_t1=False,new_model_calls=0)
    path=results/'eb032_math_k/result.json'
    if path.exists():
        grade=json.loads(path.read_bytes());measurements=[json.loads(p.read_bytes()) for p in (results/'eb032_math_k/runtime').glob('*.json')]
        receipt.update(execution_status=grade['execution_status'],reward=grade['reward'],checks=len(grade['cases']),groups=grade['groups'],
                       measured_calls=len(measurements),candidate_seconds=sum(r.get('elapsed_seconds',0) for r in measurements),peak_rss_kib=max((r.get('peak_rss_kib',0) for r in measurements),default=0))
    if path.exists() and mode == 'oracle':
        sys.path.insert(0, '/tests')
        from algebra import check
        singular = []
        cases = json.loads(Path('/tests/cases032.json').read_bytes())
        target = results / 'singular-answers'
        target.mkdir()
        for index, case in enumerate(cases, 1):
            if case['group'] != 'singular_proof':
                continue
            measured = json.loads((results / 'eb032_math_k/runtime' / f'{index:04d}.json').read_bytes())
            command = measured['command']
            answer_path = Path(command[command.index('--output') + 1])
            assert answer_path.is_file() and not answer_path.is_symlink()
            raw = answer_path.read_bytes()
            answer = json.loads(raw)
            point, proof, evidence = check(case['query'], answer, case['optimum'])
            (target / (case['query']['id'] + '.jsonl')).write_bytes(raw)
            singular.append(dict(id=case['query']['id'], state=answer['state'],
                                 point=point, proof=proof, seconds=measured['elapsed_seconds'],
                                 evidence=evidence))
        receipt['singular'] = singular
    receipt['task']=grade.get('task') if path.exists() else None
    (results/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    raise SystemExit(got.returncode)

if __name__=='__main__':main()
