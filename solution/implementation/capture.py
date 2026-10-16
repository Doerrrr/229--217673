"""Durable byte capture, including non-text and mid-character checkpoints."""
from pathlib import Path
import os
from core import Failure, require, hash_file, save, wait_gate, sync_dir

def receive(session,meta,source,checkpoint=None,checkpoint_gate=None):
    raw=session/'capture.raw';wanted=meta['input']['source'];size=raw.stat().st_size if raw.exists() else 0
    if meta['state']!='CAPTURING':
        try:actual=hash_file(raw)
        except OSError as e:raise Failure(5,'captured source is missing or unreadable') from e
        require(actual==wanted,'captured source was altered',5);return
    # A CAPTURING label only trusts the last fsynced prefix, never the file length alone.
    prefix=meta.get('prefix',dict(bytes=0,sha256=hash_file_empty()))
    require(size>=prefix['bytes'],'capture prefix is missing',5)
    if size!=prefix['bytes']:
        with raw.open('r+b') as f:f.truncate(prefix['bytes']);f.flush();os.fsync(f.fileno())
    if raw.exists():require(hash_file(raw)==prefix,'capture prefix digest mismatch',5)
    size=prefix['bytes'];require(size<=wanted['bytes'],'capture too long',5)
    try:reader=open(source,'rb',buffering=0)
    except OSError as e:raise Failure(3,'cannot open source') from e
    with reader,raw.open('ab',buffering=0) as out:
        while size<wanted['bytes']:
            limit=min(1024*1024,wanted['bytes']-size)
            if checkpoint is not None and size<checkpoint:limit=min(limit,checkpoint-size)
            block=reader.read(limit)
            require(bool(block),'source ended before declared byte length')
            view=memoryview(block)
            while view:
                n=out.write(view)
                if not n:raise Failure(6,'short capture write')
                view=view[n:]
            size+=len(block)
            if checkpoint is not None and size==checkpoint:
                os.fsync(out.fileno());meta['prefix']=hash_file(raw);save(session/'session.json',meta)
                wait_gate(checkpoint_gate,dict(stage='CHECKPOINTED',ticket=meta['ticket'],**meta['prefix']))
                checkpoint=None
        require(not reader.read(1),'source exceeds declared byte length')
        os.fsync(out.fileno())
    sync_dir(session)
    require(hash_file(raw)==wanted,'full source identity mismatch')
    meta['prefix']=wanted;meta['state']='CAPTURED';save(session/'session.json',meta)

def hash_file_empty():
    import hashlib
    return hashlib.sha256(b'').hexdigest()
