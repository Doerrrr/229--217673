"""Search numerically; accept a certificate only after exact algebraic checks."""
from fractions import Fraction
import math
import random
import time
import warnings

def value_at(poly, assignment):
    negative = sum(1 << i for i, value in enumerate(assignment) if value == -1)
    return sum((c if (mask & negative).bit_count() % 2 == 0 else -c)
               for mask, c in poly.items())

def string_of(value):
    value = Fraction(value)
    result = str(value.numerator) if value.denominator == 1 else f'{value.numerator}/{value.denominator}'
    if len(result) > 128:
        raise OverflowError('output rational too long')
    return result

def local_assignment(n, poly, seconds):
    rng = random.Random(0xDD1032)
    stop = time.monotonic() + seconds
    best, best_value = None, None
    for run in range(128):
        if time.monotonic() >= stop: break
        assignment = [1] * n if run == 0 else [rng.choice((-1, 1)) for _ in range(n)]
        for _ in range(4*n + 4):
            if time.monotonic() >= stop: break
            current = value_at(poly, assignment)
            if best_value is None or current < best_value:
                best, best_value = assignment[:], current
            negative = sum(1 << i for i, x in enumerate(assignment) if x == -1)
            best_flip, best_delta = None, Fraction(0)
            for i in range(n):
                delta = -2 * sum((c if (mask & negative).bit_count() % 2 == 0 else -c)
                                 for mask, c in poly.items() if mask >> i & 1)
                if delta < best_delta:
                    best_flip, best_delta = i, delta
            if best_flip is None: break
            assignment[best_flip] *= -1
    return best or [1] * n

def optimize(n, poly, seconds):
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return local_assignment(n, poly, seconds)
    model = cp_model.CpModel()
    bits = [model.NewBoolVar(f'x{i}') for i in range(n)]
    masks = [mask for mask in poly if mask]
    parities = {}
    for mask in masks:
        indices = [i for i in range(n) if mask >> i & 1]
        if len(indices) == 1:
            parities[mask] = bits[indices[0]]
        else:
            p = model.NewBoolVar(f'p{mask}')
            model.AddBoolXOr([bits[i] for i in indices] + [p.Not()])
            parities[mask] = p
    coefficients = [poly[mask] for mask in masks]
    common = 1
    for c in coefficients:
        common = math.lcm(common, c.denominator)
        if common > 10**15: break
    if common <= 10**15:
        weights = [int(c * common) for c in coefficients]
        divisor = math.gcd(*weights) if weights else 1
        weights = [w // divisor for w in weights]
    else:
        scale = 10**12 / max((float(abs(c)) for c in coefficients), default=1)
        weights = [round(float(c) * scale) for c in coefficients]
    if max((abs(w) for w in weights), default=0) > 10**15 or sum(map(abs, weights)) > 4*10**18:
        scale = 10**12 / max((float(abs(c)) for c in coefficients), default=1)
        weights = [round(float(c) * scale) for c in coefficients]
    model.Maximize(sum(w * parities[mask] for mask, w in zip(masks, weights) if w))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, seconds)
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [1 - 2*solver.Value(bit) for bit in bits]
    return local_assignment(n, poly, min(seconds, 5))

def equations(basis, poly, assignment, equal_assignments=()):
    """Represent Q as B.T H B, with B_i z = z_(i+1)-z_(i+1)(x*)."""
    negative = sum(1 << i for i, x in enumerate(assignment) if x == -1)
    signs = [1 if (mask & negative).bit_count() % 2 == 0 else -1 for mask in basis]
    rows, columns = {}, []
    for i in range(1, len(basis)):
        for j in range(i, len(basis)):
            col = len(columns)
            columns.append((i-1, j-1))
            factor = 1 if i == j else 2
            pieces = ((basis[i] ^ basis[j], 1), (basis[i], -signs[j]),
                      (basis[j], -signs[i]), (0, signs[i]*signs[j]))
            for mask, coefficient in pieces:
                row = rows.setdefault(mask, {})
                row[col] = row.get(col, 0) + factor*coefficient
    rows = {mask: {col: weight for col, weight in row.items() if weight}
            for mask, row in rows.items()}
    independent = {}
    number = 0
    for other in equal_assignments:
        other_negative = sum(1 << i for i, x in enumerate(other) if x == -1)
        other_signs = [1 if (mask & other_negative).bit_count() % 2 == 0 else -1 for mask in basis]
        difference = [other_signs[i+1]-signs[i+1] for i in range(len(basis)-1)]
        if not any(difference): continue
        reduced = {i: Fraction(v) for i, v in enumerate(difference) if v}
        while reduced and min(reduced) in independent:
            lead = min(reduced)
            factor = reduced[lead]
            for i, v in independent[lead].items():
                updated = reduced.get(i, 0)-factor*v
                if updated: reduced[i] = updated
                else: reduced.pop(i, None)
        if not reduced: continue
        lead = min(reduced)
        factor = reduced[lead]
        independent[lead] = {i: v/factor for i, v in reduced.items()}
        for i in range(len(difference)):
            row = {}
            for col, (a, b) in enumerate(columns):
                weight = (difference[b] if a == i else 0) + (difference[a] if b == i and a != b else 0)
                if weight: row[col] = weight
            rows[(number, i)] = row
        number += 1
    target = dict(poly)
    target[0] = target.get(0, Fraction(0)) - value_at(poly, assignment)
    if any(mask not in rows and coefficient for mask, coefficient in target.items()):
        return None
    return rows, columns, target, signs

def affine_project(rows, columns, target, rounded):
    """Exact sparse elimination of the residual, free corrections set to zero."""
    residual = {mask: target.get(mask, 0) - sum(Fraction(weight)*rounded[col]
                for col, weight in row.items()) for mask, row in rows.items()}
    pivots = {}
    for mask, original in rows.items():
        row = {col: Fraction(weight) for col, weight in original.items()}
        rhs = Fraction(residual[mask])
        while row:
            col = min(row)
            if col not in pivots:
                lead = row[col]
                pivots[col] = ({k: v/lead for k, v in row.items()}, rhs/lead)
                break
            pivot_row, pivot_rhs = pivots[col]
            factor = row[col]
            for k, value in pivot_row.items():
                updated = row.get(k, 0) - factor*value
                if updated: row[k] = updated
                else: row.pop(k, None)
            rhs -= factor*pivot_rhs
        else:
            if rhs: return None
    correction = [Fraction(0)]*len(columns)
    for col in sorted(pivots, reverse=True):
        row, rhs = pivots[col]
        correction[col] = rhs - sum(value*correction[k] for k, value in row.items() if k != col)
    return [a+b for a, b in zip(rounded, correction)]

def is_psd(matrix, deadline=None):
    """Exact symmetric elimination; zero diagonal requires a zero remaining row."""
    a = [row[:] for row in matrix]
    for k in range(len(a)):
        if deadline is not None and time.monotonic() >= deadline: return False
        pivot = a[k][k]
        if pivot < 0: return False
        if pivot == 0:
            if any(a[k][j] for j in range(k+1, len(a))): return False
            continue
        for i in range(k+1, len(a)):
            for j in range(i, len(a)):
                a[i][j] -= a[k][i]*a[k][j]/pivot
                a[j][i] = a[i][j]
    return True

def exact_identity(basis, poly, assignment, gram):
    target = dict(poly)
    target[0] = target.get(0, Fraction(0)) - value_at(poly, assignment)
    actual = {}
    for i in range(len(basis)):
        for j in range(i, len(basis)):
            mask = basis[i] ^ basis[j]
            actual[mask] = actual.get(mask, Fraction(0)) + (1 if i == j else 2)*gram[i][j]
    return all(actual.get(mask, 0) == target.get(mask, 0) for mask in set(actual) | set(target))

def certificate(basis, poly, assignment, seconds, equal_assignments=()):
    data = equations(basis, poly, assignment, equal_assignments)
    if data is None: return None
    rows, columns, target, signs = data
    d = len(basis)-1
    import numpy as np
    import scipy.sparse as sp
    import cvxpy as cp
    masks = list(rows)
    triples = [(r, col, float(weight)) for r, mask in enumerate(masks)
               for col, weight in rows[mask].items()]
    A = sp.csc_matrix(([v for _, _, v in triples],
                       ([r for r, _, _ in triples], [c for _, c, _ in triples])),
                      shape=(len(masks), len(columns)))
    scale = max((abs(float(c)) for c in target.values()), default=0.0)
    if scale == 0:
        return [[Fraction(0)]*len(basis) for _ in basis]
    H = cp.Variable((d, d), symmetric=True)
    floor = cp.Variable()
    vector = cp.hstack([H[i, j] for i, j in columns])
    rhs = np.array([float(target.get(mask, 0))/scale for mask in masks])
    problem = cp.Problem(cp.Maximize(floor),
                         [A@vector == rhs, H-floor*np.eye(d) >> 0])
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Constraint #0 contains too many subexpressions')
        try:
            problem.solve(solver='CLARABEL', max_iter=150, tol_gap_abs=1e-10,
                          tol_feas=1e-10, verbose=False)
        except Exception:
            try: problem.solve(solver='SCS', eps=1e-8, max_iters=30000, verbose=False)
            except Exception: return None
    if H.value is None: return None
    numerical = np.asarray(H.value)*scale
    deadline = time.monotonic()+seconds
    for digits in (5, 7, 9, 11, 13):
        if time.monotonic() >= deadline: break
        denominator = 10**digits
        rounded = [Fraction(round(float(numerical[i, j])*denominator), denominator)
                   for i, j in columns]
        exact = affine_project(rows, columns, target, rounded)
        if exact is None: continue
        h = [[Fraction(0)]*d for _ in range(d)]
        for (i, j), value in zip(columns, exact):
            h[i][j] = h[j][i] = value
        try:
            for row in h:
                for item in row: string_of(item)
        except OverflowError: continue
        if not is_psd(h, deadline): continue
        gram = [[Fraction(0)]*(d+1) for _ in range(d+1)]
        for i in range(d):
            for j in range(d): gram[i+1][j+1] = h[i][j]
        for i in range(d):
            gram[0][i+1] = gram[i+1][0] = -sum(signs[j+1]*h[i][j] for j in range(d))
        gram[0][0] = sum(signs[i+1]*signs[j+1]*h[i][j]
                         for i in range(d) for j in range(d))
        if not exact_identity(basis, poly, assignment, gram): continue
        try:
            for row in gram:
                for item in row: string_of(item)
        except OverflowError: continue
        return gram
    return None

def equal_minima(n, poly, assignment, seconds, limit=96):
    """Find other exact ties; each supplies a necessary Gram-kernel vector."""
    optimum = value_at(poly, assignment)
    if n <= 14 and len(poly)*(1 << n) <= 3_000_000:
        found = []
        stop = time.monotonic()+seconds
        for bits in range(1 << n):
            if time.monotonic() >= stop or len(found) >= limit: break
            other = [1-2*(bits >> i & 1) for i in range(n)]
            if other != assignment and value_at(poly, other) == optimum:
                found.append(other)
        return found
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return []
    model = cp_model.CpModel()
    bits = [model.NewBoolVar(f'x{i}') for i in range(n)]
    masks = [mask for mask in poly if mask]
    parity = {}
    for mask in masks:
        indices = [i for i in range(n) if mask >> i & 1]
        if len(indices) == 1: parity[mask] = bits[indices[0]]
        else:
            p = model.NewBoolVar(f'p{mask}')
            model.AddBoolXOr([bits[i] for i in indices]+[p.Not()])
            parity[mask] = p
    common = 1
    for mask in masks:
        common = math.lcm(common, poly[mask].denominator)
        if common > 10**15: break
    if common <= 10**15:
        weights = [int(poly[mask]*common) for mask in masks]
        divisor = math.gcd(*weights) if weights else 1
        weights = [w//divisor for w in weights]
    else:
        scale = 10**12/max((float(abs(poly[mask])) for mask in masks),default=1)
        weights = [round(float(poly[mask])*scale) for mask in masks]
    if sum(map(abs,weights)) > 4*10**18: return []
    negative = sum(1 << i for i, x in enumerate(assignment) if x == -1)
    score = sum(w for mask,w in zip(masks,weights) if (mask & negative).bit_count() % 2)
    model.Add(sum(w*parity[mask] for mask,w in zip(masks,weights) if w) == score)
    class Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.found=[]
        def on_solution_callback(self):
            other = [1-2*self.Value(bit) for bit in bits]
            if other != assignment and value_at(poly,other) == optimum:
                self.found.append(other)
                if len(self.found) >= limit: self.StopSearch()
    collector = Collector()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0,seconds)
    solver.parameters.num_search_workers = 1
    solver.SearchForAllSolutions(model,collector)
    return collector.found

def linear_solution(query):
    qid, n, basis, poly = query
    assignment = [-1 if poly.get(1 << i, 0) > 0 else 1 for i in range(n)]
    gram = [[Fraction(0) for _ in basis] for _ in basis]
    for i in range(n):
        coefficient = poly.get(1 << i, Fraction(0))
        index = basis.index(1 << i)
        gram[0][0] += abs(coefficient) / 2
        gram[index][index] += abs(coefficient) / 2
        gram[0][index] = gram[index][0] = coefficient / 2
    return {'id': qid, 'state': 'CERTIFIED', 'assignment': assignment,
            'value': string_of(value_at(poly, assignment)),
            'gram': [[string_of(item) for item in row] for row in gram]}


def solve(query, budget):
    qid, n, basis, poly = query
    if all(mask.bit_count() <= 1 for mask in poly):
        try:
            return linear_solution(query)
        except OverflowError:
            return {'id': qid, 'state': 'UNSOLVED', 'assignment': None,
                    'value': None, 'gram': None}
    start = time.monotonic()
    try: assignment = optimize(n, poly, min(100.0, budget*0.4))
    except Exception: assignment = local_assignment(n, poly, min(5.0, budget*0.1))
    value = value_at(poly, assignment)
    try: value_string = string_of(value)
    except OverflowError:
        return {'id': qid, 'state': 'UNSOLVED', 'assignment': None,
                'value': None, 'gram': None}
    result = {'id': qid, 'state': 'INCUMBENT', 'assignment': assignment,
              'value': value_string, 'gram': None}
    try:
        gram = certificate(basis, poly, assignment, min(30.0,max(1.0,budget-(time.monotonic()-start))))
        if gram is None and budget-(time.monotonic()-start) > 10:
            ties = equal_minima(n, poly, assignment, min(10.0,budget*0.1))
            if ties:
                gram = certificate(basis, poly, assignment,
                                   max(1.0,budget-(time.monotonic()-start)),ties)
        if gram is not None:
            result['state'] = 'CERTIFIED'
            result['gram'] = [[string_of(item) for item in row] for row in gram]
    except Exception:
        pass
    return result
