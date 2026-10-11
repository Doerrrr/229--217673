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
parser.add_argument('--self-test',action='store_true',help='Check LF/CRLF portability and rejection of content changes')
args=parser.parse_args()
# These are SHA-256 hashes of the immutable Git blobs, not Windows checkout
# bytes. The CSV attributes specify LF; an older Windows checkout can still
# contain CRLF until Git recreates it. Do not parse/reserialize or trim data.
PROTECTED={
    'environment/data/drug_list.csv':'208edfd36b34dc7f2d877f3b86636cff5fc14c11ff5617466b92b2633890a513',
    'environment/data/DDI_event.csv':'3efbd7ade6ef3c6d3e0fb0422653b7689912b5a75316a29d85c8e26072bff311',
    'environment/data/newddi.csv':'673d7ed6a0f3ecfdeaa1df54295f98ddf45266a837f6ec3a6a5f7934710d3b72',
    '.github/workflows/harbor-validation.yml':'da628e5289907fc57baac03618158602ee8017e775b1f5cc1068c74b662b1156',
}


def verify_asset(name, data, expected):
    raw_hash = hashlib.sha256(data).hexdigest()
    # Only Git's CSV line-ending conversion is accepted. The workflow remains
    # an exact byte check, and no original file is rewritten by this preflight.
    canonical = data.replace(b'\r\n', b'\n') if name.endswith('.csv') else data
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != expected:
        raise ValueError(f'protected asset changed: {name}; '
                         f'expected_lf={expected}; actual_lf={actual}; raw={raw_hash}')


if args.self_test:
    count = 0
    for name, expected in PROTECTED.items():
        if not name.endswith('.csv'):
            continue
        canonical = (ROOT/name).read_bytes().replace(b'\r\n', b'\n')
        verify_asset(name, canonical, expected)
        verify_asset(name, canonical.replace(b'\n', b'\r\n'), expected)
        for changed in (b'X' + canonical[1:], canonical + b' ',
                        canonical.replace(b'\n', b'\r')):
            try:
                verify_asset(name, changed, expected)
            except ValueError:
                pass
            else:
                raise AssertionError(f'content change escaped protection: {name}')
        count += 1
    print(json.dumps({'lf_crlf_files': count, 'content_changes': 'REJECTED',
                      'whitespace_changes': 'REJECTED', 'lone_cr': 'REJECTED'}))


for name,want in PROTECTED.items():
    if args.platform and name.startswith('.github/'):
        continue
    verify_asset(name, (ROOT/name).read_bytes(), want)
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
