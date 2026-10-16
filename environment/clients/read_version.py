"""Public consumer: pin once, validate the envelope, then read a chosen view."""
from pathlib import Path
import argparse
import hashlib
import json

def pin(store,generation='CURRENT'):
    if generation=='CURRENT':
        pointer=json.loads((store/'CURRENT').read_bytes());generation=pointer['generation'];expected=pointer['manifest_sha256']
    else:expected=None
    folder=store/'generations'/generation;raw=(folder/'manifest.json').read_bytes()
    if expected is not None:assert hashlib.sha256(raw).hexdigest()==expected
    manifest=json.loads(raw);assert manifest['generation']==generation
    for name,identity in manifest['files'].items():
        h=hashlib.sha256();size=0
        with (folder/name).open('rb') as stream:
            while block:=stream.read(1024*1024):h.update(block);size+=len(block)
        assert dict(sha256=h.hexdigest(),bytes=size)==identity
    return folder,manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('store',type=Path);p.add_argument('--generation',default='CURRENT');p.add_argument('--view',choices=['decision','calls','facts','provenance'],default='decision');a=p.parse_args();folder,m=pin(a.store,a.generation)
    path=folder/(a.view+('.json' if a.view=='decision' else '.jsonl'))
    with path.open('rb') as stream:
        for line in stream:print(json.dumps(json.loads(line),ensure_ascii=False))
