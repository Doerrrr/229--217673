"""Oracle-only resource planning: validated policy and exact CP-SAT stages."""
import json
from collections import Counter
from ortools.sat.python import cp_model


def read_plan(path, aliases, valid_types):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def fields(value, keys):
        if not isinstance(value, dict) or set(value) != set(keys):
            raise ValueError(f"plan object requires exactly {','.join(keys)}")

    def integer(value, upper, lower=0):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"plan integer outside [{lower},{upper}]")

    with open(path, encoding='utf-8') as handle:
        plan = json.load(handle, object_pairs_hook=object_pairs,
                         parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    fields(plan, ('version', 'defaults', 'drug_overrides', 'folds'))
    integer(plan['version'], 1, 1)
    fields(plan['defaults'], ('stock', 'setup_cost'))
    integer(plan['defaults']['stock'], 96)
    integer(plan['defaults']['setup_cost'], 10000)
    if not isinstance(plan['drug_overrides'], list):
        raise ValueError('drug_overrides must be an array')
    overrides = {}
    for item in plan['drug_overrides']:
        fields(item, ('drug_id', 'stock', 'setup_cost'))
        key = item['drug_id']
        if not isinstance(key, str) or key not in aliases:
            raise ValueError('override requires a valid, nonconflicting drug ID')
        integer(item['stock'], 96)
        integer(item['setup_cost'], 10000)
        rep = aliases[key]
        config = (item['stock'], item['setup_cost'])
        if rep in overrides and overrides[rep] != config:
            raise ValueError('conflicting overrides for aliases of one molecule')
        overrides[rep] = config
    resources = {rep: overrides.get(rep, (plan['defaults']['stock'],
                                         plan['defaults']['setup_cost']))
                 for rep in set(aliases.values())}
    fields(plan['folds'], ('validation', 'test'))
    for config in plan['folds'].values():
        fields(config, ('budget', 'assay_cost', 'max_pairs', 'cluster_cap', 'event_quotas'))
        for key, limit in (('budget', 1000000), ('assay_cost', 10000),
                           ('max_pairs', 48), ('cluster_cap', 48)):
            integer(config[key], limit)
        if not isinstance(config['event_quotas'], list):
            raise ValueError('event_quotas must be an array')
        seen = set()
        for quota in config['event_quotas']:
            fields(quota, ('type', 'min', 'max'))
            typ = quota['type']
            if type(typ) is not int or typ not in valid_types or typ in seen:
                raise ValueError('quota type must reference a unique valid event')
            seen.add(typ)
            integer(quota['min'], 48)
            integer(quota['max'], 48, quota['min'])
    return resources, plan['folds']


def solve_plan(targets, options, metadata, resources, policy):
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
        model.add(sum(incident) <= resources[d][0])
    for cluster in {metadata[c][0] for _, c, _ in edges}:
        model.add(sum(xs[j] for j, (_, c, _) in enumerate(edges)
                      if metadata[c][0] == cluster) <= policy['cluster_cap'])
    for q in policy['event_quotas']:
        count = sum(xs[j] for j, (i, _, _) in enumerate(edges) if targets[i][1] == q['type'])
        model.add(count >= q['min'])
        model.add(count <= q['max'])
    count = sum(xs)
    score = sum(x * edge[2] for x, edge in zip(xs, edges))
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
    for i in range(len(targets)):
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


def audit(targets, matches, metadata, resources, policy, status):
    stock, clusters, events = Counter(), Counter(), Counter()
    score = 0
    for (a, typ, _), match in zip(targets, matches):
        if match:
            c, value = match
            stock.update((a, c))
            clusters[metadata[c][0]] += 1
            events[typ] += 1
            score += value
    return dict(
        status=status, total_score=score,
        total_cost=sum(resources[d][1] for d in stock) + sum(events.values()) * policy['assay_cost'],
        stock_usage=[dict(drug_id=d, used=stock[d], capacity=resources[d][0], setup_cost=resources[d][1])
                     for d in sorted(stock)],
        cluster_usage=[dict(cluster_id=c, used=clusters[c]) for c in sorted(clusters)],
        event_usage=[dict(type=q['type'], min=q['min'], max=q['max'], used=events[q['type']])
                     for q in sorted(policy['event_quotas'], key=lambda q: q['type'])])
