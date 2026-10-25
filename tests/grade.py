"""Private production grader: fixtures and exact comparison, no reference imports."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from common import Runner, success
from output_reader import rows_from

RAT=re.compile(r'[+-]?[0-9]+(?:/[0-9]+)?\Z',re.ASCII)

def same(got,want):
    if isinstance(want,str) and RAT.fullmatch(want):
        return isinstance(got,str) and len(got)<=100000 and bool(RAT.fullmatch(got)) and ('/' not in got or int(got.split('/')[1])>0) and Fraction(got)==Fraction(want)
    if type(got) is not type(want):return False
    if isinstance(want,dict):return set(got)==set(want) and all(same(got[k],v) for k,v in want.items())
    if isinstance(want,list):return len(got)==len(want) and all(same(a,b) for a,b in zip(got,want))
    return got==want

def result_row(rows,q):
    if len(rows)!=1:return None
    row=rows[0]
    if not isinstance(row,dict) or set(row)!={'id','state','result'} or row['id']!=q['id'] or row['state'] not in ('SOLVED','PARTIAL'):return None
    return row['result']

def projection(result,field):
    if field in ('bands_area','bands_moments'):
        bands=result['bands']
        if not isinstance(bands,list):return None
        names=('winding','area') if field=='bands_area' else ('winding','mx','my','mxx','mxy','myy')
        if any(not isinstance(b,dict) or set(b)!={'winding','area','mx','my','mxx','mxy','myy'} for b in bands):return None
        return [{n:b[n] for n in names} for b in bands]
    return result[field]

def accepts(q,got,want,field):
    if field.startswith('word_'):
        from group_word_checker import checks
        return checks(q,got)[field[len('word_'):]]
    if field.startswith('logic_'):
        from logic_checker import checks
        return checks(q,got)[field[len('logic_'):]]
    if field.startswith('latin_'):
        from latin_checker import checks
        return checks(q,got)[field[len('latin_'):]]
    if field=='tensor_factor':
        from tensor_checker import check
        return check(q,got)
    if field.startswith('h_'):
        from topology_checker import checks
        return checks(q,got,want)[field[2:]]
    if field.startswith('g_'):
        from graph_checker import checks
        return checks(q,got,want)[field[2:]]
    return same(projection(got,field),projection(want,field))

def evaluate(project,output):
    fixture=json.loads(Path(__file__).with_name('fixtures.json').read_bytes())
    r=Runner(project,'analyze',output)
    aborted=False
    for i,c in enumerate(fixture['cases']):
        source=r.file('q'+str(i)+'.json',(b'\xef\xbb\xbf' if i%2==0 else b'')+json.dumps(dict(version=1,queries=[c['query']])).encode())
        dst=r.home/f'new{i}/nested/output.jsonl'
        call=r.call(['--input',source,'--output',dst])
        rows=rows_from(dst)
        got=result_row(rows,c['query'])
        okay=success(call) and not call['stdout'] and isinstance(got,dict) and set(got)==set(c['expected'])
        if b'Traceback (most recent call last)' in call['stderr']:
            r.infrastructure.append(dict(candidate_crash=True,call=i))
        if r.infrastructure:aborted=True
        for group,fields in fixture['projections'].items():
            if fixture.get('case_groups',{}).get(c['query']['id'],group)!=group:continue
            passed=okay and all(accepts(c['query'],got,c['expected'],field) for field in fields)
            r.check(group,c['query']['id'],passed,dict(fields=fields,ordinary_exit=call['returncode']))
        if aborted:break
    # All planned but unexecuted mathematical checks remain visibly NOT_RUN.
    if aborted:
        completed={(c['group'],c['name']) for c in r.cases}
        for c in fixture['cases']:
            for group in fixture['projections']:
                if fixture.get('case_groups',{}).get(c['query']['id'],group)!=group:continue
                if (group,c['query']['id']) not in completed:
                    r.check(group,c['query']['id'],False,'not run after runtime failure')
                    r.cases[-1]['status']='NOT_RUN'
        for name in ['batch-order']+[x['name'] for x in fixture['invalids']]+['missing-input','missing-output','no-args','missing-file','output-write-failure']:
            r.check('engineering',name,False,'not run after runtime failure')
            r.cases[-1]['status']='NOT_RUN'
    else:
        qs=[c['query'] for c in fixture['cases'][:2]]
        source=r.file('batch.json',json.dumps(dict(version=1,queries=qs)).encode())
        dst=r.home/'batch/result.jsonl'
        call=r.call(['--input',source,'--output',dst]);rows=rows_from(dst)
        batch=success(call) and not call['stdout'] and len(rows)==2
        if batch:
            for row,c in zip(rows,fixture['cases'][:2]):
                batch=batch and isinstance(row,dict) and set(row)=={'id','state','result'} and row['id']==c['query']['id'] and row['state'] in ('SOLVED','PARTIAL') and isinstance(row['result'],dict) and set(row['result'])==set(c['expected']) and all(accepts(c['query'],row['result'],c['expected'],field) for fields in fixture['projections'].values() for field in fields)
        r.check('engineering','batch-order',batch)
        for item in fixture['invalids']:
            source=r.file('bad.json',item['wire'].encode())
            old=r.file('old-output.jsonl',b'OLD\x00SENTINEL\n')
            call=r.call(['--input',source,'--output',old])
            r.check('engineering',item['name'],call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and old.read_bytes()==b'OLD\x00SENTINEL\n')
        for name,args in [('missing-input',['--output',str(r.home/'cli.jsonl')]),('missing-output',['--input',str(source)]),('no-args',[]),('missing-file',['--input',str(r.home/'absent.json'),'--output',str(r.home/'cli.jsonl')])]:
            old=r.file('cli.jsonl',b'CLI_SENTINEL');call=r.call(args)
            r.check('engineering',name,call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and old.read_bytes()==b'CLI_SENTINEL')
        source=r.file('write-valid.json',json.dumps(dict(version=1,queries=[fixture['cases'][0]['query']])).encode())
        blocker=r.file('plain-file',b'UNCHANGED')
        call=r.call(['--input',source,'--output',str(blocker/'child.jsonl')])
        r.check('engineering','output-write-failure',call['returncode']!=0 and not call['stdout'] and bool(call['stderr'].strip()) and blocker.read_bytes()==b'UNCHANGED')
    result=r.save(fixture['task'],fixture['weights'])
    result['version']=fixture.get('version','v01')
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir() if p.is_file()}
    result['verification_provenance']=dict(source_files_sha256=sources,case_count=len(fixture['cases']),reference_imported=False)
    (Path(output)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['execution_status']=='NORMAL':
        (Path(output).parent/'reward.txt').write_text(str(result['reward'])+'\n')
    else:
        raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--results',required=True);a=p.parse_args()
    evaluate(a.project,a.results)
