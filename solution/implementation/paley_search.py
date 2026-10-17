"""Input-constrained embeddings of algebraically generated Paley graphs."""
import time
from ortools.sat.python import cp_model
from graphs import paley,adjacency,find_clique,structural

def construct(q,seconds):
    n=q['n'];deadline=time.monotonic()+seconds
    for p in range(n,n+9):
        if p%4!=1 or any(p%d==0 for d in range(2,int(p**.5)+1)):continue
        parent=paley(p)
        if find_clique(adjacency(parent,1),q['red_forbid']) is not None:continue
        if find_clique(adjacency(parent,0),q['blue_forbid']) is not None:continue
        degree=(p-1)//2
        if p==n and any(not lo<=degree<=hi for lo,hi in q['degrees']):continue
        model=cp_model.CpModel();labels=[model.new_int_var(0,p-1,f'v{u}') for u in range(p)];model.add_all_different(labels)
        residues={a*a%p for a in range(1,p)}
        domains={c:cp_model.Domain.FromValues([d for d in range(1-p,p) if d and int(d%p in residues)==c]) for c in (0,1)}
        fixed={tuple(sorted((u,v))):c for u,v,c in q['fixed']};neighbors=[[] for _ in range(n)]
        for u,v,c in q['fixed']:
            model.add_linear_expression_in_domain(labels[u]-labels[v],domains[c]);neighbors[u].append((v,c));neighbors[v].append((u,c))
        # Translation and multiplication by a nonzero square are graph
        # automorphisms, including for an induced subset. These two anchors
        # preserve at least one embedding whenever one exists.
        root=max(range(n),key=lambda u:len(neighbors[u]));model.add(labels[root]==0)
        if neighbors[root]:
            v,c=max(neighbors[root],key=lambda pair:len(neighbors[pair[0]]))
            representative=1 if c else next(a for a in range(1,p) if a not in residues)
            model.add(labels[v]==representative)
        colors={}
        def edge(u,v):
            key=tuple(sorted((u,v)))
            if key in fixed:return fixed[key]
            if key not in colors:
                b=model.new_bool_var(f'e{key[0]}_{key[1]}');colors[key]=b
                model.add_linear_expression_in_domain(labels[u]-labels[v],domains[1]).only_enforce_if(b)
                model.add_linear_expression_in_domain(labels[u]-labels[v],domains[0]).only_enforce_if(b.Not())
            return colors[key]
        if p>n:
            for u,(lo,hi) in enumerate(q['degrees']):model.add_linear_constraint(degree-sum(edge(u,w) for w in range(n,p)),lo,hi)
        for cut in q['cuts']:model.add_linear_constraint(sum(edge(u,v) for u in cut['left'] for v in cut['right']),cut['min'],cut['max'])
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=2;solver.parameters.max_time_in_seconds=max(.01,deadline-time.monotonic());solver.parameters.random_seed=31
        status=solver.solve(model)
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            assignment=[solver.value(v) for v in labels[:n]]
            rows=[''.join('.' if u==v else str(int((assignment[u]-assignment[v])%p in residues)) for v in range(n)) for u in range(n)]
            if structural(q,dict(id=q['id'],state='COMPLETE',rows=rows))[0]:return rows
        if time.monotonic()>=deadline:break
    return None
