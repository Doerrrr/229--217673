"""Alternative SAT search over generated graph embeddings, not fixtures."""
import json,sys,time
from itertools import combinations
from pysat.card import CardEnc,EncType
from pysat.formula import IDPool
from pysat.solvers import Solver
from graphs import paley,adjacency,find_clique,structural

def construct(q,seconds):
    n=q['n'];deadline=time.monotonic()+seconds
    candidates=list(range(n,104))
    if not q['cuts'] and all(lo==0 and hi==n-1 for lo,hi in q['degrees']):candidates.reverse()
    for p in candidates:
        if p%4!=1 or any(p%d==0 for d in range(2,int(p**.5)+1)):continue
        rows=paley(p)
        if find_clique(adjacency(rows,1),q['red_forbid']) is not None or find_clique(adjacency(rows,0),q['blue_forbid']) is not None:continue
        degree=(p-1)//2
        if p==n and any(not lo<=degree<=hi for lo,hi in q['degrees']):continue
        residues={a*a%p for a in range(1,p)};pool=IDPool();clauses=[]
        neighbors=[[] for _ in range(p)]
        fixed={tuple(sorted((u,v))):c for u,v,c in q['fixed']}
        for (u,v),c in fixed.items():neighbors[u].append((v,c));neighbors[v].append((u,c))
        root=max(range(n),key=lambda u:len(neighbors[u]));anchor={root:0}
        if neighbors[root]:
            v,c=max(neighbors[root],key=lambda item:len(neighbors[item[0]]));anchor[v]=1 if c else next(a for a in range(1,p) if a not in residues)
        domains=[set(range(p)) for _ in range(p)]
        for u,a in anchor.items():domains[u]={a}
        for u in range(p):
            if u not in anchor:domains[u]-=set(anchor.values())
        for u,a in anchor.items():
            for v,c in neighbors[u]:domains[v]&={b for b in range(p) if b!=a and int((a-b)%p in residues)==c}
        if any(not d for d in domains):continue
        variables={(u,a):pool.id(('label',u,a)) for u in range(p) for a in sorted(domains[u])}
        def card(lits,lo,hi):
            if lo>hi or lo>len(lits) or hi<0:clauses.append([]);return
            lo=max(0,lo);hi=min(len(lits),hi)
            if lo==hi:
                clauses.extend(CardEnc.equals(lits,lo,vpool=pool,encoding=EncType.cardnetwrk).clauses)
            else:
                if lo:clauses.extend(CardEnc.atleast(lits,lo,vpool=pool,encoding=EncType.cardnetwrk).clauses)
                if hi<len(lits):clauses.extend(CardEnc.atmost(lits,hi,vpool=pool,encoding=EncType.cardnetwrk).clauses)
        for u in range(p):clauses.extend(CardEnc.equals([variables[u,a] for a in domains[u]],1,vpool=pool,encoding=EncType.seqcounter).clauses)
        for a in range(p):clauses.extend(CardEnc.atmost([variables[u,a] for u in range(p) if a in domains[u]],1,vpool=pool,encoding=EncType.seqcounter).clauses)
        for u,v,c in q['fixed']:
            for source,target in ((u,v),(v,u)):
                for a in domains[source]:
                    clauses.append([-variables[source,a]]+[variables[target,b] for b in domains[target] if b!=a and int((a-b)%p in residues)==c])
        colors={}
        def edge(u,v):
            key=tuple(sorted((u,v)))
            if key in colors:return colors[key]
            y=pool.id(('edge',*key));colors[key]=y
            if key in fixed:clauses.append([y if fixed[key] else -y]);return y
            # One row of a conditional support relation per source label.
            # The column's one-hot constraint supplies the exact other label.
            for a in domains[u]:
                red=[variables[v,b] for b in domains[v] if b!=a and (a-b)%p in residues]
                blue=[variables[v,b] for b in domains[v] if b!=a and (a-b)%p not in residues]
                clauses.append([-variables[u,a],-y,*red]);clauses.append([-variables[u,a],y,*blue])
            return y
        if p>n:
            for u,(lo,hi) in enumerate(q['degrees']):
                low=degree-hi;high=degree-lo
                if low<=0 and high>=p-n:continue
                card([edge(u,v) for v in range(n,p)],low,high)
        for cut in q['cuts']:card([edge(u,v) for u in cut['left'] for v in cut['right']],cut['min'],cut['max'])
        # Omitted vertices are interchangeable. Sorting their field labels
        # removes this symmetry without restricting any observed graph.
        for u in range(n,p-1):
            for a in domains[u]:clauses.append([-variables[u,a]]+[variables[u+1,b] for b in domains[u+1] if b>a])
        with Solver(name='cadical195',bootstrap_with=clauses) as solver:
            if not solver.solve():continue
            positive={a for a in solver.get_model() if a>0}
        labels=[next(a for a in domains[u] if variables[u,a] in positive) for u in range(n)]
        result=[''.join('.' if u==v else str(int((labels[u]-labels[v])%p in residues)) for v in range(n)) for u in range(n)]
        if structural(q,dict(id=q['id'],state='COMPLETE',rows=result))[0]:return result
        if time.monotonic()>=deadline:break
    return None

if __name__=='__main__':
    request=json.load(sys.stdin);rows=construct(request['query'],request['seconds'])
    if rows:
        print('\n'.join(rows));raise SystemExit(0)
    raise SystemExit(1)
