"""Private exact finite-graph evaluator. No hidden solution equality."""
import argparse
import copy
import json
from pathlib import Path
from common import Runner, success
from graphs import structural

WEIGHTS={'small':.10,'both_colors':.30,'fixed':.20,'degree_cuts':.30,'failure':.10}

def invalids(first):
    base={'version':1,'queries':[first]};result=[]
    def add(name,obj):result.append((name,json.dumps(obj).encode()))
    add('bool-version',{**base,'version':True})
    add('unknown-top',{**base,'extra':0})
    add('empty-queries',{'version':1,'queries':[]})
    add('repeated-id',{'version':1,'queries':[first,first]})
    mutations=[('n-bool','n',True),('n-range','n',81),('bad-forbid','red_forbid',2),('bad-degrees','degrees',[[0,5]]*5),('duplicate-edge','fixed',[[0,1,0],[0,1,0]]),('edge-order','fixed',[[1,0,1]]),('color-bool','fixed',[[0,1,True]]),('overlap-cut','cuts',[dict(left=[0],right=[0,1],min=0,max=1)]),('duplicate-cut-vertex','cuts',[dict(left=[0,0],right=[1],min=0,max=1)]),('cut-range','cuts',[dict(left=[0],right=[1],min=0,max=2)])]
    for name,key,val in mutations:
        q=copy.deepcopy(first);q['id']='invalid_second';q[key]=val
        add(name,{'version':1,'queries':[first,q]})
    q=copy.deepcopy(first);q['id']='invalid_second';q['extra']=0;add('unknown-query',{'version':1,'queries':[first,q]})
    q=copy.deepcopy(first);del q['cuts'];add('missing-field',{'version':1,'queries':[q]})
    result.extend([('truncated',b'{'),('duplicate-key',b'{"version":1,"version":1,"queries":[]}'),('nonfinite',b'{"version":NaN,"queries":[]}')])
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--results',required=True);a=p.parse_args()
    cases=json.loads(Path(__file__).with_name('cases031.json').read_bytes())
    r=Runner(a.project,'ramsey-complete',a.results)
    for idx,case in enumerate(cases):
        wire=json.dumps({'version':1,'queries':[case['query']]}).encode()
        if idx%2==0:wire=b'\xef\xbb\xbf'+wire
        source=r.file(f'query{idx}.json',wire);out=r.home/f'new{idx}/nested/result.jsonl'
        got=r.call(['--input',source,'--output',out])
        if got['returncode'] in (125,126,127):r.infrastructure.append({'launch_failure':got['returncode']})
        ok=False;why='absent/malformed output or unexpected row count'
        try:
            lines=out.read_bytes().splitlines()
            if len(lines)==1:ok,why=structural(case['query'],json.loads(lines[0]))
        except (OSError,ValueError,TypeError,KeyError):pass
        r.check(case['group'],case['query']['id'],success(got) and not got['stdout'] and ok,why)
        if r.infrastructure:
            # Do not waste 28 * 300 seconds after a runtime failure. No valid score.
            for rest in cases[idx+1:]:r.check(rest['group'],rest['query']['id'],False,'not run after runtime failure')
            break
    # A genuine multi-query call, preserving independent first-group points.
    source_multi=r.file('multi.json',json.dumps({'version':1,'queries':[c['query'] for c in cases[:2]]}).encode())
    out_multi=r.home/'multi/result.jsonl';got=r.call(['--input',source_multi,'--output',out_multi])
    passed=False
    try:
        parsed=[json.loads(line) for line in out_multi.read_bytes().splitlines()]
        passed=len(parsed)==2 and all(structural(c['query'],row)[0] for c,row in zip(cases[:2],parsed))
    except (OSError,ValueError,TypeError,KeyError):pass
    r.check('small','multi-query-order',success(got) and not got['stdout'] and passed)
    first=cases[0]['query']
    for name,raw in invalids(first):
        src=r.file('bad.json',raw);old=r.file('old.jsonl',b'OLD\x00SENTINEL\n')
        got=r.call(['--input',src,'--output',old])
        r.check('failure',name,got['returncode']!=0 and bool(got['stderr'].strip()) and not got['stdout'] and old.read_bytes()==b'OLD\x00SENTINEL\n')
    for name,args in [('missing-input',['--output',str(r.home/'cli.jsonl')]),('missing-output',['--input',str(source)]),('no-args',[]),('unreadable',['--input',str(r.home/'missing'),'--output',str(r.home/'cli.jsonl')])]:
        old=r.file('cli.jsonl',b'CLI_SENTINEL');got=r.call(args)
        r.check('failure',name,got['returncode']!=0 and bool(got['stderr'].strip()) and not got['stdout'] and old.read_bytes()==b'CLI_SENTINEL')
    r.save('DDI-031',WEIGHTS)

if __name__=='__main__':main()
