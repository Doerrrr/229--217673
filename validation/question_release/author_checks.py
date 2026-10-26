"""Compatibility entry point for the platform's existing author CI workflow.

Run inside a disposable root Linux container. Does not invoke answer models.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'posix' and os.geteuid() == 0, 'disposable root Linux container required'
    repo = args.repo.resolve()
    results = args.results.resolve()
    fixed = [Path(p) for p in ('/work/bench', '/tests', '/solution', '/logs/verifier')]
    for target in fixed:
        assert not target.is_symlink() and target.resolve() == target
        assert target != repo and target not in repo.parents
        assert target != results and target not in results.parents
    subprocess.run(['python3', str(repo/'validation/question_release/preflight.py')], check=True)
    assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '2147483648'
    assert Path('/sys/fs/cgroup/cpu.max').read_text().split() == ['200000', '100000']
    results.mkdir(parents=True, exist_ok=True)
    records = []
    for mode in ('oracle', 'nop', 'empty-result-schema-fault'):
        for target in fixed:
            if target.exists():
                shutil.rmtree(target)
        project = Path('/work/bench')
        shutil.copytree(repo/'environment', project)
        shutil.copytree(repo/'tests', '/tests')
        (project/'bin/analyze').chmod(0o755)
        if mode != 'nop':
            shutil.copytree(repo/'solution', '/solution')
            subprocess.run(['bash', '/solution/solve.sh'], cwd=project, check=True)
        if mode == 'empty-result-schema-fault':
            (project/'app/main.py').write_text('import sys\nfrom contract import cli\nfrom algorithm import validate\ndef main(): return cli(validate, lambda q: {})\nif __name__ == "__main__": sys.exit(main())\n')
        began = time.monotonic()
        run = subprocess.run(['bash', '/tests/test.sh'], cwd=project, capture_output=True, timeout=17950)
        logs = Path('/logs/verifier')
        (logs/'test-stdout.txt').write_bytes(run.stdout)
        (logs/'test-stderr.txt').write_bytes(run.stderr)
        result = json.loads((logs/'details/result.json').read_bytes())
        receipt = dict(mode=mode, test_exit=run.returncode, seconds=time.monotonic()-began,
                       execution_status=result['execution_status'], reward=result['reward'],
                       groups=result['groups'], actual_production_test_sh=True,
                       formal_platform_t1=False)
        destination = results/mode
        assert not destination.exists(), 'use a fresh results directory'
        shutil.copytree(logs, destination)
        (destination/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        assert run.returncode == 0 and result['execution_status'] == 'NORMAL', receipt
        if mode in ('oracle', 'nop'):
            assert (result['reward'] == 1.0 if mode == 'oracle' else 0 <= result['reward'] <= .1), receipt
        else:
            assert result['reward'] <= .1, receipt
            assert all(g['passed'] == 0 for g in result['groups'] if g['name'] != 'engineering'), receipt
        records.append(receipt)
        print(json.dumps(receipt), flush=True)
    (results/'summary.json').write_text(json.dumps(dict(status='PASS', records=records), indent=2)+'\n')


if __name__ == '__main__':
    main()
