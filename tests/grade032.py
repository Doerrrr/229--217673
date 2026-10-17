"""Private exact proof-carrying optimization evaluator."""
import argparse
import copy
import json
from pathlib import Path
from common import Runner,success
from algebra import check

WEIGHTS={'witness':.30,'quadratic_proof':.15,'quartic_proof':.20,'singular_proof':.25,'failure':.10}

def invalids(first):
    base=dict(version=1,queries=[first]);result=[]
    def add(name,obj):result.append((name,json.dumps(obj).encode()))
    add('bool-version',{**base,'version':True});add('extra-top',{**base,'extra':0})
    add('no-query',dict(version=1,queries=[]));add('duplicate-id',dict(version=1,queries=[first,first]))
    variants=[('n-bool','n',True),('n-range','n',33),('no-constant','basis',[[0],[1]]),('duplicate-basis','basis',[[],[0],[1],[0]]),('basis-missing-var','basis',[[],[0]]),('basis-unsorted','basis',[[],[0],[1],[1,0]]),('empty-terms','terms',[]),('zero-coefficient','terms',[dict(vars=[],coef='0')]),('decimal','terms',[dict(vars=[],coef='0.5')]),('bool-coefficient','terms',[dict(vars=[],coef=True)]),('zero-denominator','terms',[dict(vars=[],coef='1/0')]),('duplicate-term','terms',[dict(vars=[],coef='1'),dict(vars=[],coef='2')]),('out-of-range','terms',[dict(vars=[2],coef='1')]),('duplicate-var','terms',[dict(vars=[0,0],coef='1')]),('huge-coefficient','terms',[dict(vars=[],coef='1000000000001')])]
    for name,key,val in variants:
        q=copy.deepcopy(first);q['id']='bad_second';q[key]=val
        add(name,dict(version=1,queries=[first,q]))
    q=copy.deepcopy(first);q['id']='bad_second';q['extra']=1;add('extra-query',dict(version=1,queries=[first,q]))
    q=copy.deepcopy(first);del q['basis'];add('missing-field',dict(version=1,queries=[q]))
    result.extend([('truncated',b'{'),('duplicate-key',b'{"version":1,"version":1,"queries":[]}'),('nonfinite',b'{"version":NaN,"queries":[]}')])
    return result

def rows_from(path):
    try:return [json.loads(line) for line in path.read_bytes().splitlines()]
    except (OSError,ValueError):return []

def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--results',required=True);a=p.parse_args()
    cases=json.loads(Path(__file__).with_name('cases032.json').read_bytes());r=Runner(a.project,'certified-minimum',a.results)
    for i,c in enumerate(cases):
        wire=json.dumps(dict(version=1,queries=[c['query']])).encode();wire=(b'\xef\xbb\xbf'+wire) if i%2==0 else wire
        source=r.file(f'q{i}.json',wire);out=r.home/f'not-existing{i}/nested/result.jsonl'
        got=r.call(['--input',source,'--output',out]);rows=rows_from(out)
        if got['returncode'] in (125,126,127):r.infrastructure.append(dict(launch_failure=got['returncode']))
        point,proof,why=check(c['query'],rows[0],c['optimum']) if len(rows)==1 else (False,False,'absent/malformed/wrong row count')
        okay=success(got) and not got['stdout']
        r.check('witness',c['query']['id']+'-point',okay and point,why)
        r.check(c['group'],c['query']['id']+'-proof',okay and proof,why)
        if r.infrastructure:
            for rest in cases[i+1:]:
                r.check('witness',rest['query']['id']+'-point',False,'not run after runtime failure');r.check(rest['group'],rest['query']['id']+'-proof',False,'not run after runtime failure')
            break
    source=r.file('multi.json',json.dumps(dict(version=1,queries=[c['query'] for c in cases[:2]])).encode());out=r.home/'multi/result.jsonl'
    got=r.call(['--input',source,'--output',out]);rows=rows_from(out)
    results=[check(c['query'],row,c['optimum']) for c,row in zip(cases[:2],rows)] if len(rows)==2 else []
    r.check('witness','multi-point-order',success(got) and not got['stdout'] and len(results)==2 and all(z[0] for z in results))
    r.check('quadratic_proof','multi-proof-order',success(got) and not got['stdout'] and len(results)==2 and all(z[1] for z in results))
    for name,wire in invalids(cases[0]['query']):
        source_bad=r.file('bad.json',wire);old=r.file('old.jsonl',b'OLD\x00SENTINEL\n');got=r.call(['--input',source_bad,'--output',old])
        r.check('failure',name,got['returncode']!=0 and not got['stdout'] and bool(got['stderr'].strip()) and old.read_bytes()==b'OLD\x00SENTINEL\n')
    for name,args in [('missing-input',['--output',str(r.home/'cli.jsonl')]),('missing-output',['--input',str(source)]),('no-args',[]),('missing-file',['--input',str(r.home/'missing.json'),'--output',str(r.home/'cli.jsonl')])]:
        old=r.file('cli.jsonl',b'CLI_SENTINEL');got=r.call(args)
        r.check('failure',name,got['returncode']!=0 and not got['stdout'] and bool(got['stderr'].strip()) and old.read_bytes()==b'CLI_SENTINEL')
    r.save('EB-032-MATH-M',WEIGHTS)

if __name__=='__main__':main()
