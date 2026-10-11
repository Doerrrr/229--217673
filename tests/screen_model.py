"""Independent policy interpretation and binary MILP release optimizer.

No imports from solution/. Sparse rows and sequential MILP constraints are built
here, independently from the Oracle's CP-SAT model.
"""
import json
import itertools
from collections import defaultdict
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


def policy_input(path, molecules, valid_events):
    def unique(pairs):
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError('repeated object key')
        return dict(pairs)
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)

    def shape(obj, keys):
        assert type(obj) is dict and sorted(obj) == sorted(keys), 'plan fields'

    def bounded(value, lo, hi):
        assert type(value) is int and lo <= value <= hi, 'plan integer'

    shape(data, ['version', 'defaults', 'drug_overrides', 'folds'])
    bounded(data['version'], 1, 1)
    shape(data['defaults'], ['stock', 'setup_cost'])
    bounded(data['defaults']['stock'], 0, 96)
    bounded(data['defaults']['setup_cost'], 0, 10000)
    ids = {alias: row[0] for row in molecules for alias in row[2].split(';')}
    limits = {row[0]: (data['defaults']['stock'], data['defaults']['setup_cost']) for row in molecules}
    assert type(data['drug_overrides']) is list
    seen = {}
    for entry in data['drug_overrides']:
        shape(entry, ['drug_id', 'stock', 'setup_cost'])
        assert type(entry['drug_id']) is str and entry['drug_id'] in ids
        bounded(entry['stock'], 0, 96)
        bounded(entry['setup_cost'], 0, 10000)
        rep = ids[entry['drug_id']]
        pair = (entry['stock'], entry['setup_cost'])
        assert rep not in seen or seen[rep] == pair
        seen[rep] = limits[rep] = pair
    shape(data['folds'], ['validation', 'test'])
    for fold in data['folds'].values():
        shape(fold, ['budget', 'assay_cost', 'max_pairs', 'cluster_cap', 'event_quotas'])
        for key, hi in [('budget',1000000), ('assay_cost',10000), ('max_pairs',48), ('cluster_cap',48)]:
            bounded(fold[key], 0, hi)
        assert type(fold['event_quotas']) is list
        seen = set()
        for q in fold['event_quotas']:
            shape(q, ['type', 'min', 'max'])
            assert type(q['type']) is int and q['type'] in valid_events and q['type'] not in seen
            seen.add(q['type'])
            bounded(q['min'], 0, 48)
            bounded(q['max'], q['min'], 48)
    return limits, data['folds']


def optimize_batch(targets, options, meta, resources, config):
    arcs = [(i,c,s) for i,row in enumerate(options) for c,s in row]
    if not arcs:
        return [None]*len(targets), 'INFEASIBLE' if any(q['min'] for q in config['event_quotas']) else 'OPTIMAL'
    participants = sorted({d for i,c,_ in arcs for d in (targets[i][0],c)})
    activation = {d: len(arcs)+j for j,d in enumerate(participants)}
    size = len(arcs)+len(participants)
    rows, lower, upper = [], [], []

    def constrain(coefficients, lo=-np.inf, hi=np.inf):
        rows.append(coefficients)
        lower.append(lo)
        upper.append(hi)

    def indices(predicate):
        return {j: 1 for j,arc in enumerate(arcs) if predicate(*arc)}

    for t in range(len(targets)):
        constrain(indices(lambda i,c,s: i == t), hi=1)
    for candidate in {c for _,c,_ in arcs}:
        constrain(indices(lambda i,c,s: c == candidate), hi=1)
    for drug in participants:
        incidence = indices(lambda i,c,s: drug == targets[i][0] or drug == c)
        constrain(incidence, hi=resources[drug][0])
        # z == OR(incident edges); required even for zero-cost molecules.
        constrain({**{j:-v for j,v in incidence.items()}, activation[drug]:1}, hi=0)
        for j in incidence:
            constrain({j:1, activation[drug]:-1}, hi=0)
    for cluster in {meta[c][0] for _,c,_ in arcs}:
        constrain(indices(lambda i,c,s: meta[c][0] == cluster), hi=config['cluster_cap'])
    for q in config['event_quotas']:
        constrain(indices(lambda i,c,s: targets[i][1] == q['type']), q['min'], q['max'])
    count = {j:1 for j in range(len(arcs))}
    score = {j:s for j,(_,_,s) in enumerate(arcs)}
    cost = {j:config['assay_cost'] for j in range(len(arcs))}
    cost.update({activation[d]:resources[d][1] for d in participants})
    constrain(count, hi=config['max_pairs'])
    constrain(cost, hi=config['budget'])

    def stage(coefficients, maximize=False):
        rr, cc, vv = [], [], []
        for r, values in enumerate(rows):
            for c,v in values.items():
                if v:
                    rr.append(r); cc.append(c); vv.append(v)
        matrix = coo_matrix((vv,(rr,cc)), shape=(len(rows),size)).tocsc()
        objective = np.zeros(size)
        for j,v in coefficients.items():
            objective[j] = -v if maximize else v
        result = milp(objective, integrality=np.ones(size), bounds=Bounds(0,1),
                      constraints=LinearConstraint(matrix,lower,upper), options={'mip_rel_gap':0})
        if result.status == 2:
            return None
        if result.status != 0 or result.x is None:
            raise AssertionError(f'MILP did not prove optimum: {result.message}')
        values = np.rint(result.x).astype(int)
        assert np.max(np.abs(result.x-values)) < 1e-5
        optimum = sum(v*values[j] for j,v in coefficients.items())
        constrain(coefficients, optimum, optimum)
        return values

    values = stage(count, True)
    if values is None:
        return [None]*len(targets), 'INFEASIBLE'
    values = stage(score, True)
    values = stage(cost)
    ordered = sorted({c for _,c,_ in arcs})
    rank = {c:j for j,c in enumerate(ordered)}
    for target in range(len(targets)):
        coefficients = {j:rank[c]-len(ordered) for j,(i,c,_) in enumerate(arcs) if i == target}
        if coefficients:
            values = stage(coefficients)
    answer = [None]*len(targets)
    for j,(i,c,s) in enumerate(arcs):
        if values[j]:
            answer[i] = (c,s)
    return answer, 'OPTIMAL'


def resource_report(targets, selected, meta, resources, config, status, enforce=True):
    uses, cluster_uses, event_counts = defaultdict(int), defaultdict(int), defaultdict(int)
    total_score, total_pairs = 0, 0
    candidate_ids = set()
    for (anchor,typ,_), choice in zip(targets,selected):
        if choice is None:
            continue
        candidate, score = choice
        if enforce:
            assert candidate not in candidate_ids, 'candidate reused'
        candidate_ids.add(candidate)
        uses[anchor] += 1
        uses[candidate] += 1
        cluster_uses[meta[candidate][0]] += 1
        event_counts[typ] += 1
        total_pairs += 1
        total_score += score
    expense = total_pairs*config['assay_cost'] + sum(resources[d][1] for d in uses)
    if enforce:
        assert all(n <= resources[d][0] for d,n in uses.items()), 'shared inventory exceeded'
        assert expense <= config['budget'] and total_pairs <= config['max_pairs'], 'budget/pair limit exceeded'
        assert all(n <= config['cluster_cap'] for n in cluster_uses.values()), 'cluster cap exceeded'
        if status == 'OPTIMAL':
            assert all(q['min'] <= event_counts[q['type']] <= q['max'] for q in config['event_quotas']), 'quota exceeded'
        else:
            assert status == 'INFEASIBLE' and not total_pairs, 'infeasible output selected assays'
    return {'status':status, 'total_score':total_score, 'total_cost':expense,
            'stock_usage':[{'drug_id':d,'used':uses[d],'capacity':resources[d][0],'setup_cost':resources[d][1]} for d in sorted(uses)],
            'cluster_usage':[{'cluster_id':c,'used':cluster_uses[c]} for c in sorted(cluster_uses)],
            'event_usage':[{'type':q['type'],'min':q['min'],'max':q['max'],'used':event_counts[q['type']]}
                           for q in sorted(config['event_quotas'],key=lambda q:q['type'])]}


def exhaustive_batch(targets, options, meta, resources, config):
    """Small-instance truth by listing all assignments, not an optimization solver."""
    best = None
    for values in itertools.product(*(row+[None] for row in options)):
        try:
            report = resource_report(targets,values,meta,resources,config,'OPTIMAL')
        except AssertionError:
            continue
        key = (-sum(v is not None for v in values), -report['total_score'], report['total_cost'],
               tuple((1,'') if v is None else (0,v[0]) for v in values))
        if best is None or key < best[0]:
            best = key,list(values)
    return (best[1], 'OPTIMAL') if best else ([None]*len(targets),'INFEASIBLE')
