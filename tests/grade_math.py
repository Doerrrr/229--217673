"""Private finite-instance evaluator. Public mathematical contract is authoritative."""
import argparse
import copy
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import json
from pathlib import Path
import re
from common import Runner, success

WEIGHTS={28:{'classification':.30,'interior':.20,'critical':.25,'cancellation':.20,'failure':.05},
         29:{'interior':.15,'boundary':.25,'degenerate':.25,'near_critical':.25,'failure':.10},
         30:{'small_global':.25,'overlap':.35,'hypergraph':.25,'accounting':.10,'failure':.05}}
COMMANDS={28:'oscillatory-integral',29:'quadratic-minimum',30:'phase-repair'}
DECIMAL=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')

def dec(value):
    if not isinstance(value,str) or len(value)>4096 or not DECIMAL.fullmatch(value):raise ValueError('finite decimal string required')
    z=Decimal(value)
    if not z.is_finite() or (z and abs(z.adjusted())>10000):raise ValueError('invalid number')
    return z

def fracdec(value):
    f=Fraction(value)
    return Decimal(f.numerator)/Decimal(f.denominator)

def correct(number,case,row):
    try:
        q=case['query']
        if not isinstance(row,dict) or row.get('id')!=q['id']:return False, 'id or object'
        if number==28:
            if set(row)!={'id','state','value'}:return False,'schema'
            expected=case['answer']
            if row['state']!=expected['state']:return False,{'expected_state':expected['state'],'actual':row['state']}
            if row['state']=='DIVERGENT':return row['value'] is None,'ordinary improper integral, not regularized value'
            v=dec(row['value']);want=dec(expected['value'])
            if case['group']=='classification':return (v==0 if row['state']=='ZERO' else True),'classification'
            tolerance=Decimal('1e-10')*abs(want)+Decimal('1e-35')
            return abs(v-want)<=tolerance,{'error':str(abs(v-want)),'tolerance':str(tolerance)}
        if number==29:
            if set(row)!={'id','point','value'} or not isinstance(row['point'],list) or len(row['point'])!=len(q['linear']):return False,'schema'
            x=[dec(z) for z in row['point']];r=fracdec(q['radius'])
            c=[fracdec(z) for z in q['linear']];Q=[[fracdec(z) for z in line] for line in q['matrix']]
            f=sum((x[i]*sum((Q[i][j]*x[j] for j in range(len(x))),Decimal(0)))/2+c[i]*x[i] for i in range(len(x)))
            S=r*r*sum(abs(z) for line in Q for z in line)+2*r*sum(abs(z) for z in c)
            if not S:S=Decimal(1)
            tol=Decimal('1e-10')*S;opt=fracdec(case['optimum'])
            norm=sum(z*z for z in x);feasible=norm<=r*r*(1+Decimal('1e-10'))
            okay=feasible and abs(f-opt)<=tol and abs(dec(row['value'])-f)<=tol
            return okay,{'feasible':feasible,'actual_objective':str(f),'optimality_gap':str(f-opt),'tolerance':str(tol)}
        if set(row)!={'id','assignment','dropped','cost'}:return False,'schema'
        bits=row['assignment'];drop=row['dropped'];cost=row['cost']
        if not isinstance(bits,dict) or set(bits)!=set(q['markers']) or any(type(z)is not int or z not in (0,1) for z in bits.values()):return False,'assignment'
        if any(bits[k]!=v for k,v in q['pins'].items()):return False,'pinned assignment'
        want=[];total=0
        for e in q['evidence']:
            p=0
            for term in e['terms']:p^=bits[term]
            if p!=e['parity']:want.append(e['id']);total+=e['cost']
        want.sort()
        okay=drop==want and type(cost)is int and cost==total and total==case['certificate']['lower_bound']
        return okay,{'actual_cost':total,'certified_optimum':case['certificate']['lower_bound'],'dropped_exact':drop==want}
    except (ArithmeticError,ValueError,TypeError,KeyError,OverflowError):
        return False,'malformed or nonfinite candidate result'

def invalid_inputs(number,first):
    base={'version':1,'queries':[first]}
    rows=[]
    def add(name,value):rows.append((name,json.dumps(value).encode()))
    add('boolean-version',{**base,'version':True})
    add('unknown-top-key',{**base,'extra':0})
    add('empty-queries',{'version':1,'queries':[]})
    add('duplicate-query-id',{'version':1,'queries':[first,first]})
    q=copy.deepcopy(first);q['unknown']=2;add('unknown-query-key',{'version':1,'queries':[first,q]})
    q=copy.deepcopy(first);del q[next(k for k in q if k!='id')];add('missing-field',{'version':1,'queries':[first,q]})
    rows.extend([('bad-json',b'{'),('duplicate-json-key',b'{"version":1,"version":1,"queries":[]}'),('nonfinite-json',b'{"version":NaN,"queries":[]}')])
    if number==28:
        for key,value in [('a',True),('b','0'),('s','4.0001'),('damping','-1'),('a','0.0000000000001'),('s','NaN')]:
            q=copy.deepcopy(first);q[key]=value;add(f'bad-{key}-{value}',{'version':1,'queries':[first,q]})
    elif number==29:
        for name,key,value in [('non-symmetric','matrix',[['1','2'],['3','1']]),('wrong-dimension','linear',['0']),('zero-radius','radius','0'),('bool-coefficient','radius',True),('zero-denominator','radius','1/0')]:
            q=copy.deepcopy(first);q[key]=value;add(name,{'version':1,'queries':[first,q]})
    else:
        for name in ['unknown-term','bool-parity','zero-cost','bad-pin','duplicate-evidence']:
            q=copy.deepcopy(first)
            if not q['evidence']:raise AssertionError('first needs evidence')
            if name=='unknown-term':q['evidence'][0]['terms']=['unknown_marker']
            if name=='bool-parity':q['evidence'][0]['parity']=True
            if name=='zero-cost':q['evidence'][0]['cost']=0
            if name=='bad-pin':q['pins']={'unknown_marker':0}
            if name=='duplicate-evidence':q['evidence'].append(copy.deepcopy(q['evidence'][0]))
            add(name,{'version':1,'queries':[first,q]})
    # Give invalid rows unique IDs to ensure failure is not merely duplicate-id detection.
    fixed=[]
    for name,raw in rows:
        if name not in ('duplicate-query-id','duplicate-json-key','bad-json','nonfinite-json'):
            obj=json.loads(raw)
            if isinstance(obj.get('queries'),list) and len(obj['queries'])>1:
                obj['queries'][1]['id']='invalid_second'
            raw=json.dumps(obj).encode()
        fixed.append((name,raw))
    return fixed

def main(number):
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--results',required=True);args=parser.parse_args()
    cases=json.loads(Path(__file__).with_name(f'cases{number:03d}.json').read_bytes())
    runner=Runner(args.project,COMMANDS[number],args.results)
    wire=b'\xef\xbb\xbf'+json.dumps({'version':1,'queries':[c['query'] for c in cases]}).encode()
    source=runner.file('valid.json',wire)
    output=runner.home/'not-yet-created'/'nested'/'result.jsonl'
    assert not output.parent.exists()
    got=runner.call(['--input',source,'--output',output])
    if got['returncode'] in (125,126,127):
        runner.infrastructure.append({'launch_failure':got['returncode'],'stderr':got['stderr'].decode(errors='replace')})
    parsed=[];shape=False
    try:
        parsed=[json.loads(line) for line in output.read_bytes().splitlines()]
        shape=len(parsed)==len(cases)
    except (OSError,ValueError):pass
    with localcontext() as ctx:
        ctx.prec=160
        for i,case in enumerate(cases):
            passed,evidence=correct(number,case,parsed[i]) if shape else (False,'output absent, malformed or wrong row count')
            runner.check(case['group'],case['query']['id'],success(got) and not got['stdout'] and passed,evidence)
    # Keep mathematical points independent of sentinel/fatal-path points.
    for name,raw in invalid_inputs(number,cases[0]['query']):
        bad=runner.file('bad.json',raw);old=runner.file('old.jsonl',b'old-output\x00sentinel\n')
        r=runner.call(['--input',bad,'--output',old])
        runner.check('failure',name,r['returncode']!=0 and bool(r['stderr'].strip()) and not r['stdout'] and old.read_bytes()==b'old-output\x00sentinel\n')
    for name,argv in [('missing-input',['--output',str(runner.home/'cli.jsonl')]),('missing-output',['--input',str(source)]),('no-args',[]),('unreadable',['--input',str(runner.home/'not-a-file.json'),'--output',str(runner.home/'cli.jsonl')])]:
        old=runner.file('cli.jsonl',b'CLI_SENTINEL')
        r=runner.call(argv)
        runner.check('failure',name,r['returncode']!=0 and bool(r['stderr'].strip()) and not r['stdout'] and old.read_bytes()==b'CLI_SENTINEL')
    runner.save(f'DDI-{number:03d}',WEIGHTS[number])

