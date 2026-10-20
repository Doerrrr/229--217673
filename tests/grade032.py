"""Private exact proof-carrying optimization evaluator."""
import argparse
import copy
import json
from pathlib import Path
from common import Runner,success
from guarded_check import check, configure_results, CheckerFailure
from output_reader import rows_from

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

class AbortGrading(Exception):
    def __init__(self, status, phase, detail):
        self.status, self.phase, self.detail = status, phase, detail
        super().__init__(detail)


def planned_checks(cases):
    checks=[]
    for c in cases:
        checks.extend([('witness',c['query']['id']+'-point'),(c['group'],c['query']['id']+'-proof')])
    checks.extend([('witness','multi-point-order'),('quadratic_proof','multi-proof-order')])
    checks.extend(('failure',name) for name,_ in invalids(cases[0]['query']))
    checks.extend(('failure',name) for name in ('missing-input','missing-output','no-args','missing-file'))
    assert len(checks)==len(set(checks))
    return checks


def call(r,args,*,math_launch=False):
    try:
        got=r.call(args)
    except RuntimeError as error:
        # The measurement process has already been waited/reaped by Runner.
        # Unrelated Python errors must not be reclassified as candidate faults.
        if not r.infrastructure:
            raise
        raise AbortGrading('VERIFIER_MEASUREMENT_ERROR','measurement',str(error)) from error
    if math_launch and got['returncode'] in (125,126,127):
        r.infrastructure.append(dict(launch_failure=got['returncode']))
    if r.infrastructure:
        raise AbortGrading('CANDIDATE_RUNTIME_ERROR','candidate','runtime failure confirmed')
    return got


def rows(r,path):
    try:
        return rows_from(path)
    except (OSError,RuntimeError) as error:
        r.infrastructure.append(dict(verifier_failure='output_reader',error=str(error)))
        raise AbortGrading('VERIFIER_OUTPUT_READER_ERROR','output_reader',str(error)) from error


def exact(r,*args):
    try:
        return check(*args)
    except CheckerFailure as error:
        r.infrastructure.append(dict(verifier_failure='exact_checker',error=str(error)))
        raise AbortGrading('VERIFIER_CHECKER_ERROR','exact_checker',str(error)) from error


def evaluate(r,cases):
    for i,c in enumerate(cases):
        wire=json.dumps(dict(version=1,queries=[c['query']])).encode();wire=(b'\xef\xbb\xbf'+wire) if i%2==0 else wire
        source=r.file(f'q{i}.json',wire);out=r.home/f'not-existing{i}/nested/result.jsonl'
        got=call(r,['--input',source,'--output',out],math_launch=True);observed=rows(r,out)
        point,proof,why=exact(r,c['query'],observed[0],c['optimum']) if len(observed)==1 else (False,False,'absent/malformed/wrong row count')
        okay=success(got) and not got['stdout']
        r.check('witness',c['query']['id']+'-point',okay and point,why)
        r.check(c['group'],c['query']['id']+'-proof',okay and proof,why)
    source=r.file('multi.json',json.dumps(dict(version=1,queries=[c['query'] for c in cases[:2]])).encode());out=r.home/'multi/result.jsonl'
    got=call(r,['--input',source,'--output',out]);observed=rows(r,out)
    results=[exact(r,c['query'],row,c['optimum']) for c,row in zip(cases[:2],observed)] if len(observed)==2 else []
    r.check('witness','multi-point-order',success(got) and not got['stdout'] and len(results)==2 and all(z[0] for z in results))
    r.check('quadratic_proof','multi-proof-order',success(got) and not got['stdout'] and len(results)==2 and all(z[1] for z in results))
    for name,wire in invalids(cases[0]['query']):
        source_bad=r.file('bad.json',wire);old=r.file('old.jsonl',b'OLD\x00SENTINEL\n');got=call(r,['--input',source_bad,'--output',old])
        r.check('failure',name,got['returncode']!=0 and not got['stdout'] and bool(got['stderr'].strip()) and old.read_bytes()==b'OLD\x00SENTINEL\n')
    for name,args in [('missing-input',['--output',str(r.home/'cli.jsonl')]),('missing-output',['--input',str(source)]),('no-args',[]),('missing-file',['--input',str(r.home/'missing.json'),'--output',str(r.home/'cli.jsonl')])]:
        old=r.file('cli.jsonl',b'CLI_SENTINEL');got=call(r,args)
        r.check('failure',name,got['returncode']!=0 and not got['stdout'] and bool(got['stderr'].strip()) and old.read_bytes()==b'CLI_SENTINEL')
    return r.save('EB-032-MATH-J',WEIGHTS)


def run(r,cases):
    try:
        return evaluate(r,cases)
    except AbortGrading as error:
        completed={(c['group'],c['name']) for c in r.cases}
        last_check=r.cases[-1]['name'] if r.cases else None
        for group,name in planned_checks(cases):
            if (group,name) not in completed:
                # Retain the old diagnostic text for report_reward consumers,
                # with an explicit status so this is never called an executed failure.
                r.check(group,name,False,'not run after runtime failure')
                r.cases[-1]['status']='NOT_RUN'
                r.cases[-1]['not_run_reason']=error.status
        detail=dict(execution_status=error.status,phase=error.phase,error=error.detail[:2000],
                    last_completed_check=last_check,candidate_calls=r.number,
                    last_completed_instance=next((c['query']['id'] for c in reversed(cases)
                        if (c['group'],c['query']['id']+'-proof') in completed),None),
                    completed_check_count=len(completed),not_run_check_count=len(r.cases)-len(completed),
                    first_runtime_issue=r.infrastructure[0])
        # Saving failures deliberately propagate; never synthesize a reward.
        return r.save('EB-032-MATH-J',WEIGHTS,aborted=detail)


def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--results',required=True);a=p.parse_args()
    configure_results(a.results)
    cases=json.loads(Path(__file__).with_name('cases032.json').read_bytes());r=Runner(a.project,'certified-minimum',a.results)
    run(r,cases)

if __name__=='__main__':main()
