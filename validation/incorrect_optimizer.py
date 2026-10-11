"""Validation-only CP-SAT variants with intentional business-rule errors."""
from ortools.sat.python import cp_model


def solve_plan(targets, options, metadata, resources, policy, variant=None):
    """Four proven optima; no weighted floating-point lexicographic objective."""
    model = cp_model.CpModel()
    edges = [(i, c, score) for i, row in enumerate(options) for c, score in row]
    xs = [model.new_bool_var(f'e{j}') for j in range(len(edges))]
    drugs = sorted({d for i, c, _ in edges for d in (targets[i][0], c)})
    zs = {d: model.new_bool_var(f'used_{d}') for d in drugs}
    for i in range(len(targets)):
        model.add(sum(xs[j] for j, edge in enumerate(edges) if edge[0] == i) <= 1)
    for c in {edge[1] for edge in edges}:
        model.add(sum(xs[j] for j, edge in enumerate(edges) if edge[1] == c) <= 1)
    for d in drugs:
        incident = [xs[j] for j, (i, c, _) in enumerate(edges) if d in (targets[i][0], c)]
        model.add(zs[d] <= sum(incident))
        for x in incident:
            model.add(x <= zs[d])
        if variant == 'split_stock':
            for role in (0, 1):
                model.add(sum(xs[j] for j, (i, c, _) in enumerate(edges)
                              if (targets[i][0] if role == 0 else c) == d) <= resources[d][0])
        else:
            model.add(sum(incident) <= resources[d][0])
    for cluster in {metadata[c][0] for _, c, _ in edges}:
        model.add(sum(xs[j] for j, (_, c, _) in enumerate(edges)
                      if metadata[c][0] == cluster) <= policy['cluster_cap'])
    for q in policy['event_quotas']:
        count = sum(xs[j] for j, (i, _, _) in enumerate(edges) if targets[i][1] == q['type'])
        model.add(count >= (0 if variant == 'ignore_min' else q['min']))
        model.add(count <= q['max'])
    count = sum(xs)
    score = sum(x * edge[2] for x, edge in zip(xs, edges))
    if variant == 'per_assay_setup':
        cost = cp_model.LinearExpr.weighted_sum(xs, [policy['assay_cost'] + resources[targets[i][0]][1] + resources[c][1]
                                                     for i,c,_ in edges])
    else:
        cost = cp_model.LinearExpr.weighted_sum(xs + [zs[d] for d in drugs],
                    [policy['assay_cost']]*len(xs) + [resources[d][1] for d in drugs])
    model.add(count <= policy['max_pairs'])
    model.add(cost <= policy['budget'])
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0

    def optimize(expr, maximize=False):
        (model.maximize if maximize else model.minimize)(expr)
        status = solver.solve(model)
        if status == cp_model.INFEASIBLE:
            return None
        if status != cp_model.OPTIMAL:
            raise ValueError(f'optimizer did not prove optimality: {solver.status_name(status)}')
        value = solver.value(expr)
        model.add(expr == value)
        return value

    if optimize(count, True) is None:
        return [None] * len(targets), 'INFEASIBLE'
    optimize(score, True)
    optimize(cost)
    ids = sorted({c for _, c, _ in edges})
    ranks = {c: j for j, c in enumerate(ids)}
    if variant == 'float_lex':
        # Validation-only flawed approach: tiny perturbations lose later ranks
        # when the solver scales the floating objective. Not used by the Oracle.
        model.minimize(sum((ranks[c]-len(ids)) * (1e-9 ** i) * x
                           for x,(i,c,_) in zip(xs,edges)))
        if solver.solve(model) != cp_model.OPTIMAL:
            raise ValueError('perturbed optimizer failed')
    for i in range(len(targets)) if variant != 'float_lex' else ():
        members = [(j, c) for j, (t, c, _) in enumerate(edges) if t == i]
        if members:
            # The unmatched rank is len(ids), beyond every actual candidate.
            expr = len(ids) + sum((ranks[c] - len(ids)) * xs[j] for j, c in members)
            optimize(expr)
    selected = [None] * len(targets)
    for x, (i, c, s) in zip(xs, edges):
        if solver.value(x):
            selected[i] = (c, s)
    return selected, 'OPTIMAL'
