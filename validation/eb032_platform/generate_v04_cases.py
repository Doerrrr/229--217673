"""Author-only fixed-seed parity-face SOS construction."""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import json
import random


def make_case(index, n, rank):
    seed = 20261114000 + index
    rng = random.Random(seed)
    planted = [rng.choice((-1, 1)) for _ in range(n)]
    triples = [(i, i + 1, i + 2) for i in range(0, n - 2, 3)]
    if n % 3:
        triples.append((n - 3, n - 2, n - 1))
    generators = []
    for a, b, c in triples:
        sign = planted[a] * planted[b] * planted[c]
        for left, right, single in ((a, b, c), (a, c, b), (b, c, a)):
            generators.append({(1 << left) | (1 << right): 1, 1 << single: -sign})
    masks = {0} | {1 << i for i in range(n)}
    masks.update(mask for generator in generators for mask in generator)
    ordered = list(masks - {0})
    rng.shuffle(ordered)
    basis = [0] + ordered
    factors = []
    for _ in range(rank):
        factor = defaultdict(Fraction)
        for generator in generators:
            multiplier = rng.randint(-9999, 9999)
            for mask, coefficient in generator.items():
                factor[mask] += multiplier * coefficient
        factors.append([factor[mask] for mask in basis])
    denominators = (1, 17, 257, 4099)
    weights = [Fraction(1, denominators[i] ** 2) for i in range(rank)]
    gram = [[sum(weight * factor[i] * factor[j]
                 for weight, factor in zip(weights, factors))
             for j in range(len(basis))] for i in range(len(basis))]
    optimum = Fraction(-31 * index, 37)
    polynomial = defaultdict(Fraction)
    polynomial[0] = optimum
    for i, left in enumerate(basis):
        for j, right in enumerate(basis):
            polynomial[left ^ right] += gram[i][j]
    assert max(abs(value) for value in polynomial.values()) <= 10**12
    monomial = lambda mask: [i for i in range(n) if mask >> i & 1]
    query = dict(id='v04_%02d' % index, n=n, basis=[monomial(mask) for mask in basis],
                 terms=[dict(vars=monomial(mask), coef=str(value))
                        for mask, value in sorted(polynomial.items()) if value])
    assert all(len(term['coef']) <= 80 for term in query['terms'])
    answer = dict(id=query['id'], state='CERTIFIED', assignment=planted,
                  value=str(optimum), gram=[[str(value) for value in row] for row in gram])
    assert all(len(value) <= 128 for row in answer['gram'] for value in row)
    return dict(group='quartic_proof', query=query,
                answer=answer, optimum=str(optimum),
                certificate=dict(kind='COUPLED_PARITY_FACE_SOS',
                                 factors=[[str(value) for value in row] for row in factors],
                                 weights=list(map(str, weights))),
                generation=dict(seed=seed, n=n, basis_size=len(basis), rank=rank,
                                parity_triples=triples, planted=planted,
                                construction='fixed parity constraints with dense rational factor coupling'))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = [make_case(index, n, 3 + (index % 2))
             for index, n in enumerate((8, 10, 12, 8, 10, 12), 1)]
    args.output.write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8', newline='\n')
