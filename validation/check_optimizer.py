"""500 fixed-seed resource instances checked against exhaustive enumeration."""
import json
import random
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
sys.path.insert(0,str(ROOT/'solution'))
from screen_optimizer import solve_plan
from screen_model import optimize_batch, exhaustive_batch, resource_report

# Hand witness after chemistry: jointly binding quota, stock, cluster and budget.
# The old unrestricted maximum is D,G,F; clipping it can leave D,G (15000),
# whereas joint selection chooses D,UNMATCHED,F (16000) at exactly cost 14.
targets=[('A',0,'P'),('F',1,'P'),('C',1,'P')]
options=[[('D',9000),('E',8000)],[('D',7000),('G',6000)],[('E',7000),('F',7000)]]
meta={d:(('X' if d in 'DE' else 'Y' if d in 'FG' else d),'test',None) for d in 'ACDEFG'}
resources={d:(1,3) for d in meta}
policy=dict(budget=14,assay_cost=1,max_pairs=3,cluster_cap=1,
            event_quotas=[dict(type=0,min=1,max=1),dict(type=1,min=1,max=2)])
truth=([('D',9000),None,('F',7000)],'OPTIMAL')
assert exhaustive_batch(targets,options,meta,resources,policy)==truth
assert solve_plan(targets,options,meta,resources,policy)==truth
assert optimize_batch(targets,options,meta,resources,policy)==truth
assert resource_report(targets,truth[0],meta,resources,policy,truth[1])['total_cost']==14

rng=random.Random(451)
start=time.monotonic()
for index in range(500):
    n=rng.randrange(0,6)
    targets=[(rng.choice('ABCDE'),rng.randrange(2),'P') for _ in range(n)]
    options=[[(c,rng.randrange(1,10)*500) for c in 'ABCDE' if c != targets[i][0] and rng.random()<.4]
             for i in range(n)]
    meta={c:(rng.choice('XYZ'),'test',None) for c in 'ABCDE'}
    resources={c:(rng.randrange(0,4),rng.randrange(0,5)) for c in 'ABCDE'}
    policy=dict(budget=rng.randrange(0,25),assay_cost=rng.randrange(0,3),max_pairs=rng.randrange(0,6),
                cluster_cap=rng.randrange(0,4),event_quotas=[dict(type=0,min=rng.randrange(2),max=3)])
    truth=exhaustive_batch(targets,options,meta,resources,policy)
    assert solve_plan(targets,options,meta,resources,policy)==truth, ('CP-SAT',index,truth)
    assert optimize_batch(targets,options,meta,resources,policy)==truth, ('MILP',index,truth)
print(json.dumps({'instances':500,'oracle_cp_sat':'PASS','verifier_milp':'PASS',
                  'comparison':'exhaustive enumeration','coupled_manual_witness':'PASS',
                  'elapsed_sec':round(time.monotonic()-start,3)}))
