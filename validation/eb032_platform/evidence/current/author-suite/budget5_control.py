"""Five-second CLI counterexamples with the frozen v05 reference."""
from pathlib import Path
import json
import os
import shutil
import sys
import tempfile

os.chmod('/root', 0o700)
repo = Path('/root/repo')
results = Path('/root/results')
results.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo / 'tests'))
sys.path.insert(0, str(repo / 'solution/implementation'))
from common import Runner, success
from algebra import check
from interface import parse_query
import solver

workspace = Path(tempfile.mkdtemp(prefix='certificate-budget5-', dir='/tmp'))
workspace.chmod(0o700)
project = workspace / 'project'
shutil.copytree(repo / 'environment', project, ignore=shutil.ignore_patterns('data', 'Dockerfile', '__pycache__', '*.pyc'))
for path in (repo / 'solution/implementation').glob('*.py'):
    shutil.copyfile(path, project / 'app' / path.name)
path = project / 'app/main.py'
text = path.read_text()
assert 'budget = 260.0 / len(queries)' in text
path.write_text(text.replace('budget = 260.0 / len(queries)', 'budget = 5.0'))
runner = Runner(str(project), 'certified-minimum', str(results))
records = []
for case in json.loads((repo / 'tests/cases032.json').read_bytes()):
    if case['group'] != 'singular_proof':
        continue
    raw = case['query']
    query = parse_query(raw, 0)
    polynomial = {sum(1 << i for i in mono): coefficient for mono, coefficient in query['terms']}
    assignment = solver.optimize(query['n'], polynomial, 5)
    ties = solver.equal_minima(query['n'], polynomial, assignment, 5)
    assert not ties
    source = runner.file(raw['id']+'.json', json.dumps(dict(version=1, queries=[raw])).encode())
    output = runner.home / (raw['id']+'.jsonl')
    measured = runner.call(['--input', source, '--output', output])
    assert success(measured) and not measured['stdout']
    answer = json.loads(output.read_bytes())
    point, proof, evidence = check(raw, answer, case['optimum'])
    assert point and measured['elapsed_seconds'] <= 30
    stderr = measured['stderr'].decode(errors='replace')
    if answer['state'] == 'INCUMBENT':
        assert not proof and 'certificate_incomplete' in stderr
    (results / (raw['id']+'.jsonl')).write_bytes(output.read_bytes())
    (results / (raw['id']+'.stderr')).write_bytes(measured['stderr'])
    record = dict(id=raw['id'], budget_sec=5.0, ties=0, state=answer['state'],
                  elapsed_sec=measured['elapsed_seconds'], point=point, proof=proof,
                  diagnostics_present='certificate_incomplete' in stderr, fault_injection=False)
    records.append(record)
    print(json.dumps(record), flush=True)
assert any(record['state'] == 'INCUMBENT' for record in records)
shutil.copytree(runner.private, results / 'measurements')
(results / 'budget5_summary.json').write_text(json.dumps(dict(status='PASS', records=records), indent=2)+'\n')
