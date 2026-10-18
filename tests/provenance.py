"""Attach root-owned, actually observed verifier inputs and source digests."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attach(results):
    results = Path(results)
    source = Path(__file__).resolve().parent
    hashes = {p.name: digest(p) for p in source.glob('*.py') if p.is_file()}
    hashes['cases032.json'] = digest(source / 'cases032.json')
    inputs = []
    for path in sorted((results / 'runtime').glob('*.json')):
        row = json.loads(path.read_bytes())
        inputs.append(dict(call=path.stem, input_sha256=row.get('input_sha256'),
                           returncode=row['returncode'], timed_out=row['timed_out']))
    path = results / 'result.json'
    record = json.loads(path.read_bytes())
    record['verification_provenance'] = dict(schema_version=1, source_files_sha256=hashes,
        source_digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        inputs=inputs, source_commit=None,
        commit_binding='Use the CI receipt and identical source digest; the container does not invent an unavailable platform Git SHA')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    os.replace(temporary,path)
    return record['verification_provenance']


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--results',required=True)
    attach(parser.parse_args().results)
