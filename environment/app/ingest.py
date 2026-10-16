"""Input adapter used by the existing laboratory batch jobs."""
import hashlib
import json
from pathlib import Path

def load_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def load_legacy(path):
    obj=load_json(path)
    if set(obj)!={'version','variables','relations','observations'} or obj['version']!=1:raise ValueError('old batch schema')
    if len(set(obj['variables']))!=len(obj['variables']):raise ValueError('duplicate block')
    return obj
def receive(manifest):
    obj=load_json(manifest);source=Path(obj['source']['path'])
    if not source.is_absolute():source=Path(manifest).resolve().parent/source
    raw=source.read_bytes()
    if len(raw)!=obj['source']['bytes'] or hashlib.sha256(raw).hexdigest()!=obj['source']['sha256']:raise ValueError('source identity')
    return obj,raw

def events(raw):
    result=[];previous=0
    for ordinal,line in enumerate(raw.decode('utf-8-sig').splitlines(),1):
        if not line.strip():continue
        row=json.loads(line)
        if row['seq']<=previous:raise ValueError('sequence order')
        previous=row['seq'];result.append({**row,'ordinal':ordinal})
    return result
