"""Exhaustive objective checks for both independently implemented optimizers."""
import itertools
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
sys.path.insert(0,str(ROOT/'solution'))
from oracle_release import exact_matching
from release_model import assignment

rng=random.Random(451)
for index in range(500):
    options=[[(c,rng.randint(1500,10000)) for c in 'ABCDE' if rng.random()<.45]
             for _ in range(rng.randint(1,5))]
    best=None
    for values in itertools.product(*[choices+[None] for choices in options]):
        selected=[v[0] for v in values if v]
        if len(selected)!=len(set(selected)):
            continue
        objective=(-len(selected),-sum(v[1] for v in values if v),tuple(v[0] if v else '\uffff' for v in values))
        if best is None or objective<best[0]:
            best=(objective,list(values))
    assert exact_matching(options)==best[1], ('flow',index,options,best)
    assert assignment(options)==best[1], ('assignment',index,options,best)
print(json.dumps({'graphs':500,'oracle_flow':'PASS','verifier_hungarian':'PASS','comparison':'exhaustive enumeration'}))
