"""Check committed files and identity, not a candidate publication solution."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

HEX=re.compile(r'[a-f0-9]{64}\Z')
FILES=('release.jsonl','original.jsonl')

class InvalidSnapshot(ValueError):
    pass

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise InvalidSnapshot('duplicate JSON key')
        result[key]=value
    return result

def decode(raw):
    return json.loads(raw,object_pairs_hook=unique_object)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def input_id(value):
    assert isinstance(value,dict) and set(value)=={'sources','samples'}
    assert isinstance(value['sources'],list) and isinstance(value['samples'],list)
    assert value['sources'] and value['samples']
    sources=[]
    for source in value['sources']:
        assert isinstance(source,dict) and set(source)=={'source','sha256'}
        assert isinstance(source['source'],str) and source['source']
        assert isinstance(source['sha256'],str) and HEX.fullmatch(source['sha256'])
        sources.append(source['source'])
    assert len(set(sources))==len(sources)
    assert all(isinstance(sample,str) and sample for sample in value['samples'])
    assert len(set(value['samples']))==len(value['samples'])
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return sha(raw)

def current(store):
    path=Path(store)/'CURRENT'
    if not path.exists():return None
    if path.is_symlink() or not path.is_file():raise InvalidSnapshot('CURRENT must be regular')
    raw=path.read_bytes()
    if len(raw)!=65 or raw[-1:]!=b'\n':raise InvalidSnapshot('CURRENT representation')
    try:value=raw[:-1].decode('ascii')
    except UnicodeError as error:raise InvalidSnapshot('CURRENT encoding') from error
    if not HEX.fullmatch(value):raise InvalidSnapshot('CURRENT identity')
    return value

def regular_bytes(directory,name):
    """Read candidate-owned files without following links or blocking on FIFOs."""
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise InvalidSnapshot('artifact must be regular')
        with os.fdopen(fd,'rb') as stream:
            fd=None
            return stream.read()
    finally:
        if fd is not None:os.close(fd)


def load_directory(root,generation,expected_input=None):
    """Validate a complete snapshot independently of its internal staging name."""
    if not isinstance(generation,str) or not HEX.fullmatch(generation):
        raise InvalidSnapshot('bad generation')
    directory=None
    try:
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        raw_manifest=regular_bytes(directory,'manifest.json')
        manifest=decode(raw_manifest)
        if manifest['generation']!=generation or input_id(manifest['input'])!=generation:
            raise InvalidSnapshot('input identity differs')
        if expected_input is not None and manifest['input']!=expected_input:
            raise InvalidSnapshot('wrong input')
        if set(manifest['files'])!=set(FILES):raise InvalidSnapshot('file set')
        rows={};payload={}
        for name in FILES:
            metadata=manifest['files'][name]
            raw=regular_bytes(directory,name);payload[name]=raw
            if metadata['sha256']!=sha(raw):raise InvalidSnapshot('wrong file digest')
            lines=raw.splitlines()
            if any(not line.strip() for line in lines):raise InvalidSnapshot('blank JSON line')
            rows[name]=[decode(line) for line in lines]
            if type(metadata['rows']) is not int or metadata['rows']!=len(lines):
                raise InvalidSnapshot('wrong line count')
        return {'generation':generation,'manifest':manifest,'rows':rows,
                'bytes':{**payload,'manifest.json':raw_manifest}}
    except (AssertionError,KeyError,TypeError,ValueError,UnicodeError) as error:
        if isinstance(error,InvalidSnapshot):raise
        raise InvalidSnapshot('invalid snapshot metadata or JSON') from error
    except OSError as error:
        raise InvalidSnapshot('incomplete or nonregular snapshot') from error
    finally:
        if directory is not None:os.close(directory)


def load_generation(store,generation,expected_input=None):
    # The committed layout is still fixed by the public reader contract.
    if not isinstance(generation,str) or not HEX.fullmatch(generation):
        raise InvalidSnapshot('bad generation')
    return load_directory(Path(store)/'generations'/generation,generation,expected_input)


def prepared_snapshots(store,generation,expected_input=None):
    """Find complete staged snapshots; do not prescribe a private directory name.

    Only used at the small PREPARED checkpoint, before releasing the candidate's
    gate. Symlink directories are not descended and special files are rejected.
    A self-consistent manifest is not sufficient: the caller checks source facts.
    """
    root=Path(store)
    if root.is_symlink() or not root.is_dir():return
    for directory,children,files in os.walk(root,followlinks=False):
        children[:]=[name for name in children if not (Path(directory)/name).is_symlink()]
        if 'manifest.json' not in files:continue
        try:yield load_directory(directory,generation,expected_input)
        except InvalidSnapshot:continue

def load_current(store,expected_input=None):
    generation=current(store)
    if generation is None:raise InvalidSnapshot('no committed generation')
    return load_generation(store,generation,expected_input)

def preserved(before,after):
    return (before['generation']==after['generation'] and before['bytes']==after['bytes'])

def bounded_shape(first_kib,second_kib):
    """Affine bound calibrated by finite correct and linear-space witnesses."""
    if type(first_kib) is not int or type(second_kib) is not int:return False
    if first_kib<0 or second_kib<0:return False
    return second_kib<=196608 and first_kib<=196608 and second_kib<=first_kib*1.25+16384
