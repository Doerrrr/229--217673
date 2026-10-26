"""Private fixture comparator. Does not import the reference algorithm."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from common import Runner,success
from output_reader import rows_from

DECIMAL=re.compile(r'[0-9]{1,256}\Z',re.ASCII)

def same(got,want):
    if type(want)is str:return type(got)is str and bool(DECIMAL.fullmatch(got)) and int(got)==int(want)
    if type(got)is not type(want):return False
    if type(want)is dict:return set(got)==set(want) and all(same(got[k],v) for k,v in want.items())
    if type(want)is list:return len(got)==len(want) and all(same(a,b) for a,b in zip(got,want))
    return got==want

def solved(rows,q):
    if len(rows)!=1:return None
    row=rows[0]
    if type(row)is not dict or set(row)!={'id','state','result'} or row['id']!=q['id'] or row['state']!='SOLVED':return None
    return row['result']

def evaluate(project,output):
    fixture=json.loads(Path(__file__).with_name('fixtures.json').read_bytes())
    r=Runner(project,'analyze',output)
    for i,c in enumerate(fixture['cases']):
        src=r.file(f'q{i}.json',(b'\xef\xbb\xbf' if i%2==0 else b'')+json.dumps(dict(version=1,queries=[c['query']])).encode())
        dst=r.home/f'new{i}/nested/output.jsonl'
        call=r.call(['--input',src,'--output',dst])
        got=solved(rows_from(dst),c['query'])
        okay=success(call) and not call['stdout'] and type(got)is dict and set(got)==set(c['expected'])
        if b'Traceback (most recent call last)' in call['stderr']:r.infrastructure.append(dict(candidate_crash=True,call=i))
        for group,fields in fixture['projections'].items():
            r.check(group,c['query']['id'],okay and all(same(got[field],c['expected'][field]) for field in fields),dict(ordinary_exit=call['returncode'],fields=fields))
        if r.infrastructure:
            for remaining in fixture['cases'][i+1:]:
                for group in fixture['projections']:
                    r.check(group,remaining['query']['id'],False,'NOT_RUN after runtime failure')
            r.check('engineering','not-run-after-runtime-failure',False,'NOT_RUN')
            result=r.save(fixture['task'],fixture['weights'])
            (Path(output)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            raise SystemExit(2)
    for index,c in enumerate(fixture['edge_cases']):
        src=r.file(f'edge-{index}.json',json.dumps(dict(version=1,queries=[c['query']])).encode())
        dst=r.home/f'edge-{index}.jsonl';call=r.call(['--input',src,'--output',dst])
        r.check('engineering',c['query']['id'],success(call) and not call['stdout'] and same(solved(rows_from(dst),c['query']),c['expected']))
    qs=[c['query'] for c in fixture['cases'][:2]]
    src=r.file('batch.json',json.dumps(dict(version=1,queries=qs)).encode())
    dst=r.home/'batch/result.jsonl';call=r.call(['--input',src,'--output',dst]);rows=rows_from(dst)
    batch=success(call) and not call['stdout'] and len(rows)==2
    if batch:batch=all(same(solved([row],q),c['expected']) for row,q,c in zip(rows,qs,fixture['cases'][:2]))
    r.check('engineering','batch-order',batch)
    good=fixture['cases'][-1]
    src=r.file('replace-valid.json',json.dumps(dict(version=1,queries=[good['query']])).encode())
    dst=r.file('existing-output.jsonl',b'OLD OUTPUT MUST BE REPLACED\n')
    call=r.call(['--input',src,'--output',dst])
    r.check('engineering','success-replaces-existing-output',success(call) and not call['stdout'] and same(solved(rows_from(dst),good['query']),good['expected']))
    for item in fixture['invalids']:
        src=r.file('bad.json',item['wire'].encode());dst=r.file('sentinel.jsonl',b'OLD\x00OUTPUT\n')
        call=r.call(['--input',src,'--output',dst])
        r.check('engineering',item['name'],call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and dst.read_bytes()==b'OLD\x00OUTPUT\n')
    for name,args in [('missing-input',['--output',str(r.home/'cli.jsonl')]),('missing-output',['--input',str(src)]),('no-args',[]),('missing-file',['--input',str(r.home/'absent.json'),'--output',str(r.home/'cli.jsonl')])]:
        dst=r.file('cli.jsonl',b'CLI SENTINEL');call=r.call(args)
        r.check('engineering',name,call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and dst.read_bytes()==b'CLI SENTINEL')
    src=r.file('write-valid.json',json.dumps(dict(version=1,queries=[good['query']])).encode());block=r.file('plain-file',b'UNCHANGED')
    call=r.call(['--input',src,'--output',str(block/'child.jsonl')])
    r.check('engineering','output-write-failure',call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and block.read_bytes()==b'UNCHANGED')
    result=r.save(fixture['task'],fixture['weights'])
    result['verification_provenance']=dict(source_files_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir() if p.is_file()},reference_imported=False)
    (Path(output)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['execution_status']=='NORMAL':(Path(output).parent/'reward.txt').write_text(str(result['reward'])+'\n')
    else:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--results',required=True);a=p.parse_args();evaluate(a.project,a.results)
