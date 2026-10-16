"""Private independent business oracle. Does not import candidate code or phase_codec."""
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path

def wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(value):return hashlib.sha256(wire(value)).hexdigest()

def condition(record):
    if record['type']=='XOR':
        odd=set()
        for v in record['vars']:
            if v in odd:odd.remove(v)
            else:odd.add(v)
        return {'type':'XOR','vars':sorted(odd),'bit':record['bit']}
    names={}
    for name,bit in zip(record['vars'],record['bits']):
        if name in names and names[name]!=bit:return {'type':'XOR','vars':[],'bit':0}
        names[name]=bit
    if not names:return {'type':'XOR','vars':[],'bit':1}
    order=sorted(names)
    return {'type':'FORBID','vars':order,'bits':[names[v] for v in order]}

def fails(record,point):
    if record['type']=='XOR':return sum(point[v] for v in record['vars'])%2!=record['bit']
    return all(point[v]==b for v,b in zip(record['vars'],record['bits']))

def replay(batches):
    history=[];seen={};disabled=set();variables=set()
    for batch,declared,raw in batches:
        variables.update(declared);ordinal=0
        for line in raw.decode('utf-8-sig').splitlines():
            if not line.strip():continue
            ordinal+=1;event=json.loads(line);identity=(batch,event['seq'])
            if event['op']=='RETRACT':
                target=(event['target']['batch_id'],event['target']['seq'])
                assert target in seen and seen[target]['op']!='RETRACT'
                disabled.add(target)
            history.append((identity,event,ordinal));seen[identity]=event
    active={}
    for (batch,seq),event,ordinal in history:
        if (batch,seq) in disabled or event['op']=='RETRACT':continue
        key=(event['kind'],event['id'])
        if event['op']=='DELETE':active.pop(key,None)
        else:active[key]={'kind':key[0],'id':key[1],'record':event['record'],'origin':{'batch_id':batch,'seq':seq,'ordinal':ordinal}}
    return sorted(variables),[active[k] for k in sorted(active)]

def model(variables,facts):
    collected={};quota={}
    for fact in facts:
        if fact['kind']=='QUOTA':quota[fact['id']]=fact['record']['max_drops']
        if fact['kind']!='EVIDENCE':continue
        r=fact['record'];c=condition(r);key=wire(c)
        if key not in collected:collected[key]={'condition':c,'protected':False,'weight':0,'counts':{}}
        g=collected[key]
        if r['protected']:g['protected']=True
        else:g['weight']+=r['cost'];g['counts'][r['source']]=g['counts'].get(r['source'],0)+1
    return {'version':'phase-cnf-v1','variables':sorted(variables),'groups':[collected[k] for k in sorted(collected)],'quotas':quota}

def point_cost(variables,facts,point):
    if type(point)is not dict or set(point)!=set(variables) or any(type(v)is not int or v not in (0,1) for v in point.values()):return None
    quota={f['id']:f['record']['max_drops'] for f in facts if f['kind']=='QUOTA'};used=Counter();cost=0;dropped=[]
    for f in facts:
        if f['kind']!='EVIDENCE' or not fails(f['record'],point):continue
        r=f['record']
        if r['protected']:return None
        cost+=r['cost'];used[r['source']]+=1;dropped.append(f['id'])
    if any(used[s]>limit for s,limit in quota.items()):return None
    return cost,sorted(dropped),dict(used)

def optimum(variables,facts):
    assert len(variables)<=16,'large instances use independently checked finite certificates'
    best=None
    for bits in itertools.product((0,1),repeat=len(variables)):
        point=dict(zip(variables,bits));result=point_cost(variables,facts,point)
        if result is not None and (best is None or result[0]<best[0]):best=(result[0],point)
    return best

def decision_ok(variables,facts,value,expected='enumerate'):
    assert set(value)=={'status','assignment','dropped','cost'}
    best=optimum(variables,facts) if expected=='enumerate' else expected
    if best is None:
        assert value==dict(status='UNSAT',assignment=None,dropped=None,cost=None);return
    r=point_cost(variables,facts,value['assignment']);assert r is not None
    assert type(value['cost'])is int and r[0]==best[0]==value['cost'] and r[1]==value['dropped']
    assert value['status']==('SAT' if r[0]==0 else 'REPAIRED')

def rows(path):return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]

def check_views(folder,variables,facts,value,gid):
    assert rows(folder/'facts.jsonl')==facts
    expected=[];audit=[]
    for f in facts:
        kind=f['kind'];r=f['record'];status=value['status']
        if kind=='QUOTA':source=f['id'];outcome='POLICY'
        else:
            source=r['source']
            if status=='UNSAT':outcome='UNRESOLVED'
            elif kind=='EVIDENCE':outcome='DROPPED' if fails(r,value['assignment']) else 'KEPT'
            else:
                outcome='PROJECTED';call=dict(r,id=f['id'],origin=f['origin'],generation=gid)
                if value['assignment'][r['block']]:a,b=r['gt'].split('|');call['gt']=b+'|'+a
                expected.append(call)
        audit.append(dict(kind=kind,id=f['id'],origin=f['origin'],source=source,outcome=outcome))
    expected.sort(key=lambda r:(r['chrom'],r['position'],r['sample'],r['id']))
    assert rows(folder/'calls.jsonl')==expected
    assert rows(folder/'provenance.jsonl')==audit
    assert json.loads((folder/'model.json').read_bytes())==model(variables,facts)
