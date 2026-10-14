"""Author-side boundary/integrity check, independent of candidate scoring."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FROZEN = {
    'fixtures.py': 'bdc9ba1251c7637e9018acca0079e959d0039f6539b8ee0481366f99ce6a229d',
    'observations.py': '68552ffad78d07388b31abc512b09a5fba0f050d27004b8dbae46dec6c053397',
    'business_checks.py': 'ec38ae5b7cd1038af16641fb608c572dbd3ba793b763fc3a7615d02f46f44730',
    'evaluate.py': '90d7666c204228c4be565e2b738b9fb5a7943c816916c2a93bbbaf1bca8ae31d',
    'resource_cases.py': 'a0214b26fe4323d830ca38f847b4414365eb1441e97edb80e6b77662fcedf86b',
}
PUBLIC = {
    'environment/packet/lab/exchange.md': '0f9cb4f8fe9774ac61be98fdaa0d497d784d8b37c9eaaf89e636c9ef1b0ab079',
    'environment/packet/readme.md': '99c1b78d86597400eb7816bac87bec138a33a6954f8077260ba7e8348ad7e52d',
    'environment/packet/clients/consume.py': '25b465c8c25db7188adc84cd47f5f0608bde6221fa4e101d737c6f948a3cd196',
    'environment/Makefile': '0b8f37862fe8220743eb0a87f36761f79c743984e5bfc0f6de7a64b6d60ebdfe',
    'environment/upstream/bcftools-1.20.tar.bz2': '312b8329de5130dd3a37678c712951e61e5771557c7129a70a327a300fda8620',
}

def digest(path):
    data = path.read_bytes()
    if path.suffix in {'.py', '.c', '.md'} or path.name == 'Makefile':
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()

def main():
    for name, wanted in FROZEN.items():
        assert digest(ROOT / 'tests' / name) == wanted, f'frozen check changed: {name}'
    runner=(ROOT/'tests/rss_runner.c').read_text(encoding='utf-8')
    assert 'strcmp(argv[4], "10001")' in runner
    assert 'setgid(10001)' in runner and 'setuid(10001)' in runner
    assert 'setgroups(0, NULL)' in runner
    assert 'setgid(uid)' not in runner and 'setuid(uid)' not in runner
    for name, wanted in PUBLIC.items():
        assert digest(ROOT / name) == wanted, f'public obligation/dependency changed: {name}'
    copied = [ROOT/'environment/Makefile']
    for directory in ('src', 'packet', 'upstream'):
        copied.extend(p for p in (ROOT/'environment'/directory).rglob('*') if p.is_file())
    hidden = [p for directory in ('tests', 'solution') for p in (ROOT/directory).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    pairs = [(str(a.relative_to(ROOT)), str(b.relative_to(ROOT)))
             for a in copied for b in hidden if digest(a) == digest(b)]
    assert not pairs, f'hidden complete file duplicated into candidate image: {pairs}'
    for path in ROOT.rglob('*.py'):
        if '.trials' not in path.parts:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    task = (ROOT/'task.toml').read_text(encoding='utf-8')
    assert re.search(r'^schema_version\s*=\s*"1\.3"\s*$', task, re.M)
    environment = task.split('[environment]', 1)[1].split('\n[', 1)[0]
    assert re.search(r'^allow_internet\s*=\s*true\s*$', environment, re.M)
    provenance = json.loads((ROOT/'validation/cohort_platform/provenance.json').read_text())
    assert provenance['scores_transfer_to_new_starter'] is False
    assert provenance['business_weights_changed'] is False
    assert sum(c['cases'] for c in provenance['business_weights']) == 33
    assert sum(c['weight'] for c in provenance['business_weights']) == 1
    print(json.dumps({'status':'PASS', 'frozen_business_checks':33,
                      'complete_file_duplicates':len(pairs), 'internet_enabled':True,
                      'platform_version':'v03-safety', 'fixed_uid_gid':10001,
                      'historical_scores_transferred':False}))

if __name__ == '__main__':
    main()
