"""Input-driven exact integer optimizer; contains no instances or answer registry."""
import argparse
from collections import Counter
from functools import reduce
from itertools import combinations
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')

def require(condition, message='invalid input'):
    if not condition:
        raise ValueError(message)

def identifier(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None

def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result

def load(path):
    obj = json.loads(Path(path).read_bytes().decode('utf-8-sig'), object_pairs_hook=object_pairs,
                     parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    require(isinstance(obj, dict) and set(obj) == {'version', 'queries'})
    require(type(obj['version']) is int and obj['version'] == 1)
    queries = obj['queries']
    require(isinstance(queries, list) and 1 <= len(queries) <= 128)
    seen = set()
    for q in queries:
        require(isinstance(q, dict) and set(q) == {'id', 'markers', 'evidence', 'pins'})
        require(identifier(q['id']) and q['id'] not in seen); seen.add(q['id'])
        names = q['markers']
        require(isinstance(names, list) and 1 <= len(names) <= 80 and all(identifier(x) for x in names))
        require(len(set(names)) == len(names)); known = set(names)
        require(isinstance(q['pins'], dict) and all(k in known and type(v) is int and v in (0, 1) for k,v in q['pins'].items()))
        require(isinstance(q['evidence'], list) and len(q['evidence']) <= 1200)
        ids = set()
        for e in q['evidence']:
            require(isinstance(e, dict) and set(e) == {'id','terms','parity','cost'})
            require(identifier(e['id']) and e['id'] not in ids); ids.add(e['id'])
            require(isinstance(e['terms'], list) and len(e['terms']) <= 6 and all(isinstance(x,str) and x in known for x in e['terms']))
            require(type(e['parity']) is int and e['parity'] in (0,1))
            require(type(e['cost']) is int and 1 <= e['cost'] <= 10**9)
    return queries

def solve(q):
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix
    names = q['markers']; pins = q['pins']; free = [x for x in names if x not in pins]
    index = {x:i for i,x in enumerate(free)}
    groups = {}
    for e in q['evidence']:
        terms = [x for x,n in Counter(e['terms']).items() if n % 2]
        parity = e['parity']
        for x in terms:
            if x in pins: parity ^= pins[x]
        key = tuple(sorted(index[x] for x in terms if x not in pins))
        group = groups.setdefault(key, [0,0]); group[parity] += e['cost']
    objective = [0.0] * len(free); lower = [0.0] * len(free); upper = [1.0] * len(free)
    rows = []; lows = []; highs = []; pair = {}
    def variable(limit=1):
        n = len(objective); objective.append(0.0); lower.append(0.0); upper.append(float(limit)); return n
    def constraint(coefficients, lo, hi):
        rows.append(coefficients); lows.append(lo); highs.append(hi)
    divisor = reduce(math.gcd, (e['cost'] for e in q['evidence']), 0) or 1
    for terms, weights in groups.items():
        if not terms: continue
        z = terms[0] if len(terms) == 1 else variable()
        objective[z] += (weights[0] - weights[1]) / divisor
        if len(terms) == 2:
            a,b = terms; pair[terms] = z
            constraint({z:1,a:-1,b:-1}, -np.inf, 0)
            constraint({a:1,b:-1,z:-1}, -np.inf, 0)
            constraint({b:1,a:-1,z:-1}, -np.inf, 0)
            constraint({z:1,a:1,b:1}, -np.inf, 2)
        elif len(terms) > 2:
            k = variable(len(terms)//2)
            coefficients = {x:1 for x in terms}; coefficients.update({z:-1,k:-2})
            constraint(coefficients, 0, 0)
    # Valid cut-polytope inequalities, derived from the input graph alone.
    adjacent = {i:set() for i in range(len(free))}
    for a,b in pair: adjacent[a].add(b); adjacent[b].add(a)
    for a,b in pair:
        for c in sorted(adjacent[a] & adjacent[b]):
            if c <= b: continue
            edges = [pair[(a,b)],pair[(a,c)],pair[(b,c)]]
            constraint({x:1 for x in edges}, -np.inf, 2)
            for x in edges: constraint({y:1 if y==x else -1 for y in edges}, -np.inf, 0)
    clique_count = 0
    def cliques(prefix, candidates):
        nonlocal clique_count
        if clique_count >= 20000: return
        if len(prefix) == 5:
            constraint({pair[(a,b)]:1 for a,b in combinations(prefix,2)}, -np.inf, 6)
            clique_count += 1; return
        if len(prefix) + len(candidates) < 5: return
        for pos,v in enumerate(candidates):
            cliques(prefix+[v], [w for w in candidates[pos+1:] if w in adjacent[v]])
            if clique_count >= 20000: return
    cliques([], list(range(len(free))))
    if free:
        # Complement symmetry is valid only when every remaining condition is even.
        if all(len(t)%2==0 for t in groups): upper[0] = 0
        rr=[];cc=[];vv=[]
        for i,row in enumerate(rows):
            for j,value in row.items(): rr.append(i);cc.append(j);vv.append(value)
        matrix=coo_matrix((vv,(rr,cc)),shape=(len(rows),len(objective))).tocsc()
        constraints=LinearConstraint(matrix,np.array(lows),np.array(highs)) if rows else None
        result=milp(np.array(objective),integrality=np.ones(len(objective)),
                    bounds=Bounds(lower,upper),constraints=constraints,
                    options={'mip_rel_gap':0.0,'time_limit':250.0})
        require(result.status==0 and result.x is not None, 'integer optimization did not finish')
        bits={x:int(round(result.x[i])) for x,i in index.items()}
    else: bits={}
    bits.update(pins); dropped=[]; cost=0
    for e in q['evidence']:
        actual=0
        for term in e['terms']: actual ^= bits[term]
        if actual != e['parity']: dropped.append(e['id']); cost += e['cost']
    if free:
        constant=groups.get((),[0,0])[1]+sum(w[1] for terms,w in groups.items() if terms)
        require(abs(result.fun*divisor+constant-cost)<0.1, 'objective reconstruction mismatch')
    return dict(id=q['id'],assignment=bits,dropped=sorted(dropped),cost=cost)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    temporary=None
    try:
        queries=load(a.input); output=[solve(q) for q in queries]
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False) as f:
            temporary=f.name
            for row in output:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
            f.flush();os.fsync(f.fileno())
        os.replace(temporary,target);temporary=None
    except Exception as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
    finally:
        if temporary is not None:Path(temporary).unlink(missing_ok=True)
    return 0

if __name__=='__main__':sys.exit(main())
