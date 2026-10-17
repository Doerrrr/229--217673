"""CP-SAT exact linear constraints plus lazily separated forbidden cliques."""
import itertools,time
from ortools.sat.python import cp_model

def cliques(rows,color,size,limit=400):
    n=len(rows);adj=[sum(1<<j for j in range(n) if i!=j and rows[i][j]==str(color)) for i in range(n)];found=[]
    def walk(mask,chosen):
        need=size-len(chosen)
        if not need:found.append(chosen);return len(found)>=limit
        while mask.bit_count()>=need:
            bit=mask&-mask;mask-=bit;v=bit.bit_length()-1
            if walk(mask&adj[v],chosen+[v]):return True
        return False
    walk((1<<n)-1,[]);return found

def repair(query,initial,seconds):
    n=query['n'];deadline=time.monotonic()+seconds
    if len(initial)!=n:return None
    edges=list(itertools.combinations(range(n),2));model=cp_model.CpModel();variables={e:model.new_bool_var(f'e{e[0]}_{e[1]}') for e in edges}
    def v(u,w):return variables[tuple(sorted((u,w)))]
    for u,w,c in query['fixed']:model.add(v(u,w)==c)
    for u,(lo,hi) in enumerate(query['degrees']):model.add_linear_constraint(sum(v(u,w) for w in range(n) if w!=u),lo,hi)
    for cut in query['cuts']:model.add_linear_constraint(sum(v(u,w) for u in cut['left'] for w in cut['right']),cut['min'],cut['max'])
    distance=sum((1-variables[e] if initial[e[0]][e[1]]=='1' else variables[e]) for e in edges)
    # Keep each candidate near the high-quality local construction. Enlarging
    # this radius never changes the public feasible region or accepts an error.
    radius=8;bound=model.add(distance<=radius);model.minimize(distance)
    rows=initial;seen=set();iteration=0;linear_feasible=False
    while time.monotonic()<deadline:
        new=0;violations=0
        for color,k in [(1,query['red_forbid']),(0,query['blue_forbid'])]:
            bad=cliques(rows,color,k);violations+=len(bad)
            for clique in bad:
                key=(color,tuple(clique))
                if key in seen:continue
                seen.add(key);new+=1
                literals=[v(u,w).Not() if color else v(u,w) for u,w in itertools.combinations(clique,2)];model.add_bool_or(literals)
        if linear_feasible and violations==0:return rows
        model.clear_hints()
        for e in edges:model.add_hint(variables[e],int(rows[e[0]][e[1]]))
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=2
        solver.parameters.max_time_in_seconds=max(.01,min(3,deadline-time.monotonic()))
        solver.parameters.random_seed=31+iteration
        status=solver.solve(model);iteration+=1
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            rows=[''.join('.' if u==w else str(solver.value(v(u,w))) for w in range(n)) for u in range(n)]
            linear_feasible=True
        else:
            # The radius is an internal search heuristic, never an input bound.
            radius+=8;bound.Proto().Clear();bound=model.add(distance<=radius)
            if radius>len(edges):break
    return None
