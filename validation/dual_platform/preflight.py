"""Cheap admission checks, not an Oracle/NOP or platform success claim."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
for name in ['instruction.md','task.toml','environment/Dockerfile','solution/solve.sh','tests/test.sh','tests/test_outputs.py']:
    assert (ROOT/name).is_file(),name
task=(ROOT/'task.toml').read_text(encoding='utf-8')
assert 'schema_version = "1.3"' in task and 'allow_internet = true' in task
assert not re.search(r'^\s*(COPY|ADD)\s+.*(?:solution|tests|validation)',(ROOT/'environment/Dockerfile').read_text(),re.M|re.I)
public=[p for p in (ROOT/'environment').rglob('*') if p.is_file()]
hidden=[p for role in ('solution','tests') for p in (ROOT/role).rglob('*') if p.is_file()]
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
duplicates=[(a.relative_to(ROOT).as_posix(),b.relative_to(ROOT).as_posix()) for a in public for b in hidden if digest(a)==digest(b)]
assert not duplicates,duplicates
for path in hidden:
    if path.suffix in ('.py','.c','.h','.sh'):
        raw=path.read_bytes();assert not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw,path
    if path.suffix=='.py':compile(path.read_text(encoding='utf-8'),str(path),'exec')
for name in ('native_process.py','measured_process.c','test_outputs.py'):
    assert not re.search(r'\b(?:setgroups|setuid|setgid)\s*\(',(ROOT/'tests'/name).read_text()),name
assert 'setpriv' in (ROOT/'tests/measured_process.c').read_text()
assert '--reuid=10001' in (ROOT/'tests/measured_process.c').read_text()
provenance=json.loads((ROOT/'validation/dual_platform/provenance.json').read_bytes())
assert provenance['business_checks']==113 and not provenance['historical_scores_transferred']
for name,wanted in provenance['reference_files'].items():assert digest(ROOT/'solution'/name)==wanted,name
protected=['environment/data/drug_list.csv','environment/data/DDI_event.csv','environment/data/newddi.csv']
subprocess.run(['git','-C',str(ROOT),'diff','--exit-code','--',*protected,'.github'],check=True)
print(json.dumps({'schema':'1.3','internet':True,'duplicate_hidden_files':0,'fixed_identity':10001,
                  'reference_provenance':'PASS','checks':113,'historical_scores_transferred':False}))
