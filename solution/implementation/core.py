"""Reference I/O and structural validation; not included in the candidate packet."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from phase_codec import canonical, digest

IDENT=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
HASH=re.compile(r'[0-9a-f]{64}\Z')

class Failure(Exception):
    def __init__(self,code,message):self.code=code;super().__init__(message)

def require(test,message,code=4):
    if not test:raise Failure(code,message)

def pairs(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out

def forbidden_number(value):raise ValueError('non-integer JSON number')

def loads(raw,code=4):
    try:return json.loads(raw,object_pairs_hook=pairs,parse_float=forbidden_number,parse_constant=forbidden_number)
    except (ValueError,UnicodeError) as e:raise Failure(code,'invalid JSON: '+str(e)) from e

def read_json(path,code=5):
    try:return loads(Path(path).read_bytes(),code)
    except OSError as e:raise Failure(code,'cannot read object: '+str(path)) from e

def keys(obj,expected,code=4):require(type(obj)is dict and set(obj)==set(expected),'wrong object fields',code)
def integer(n,lo=0,hi=2**63-1):return type(n)is int and lo<=n<=hi
def identifier(s):return type(s)is str and IDENT.fullmatch(s) is not None
def generation(s):return s=='NONE' or type(s)is str and HASH.fullmatch(s) is not None

def hash_file(path):
    h=hashlib.sha256();size=0
    with open(path,'rb') as f:
        while block:=f.read(1024*1024):h.update(block);size+=len(block)
    return dict(sha256=h.hexdigest(),bytes=size)

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def atomic_bytes(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(name,path);sync_dir(path.parent)
    finally:
        if os.path.exists(name):os.unlink(name)

def save(path,value):atomic_bytes(path,canonical(value)+b'\n')

@contextmanager
def lock(path,blocking=True):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a+b') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as e:raise Failure(7,'ticket is already in use') from e
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def wait_gate(path,receipt):
    if not path:return
    path=Path(path);path.mkdir(parents=True,exist_ok=True);save(path/'ready',receipt)
    start=time.monotonic()
    while not (path/'go').exists():
        if time.monotonic()-start>300:raise Failure(8,'gate timeout')
        time.sleep(.02)

def manifest_input(path):
    obj=read_json(path,2);keys(obj,('version','batch_id','variables','source'),2)
    require(type(obj['version'])is int and obj['version']==1 and identifier(obj['batch_id']),'invalid batch header',2)
    vs=obj['variables'];require(type(vs)is list and len(vs)<=128 and all(identifier(v) for v in vs) and len(set(vs))==len(vs),'invalid variables',2)
    src=obj['source'];keys(src,('path','bytes','sha256'),2)
    require(type(src['path'])is str and bool(src['path']) and integer(src['bytes'],1,2**30) and type(src['sha256'])is str and HASH.fullmatch(src['sha256']),'invalid source identity',2)
    source=Path(src['path']);source=source if source.is_absolute() else Path(path).resolve().parent/source
    inp=dict(batch_id=obj['batch_id'],variables=sorted(vs),source=dict(bytes=src['bytes'],sha256=src['sha256']))
    return inp,source

def validate_record(kind,r,known):
    if kind=='QUOTA':keys(r,('max_drops',));require(integer(r['max_drops'],0,2000000),'invalid source quota');return
    require(type(r)is dict and identifier(r.get('source')),'invalid logical source')
    if kind=='EVIDENCE':
        typ=r.get('type');require(typ in ('XOR','FORBID'),'unknown evidence type')
        keys(r,('source','protected','cost','type','vars','bit' if typ=='XOR' else 'bits'))
        vs=r['vars'];require(type(vs)is list and len(vs)<=8 and all(identifier(v) and v in known for v in vs),'invalid evidence variables')
        require(type(r['protected'])is bool and integer(r['cost'],0 if r['protected'] else 1) and (not r['protected'] or r['cost']==0),'invalid evidence cost')
        if typ=='XOR':require(integer(r['bit'],0,1),'invalid XOR bit')
        else:require(type(r['bits'])is list and len(r['bits'])==len(vs) and all(integer(b,0,1) for b in r['bits']),'invalid forbidden bits')
    else:
        keys(r,('source','sample','chrom','position','block','gt'))
        require(identifier(r['sample']) and identifier(r['chrom']) and integer(r['position'],1) and identifier(r['block']) and r['block'] in known and r['gt'] in ('0|0','0|1','1|0','1|1','.|.'),'invalid observation')
