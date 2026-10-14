#!/usr/bin/env python3
"""Public receiving client: pin one generation and verify artifact checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

HEX=re.compile(r'[a-f0-9]{64}\Z')

def object_once(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate manifest key')
        result[key]=value
    return result

def read_metadata(store):
    pointer=store/'CURRENT'
    if pointer.is_symlink() or not pointer.is_file():raise ValueError('no regular CURRENT')
    raw=pointer.read_bytes()
    if len(raw)!=65 or raw[-1:]!=b'\n':raise ValueError('invalid CURRENT')
    generation=raw[:-1].decode('ascii')
    if not HEX.fullmatch(generation):raise ValueError('invalid generation')
    return generation

def pinned_files(store,generation):
    folder=store/'generations'/generation
    if folder.is_symlink() or not folder.is_dir():raise ValueError('missing generation')
    manifest_path=folder/'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():raise ValueError('missing manifest')
    manifest=json.loads(manifest_path.read_bytes(),object_pairs_hook=object_once)
    if manifest['generation']!=generation:raise ValueError('mixed generation')
    raw=json.dumps(manifest['input'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if hashlib.sha256(raw).hexdigest()!=generation:raise ValueError('wrong input identifier')
    if set(manifest['files'])!={'release.jsonl','original.jsonl'}:raise ValueError('wrong file list')
    files={}
    for name,metadata in manifest['files'].items():
        path=folder/name
        if path.is_symlink() or not path.is_file():raise ValueError('missing view')
        digest=hashlib.sha256();count=0;last=b''
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                digest.update(chunk);count+=chunk.count(b'\n');last=chunk[-1:]
        if last and last!=b'\n':count+=1
        if type(metadata['rows']) is not int or metadata['rows']!=count:raise ValueError('wrong view length')
        if digest.hexdigest()!=metadata['sha256']:raise ValueError('wrong view digest')
        files[name]=path
    return files

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--view',choices=['release','original'],required=True)
    parser.add_argument('--pin',type=Path)
    args=parser.parse_args()
    generation=read_metadata(args.store)  # Exactly once; later reads stay pinned.
    if args.pin:
        if not args.pin.is_dir():raise ValueError('pin directory must exist')
        marker=args.pin/'ready.tmp'
        marker.write_text(json.dumps({'generation':generation})+'\n',encoding='utf-8')
        marker.replace(args.pin/'ready')
        while not (args.pin/'go').exists():time.sleep(.01)
    files=pinned_files(args.store,generation)
    with files[args.view+'.jsonl'].open('rb') as stream:
        shutil.copyfileobj(stream,sys.stdout.buffer)

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('read-store: '+str(error),file=sys.stderr)
        raise SystemExit(1)
