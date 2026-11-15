"""Recover a rational Gram face, then verify it with exact arithmetic."""
from fractions import Fraction
import time

import numpy as np
from scipy.optimize import least_squares
import sympy as sy


def restricted_gram(basis, poly, assignment, approximate, vectors, deadline, solver):
    """Short integer relations propose the kernel of a rational row space."""
    dimension, rank = vectors.shape
    negative = sum(1 << i for i, value in enumerate(assignment) if value == -1)
    signs = [1 if (mask & negative).bit_count() % 2 == 0 else -1 for mask in basis]
    target = dict(poly)
    target[0] = target.get(0, Fraction(0)) - solver.value_at(poly, assignment)
    for precision in (10**6, 10**8):
        if time.monotonic() >= deadline:
            return None
        lattice = sy.Matrix([
            [int(i == j) for j in range(dimension)]
            + [round(float(vectors[i, k]) * precision) for k in range(rank)]
            for i in range(dimension)
        ])
        try:
            reduced = lattice.lll()
        except (ValueError, AssertionError):
            continue
        relations = sorted(
            (list(map(int, reduced.row(i))) for i in range(dimension)),
            key=lambda row: sum(value * value for value in row),
        )
        kernel = sy.Matrix([row[:dimension] for row in relations[:dimension-rank]])
        nullspace = kernel.nullspace()
        if len(nullspace) != rank:
            continue
        columns = []
        for vector in nullspace:
            maximum = max(abs(value) for value in vector)
            columns.append([Fraction(value / maximum) for value in vector])
        forms = [
            [-sum(signs[i+1] * column[i] for i in range(dimension))] + column
            for column in columns
        ]
        pairs = [(i, j) for i in range(rank) for j in range(i, rank)]
        rows = {}
        for column_index, (left, right) in enumerate(pairs):
            multiplier = 1 if left == right else 2
            for i in range(dimension+1):
                for j in range(dimension+1):
                    value = multiplier * forms[left][i] * forms[right][j]
                    if value:
                        row = rows.setdefault(basis[i] ^ basis[j], {})
                        row[column_index] = row.get(column_index, 0) + value
        rows = {mask: {index: value for index, value in row.items() if value}
                for mask, row in rows.items()}
        if any(value and mask not in rows for mask, value in target.items()):
            continue
        inverse = np.linalg.pinv(np.asarray(columns, dtype=float).T)
        guess = inverse @ approximate @ inverse.T
        rounded = [Fraction(float(guess[i, j])).limit_denominator(10**6)
                   for i, j in pairs]
        exact = solver.affine_project(rows, pairs, target, rounded)
        if exact is None or time.monotonic() >= deadline:
            continue
        small = [[Fraction(0)] * rank for _ in range(rank)]
        for (i, j), value in zip(pairs, exact):
            small[i][j] = small[j][i] = value
        if not solver.is_psd(small, deadline):
            continue
        gram = [
            [sum(forms[i][a] * small[i][j] * forms[j][b]
                 for i in range(rank) for j in range(rank))
             for b in range(dimension+1)]
            for a in range(dimension+1)
        ]
        try:
            for row in gram:
                for value in row:
                    solver.string_of(value)
        except OverflowError:
            continue
        # Congruence with the exact PSD small matrix proves Gram PSD.
        if solver.exact_identity(basis, poly, assignment, gram):
            return gram
    return None


def refined_matrix(rows, pairs, target, approximate, rank, deadline):
    """Fit low-rank factors to every coefficient equation simultaneously."""
    dimension = len(approximate)
    scale = max(abs(float(value)) for value in target.values())
    tensors = np.zeros((len(rows), dimension, dimension))
    for equation_index, row in enumerate(rows.values()):
        for column_index, weight in row.items():
            i, j = pairs[column_index]
            tensors[equation_index, i, j] = float(weight) / (1 if i == j else 2)
            tensors[equation_index, j, i] = tensors[equation_index, i, j]
    rhs = np.asarray([float(target.get(mask, 0)) / scale for mask in rows])
    values, vectors = np.linalg.eigh(approximate / scale)
    initial = vectors[:, -rank:] * np.sqrt(np.maximum(values[-rank:], 1e-12))

    def residual(flat):
        if time.monotonic() >= deadline:
            raise TimeoutError('Gram recovery budget exhausted')
        factors = flat.reshape(dimension, rank)
        return np.einsum('ia,mij,ja->m', factors, tensors, factors,
                         optimize=True) - rhs

    def jacobian(flat):
        factors = flat.reshape(dimension, rank)
        return (2 * np.einsum('mij,ja->mia', tensors, factors,
                              optimize=True)).reshape(len(rows), -1)

    result = least_squares(residual, initial.ravel(), jac=jacobian,
                           ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=500)
    if max(abs(result.fun), default=0) > 1e-10:
        return None
    factors = result.x.reshape(dimension, rank)
    return factors @ factors.T * scale


def recover_gram(basis, poly, assignment, approximate, deadline, solver):
    dimension = len(approximate)
    if dimension < 2 or dimension > 32 or time.monotonic() >= deadline:
        return None
    approximate = np.asarray(approximate, dtype=float)
    values, vectors = np.linalg.eigh(approximate)
    scale = max(abs(values[-1]), 1e-30)
    ranks = sorted({int(np.count_nonzero(values > scale * tolerance))
                    for tolerance in (1e-4, 1e-8)})
    for rank in ranks:
        if 0 < rank < dimension:
            gram = restricted_gram(basis, poly, assignment, approximate,
                                   vectors[:, -rank:], deadline, solver)
            if gram is not None:
                return gram
    rows, pairs, target, signs = solver.equations(basis, poly, assignment)
    # Refine the observed numerical ranks first. Smaller incompatible ranks can
    # otherwise spend the entire recovery budget before the viable rank is tried.
    refinement_ranks = [rank for rank in ranks if 0 < rank < dimension]
    refinement_ranks.extend(rank for rank in range(1, min(dimension, 7))
                            if rank not in refinement_ranks)
    for rank in refinement_ranks:
        if time.monotonic() >= deadline:
            break
        remaining = deadline - time.monotonic()
        rank_deadline = min(deadline, time.monotonic() + max(0.05, remaining * 0.5))
        try:
            refined = refined_matrix(rows, pairs, target, approximate, rank, rank_deadline)
        except TimeoutError:
            continue
        if refined is None:
            continue
        _, vectors = np.linalg.eigh(refined)
        gram = restricted_gram(basis, poly, assignment, refined,
                               vectors[:, -rank:], deadline, solver)
        if gram is not None:
            return gram
    return None
