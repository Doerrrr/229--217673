"""Incremental SAT for the original graph, with exact forbidden-clique cuts."""
import itertools,json,sys,time
from pysat.card import CardEnc,EncType
from pysat.formula import IDPool
from pysat.solvers import Solver
from graphs import structural

def violations(rows,color,k,limit=5000):
    n=len(rows);adj=[sum(1<<v for v in range(n) if u!=v and rows[u][v]==str(color)) for u in range(n)];found=[]
    def walk(mask,chosen):
        need=k-len(chosen)
        if not need:found.append(chosen);return len(found)>=limit
        while mask.bit_count()>=need:
            bit=mask&-mask;mask-=bit;u=bit.bit_length()-1
            if walk(mask&adj[u],chosen+[u]):return True
        return False
    walk((1<<n)-1,[]);return found

def solve(q,initial,seconds):
    deadline=time.monotonic()+seconds;n=q['n'];pool=IDPool();edges=list(itertools.combinations(range(n),2));variables={e:pool.id(e) for e in edges}
    def v(u,w):return variables[tuple(sorted((u,w)))]
    clauses=[]
    def bounds(lits,lo,hi):
        if lo==hi:clauses.extend(CardEnc.equals(lits,lo,vpool=pool,encoding=EncType.cardnetwrk).clauses)
        else:
            if lo:clauses.extend(CardEnc.atleast(lits,lo,vpool=pool,encoding=EncType.cardnetwrk).clauses)
            if hi<len(lits):clauses.extend(CardEnc.atmost(lits,hi,vpool=pool,encoding=EncType.cardnetwrk).clauses)
    for u,w,c in q['fixed']:clauses.append([v(u,w) if c else -v(u,w)])
    for u,(lo,hi) in enumerate(q['degrees']):
        if lo==0 and hi==n-1:lo=max(0,(n-1)//2-2);hi=min(n-1,(n-1)//2+2)
        bounds([v(u,w) for w in range(n) if w!=u],lo,hi)
    for cut in q['cuts']:bounds([v(u,w) for u in cut['left'] for w in cut['right']],cut['min'],cut['max'])
    rows=initial;seen=set();iteration=0
    with Solver(name='cadical195',bootstrap_with=clauses) as solver:
        while time.monotonic()<deadline:
            bad=[]
            if len(rows)==n:
                for color,k in [(1,q['red_forbid']),(0,q['blue_forbid'])]:
                    for clique in violations(rows,color,k):
                        key=(color,tuple(clique))
                        if key not in seen:
                            seen.add(key);bad.append([-v(u,w) if color else v(u,w) for u,w in itertools.combinations(clique,2)])
                if iteration and not bad and structural(q,dict(id=q['id'],state='COMPLETE',rows=rows))[0]:return rows
                solver.set_phases([v(u,w) if rows[u][w]=='1' else -v(u,w) for u,w in edges])
            for clause in bad:solver.add_clause(clause)
            print(json.dumps(dict(iteration=iteration,clique_cuts=len(seen))),file=sys.stderr,flush=True)
            if not solver.solve():return None
            positive={x for x in solver.get_model() if x>0}
            rows=[''.join('.' if u==w else '1' if v(u,w) in positive else '0' for w in range(n)) for u in range(n)];iteration+=1
    return None

if __name__=='__main__':
    request=json.load(sys.stdin);rows=solve(request['query'],request.get('initial',[]),request['seconds'])
    if rows:print('\n'.join(rows));raise SystemExit(0)
    raise SystemExit(1)
