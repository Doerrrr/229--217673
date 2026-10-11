"""Author-side immutable assets, independent model boundary and weight preflight."""
import ast
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--platform',action='store_true',help='Platform workflow is guarded by Git, not personal workflow hash')
args=parser.parse_args()
PROTECTED={
    'environment/data/drug_list.csv':'9678f897dabe1641e3934a8cd79971c386e2bd17fdff9952af15db6a9a5d932f',
    'environment/data/DDI_event.csv':'f7bdb8290a8733a783f4a269f1f32ae2f302d41504098120b9dc61345ae19802',
    'environment/data/newddi.csv':'3e5613f00e241ff79bafe83199347bad56e9d9e6beec0a1c60e73c72c2adcf68',
    '.github/workflows/harbor-validation.yml':'da628e5289907fc57baac03618158602ee8017e775b1f5cc1068c74b662b1156',
}
for name,want in PROTECTED.items():
    if args.platform and name.startswith('.github/'):
        continue
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==want, f'protected asset changed: {name}'
for name in ('molecules.csv','positives.csv'):
    current=json.loads((ROOT/'tests/full_snapshot.json').read_text())['files'][name]
    prior=json.loads((ROOT/'validation/v3_full_snapshot.json').read_text())['files'][name]
    assert current==prior, f'unchanged publication hash changed: {name}'
for path in ROOT.rglob('*.py'):
    if '.trials' in path.parts or '__pycache__' in path.parts:
        continue
    tree=ast.parse(path.read_text(encoding='utf-8'))
    if path.parent.name == 'tests':
        for node in ast.walk(tree):
            names=[node.module or ''] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
            assert not any(n.startswith(('oracle_release','screen_optimizer','solution')) for n in names), 'verifier imports reference'
assert not (ROOT/'solution/ddi-release').exists(), 'duplicate hidden launcher returned'
tree=ast.parse((ROOT/'tests/test_outputs.py').read_text(encoding='utf-8'))
checks=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CHECKS' for t in n.targets))
weights=[n.elts[1].value for n in checks.elts]
assert len(weights)==15 and math.isclose(sum(weights),1), 'check count/weight drift'
assert [round(sum(weights[a:b]),2) for a,b in [(0,4),(4,7),(7,9),(9,11),(11,13),(13,15)]]==[.35,.20,.15,.10,.10,.10]
print(json.dumps({'protected_assets':3 if args.platform else 4,'stable_csv_hashes':2,'verifier_reference_imports':0,
                  'python_syntax':'PASS','checks':15,'business_weights':'UNCHANGED'}))
