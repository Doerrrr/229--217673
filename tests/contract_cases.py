"""Public-contract boundary inputs shared by scoring and author regression."""
import copy
import itertools


def boundary_inputs(first):
    pairs = [sorted((i, (i + 1) % 32)) for i in range(32)]
    dimensions = dict(id='d' * 64, n=32,
                      basis=[[]] + [[i] for i in range(32)] + pairs,
                      terms=[dict(vars=[], coef='32')] +
                            [dict(vars=[i], coef='1') for i in range(32)])
    rational = dict(id='r' * 64, n=2, basis=[[], [0], [1]],
                    terms=[dict(vars=[], coef='1000000000000'),
                           dict(vars=[0], coef='0' * 79 + '1'),
                           dict(vars=[1], coef='+05/10')])
    queries = []
    for i in range(16):
        query = copy.deepcopy(first)
        query['id'] = 'upper_query_%02d' % i
        queries.append(query)
    return [('upper-dimensions', [dimensions]),
            ('upper-rational-id', [rational]),
            ('upper-query-count', queries)]


WRITE_FAILURES = ('output-directory', 'output-readonly-parent', 'output-parent-file')


def adjacent_invalid_inputs(first):
    """Change one documented bound at a time while keeping other fields valid."""
    result = []
    for name, field, value in (
            ('id-below-lower', 'id', ''),
            ('id-above-upper', 'id', 'a' * 65),
            ('coefficient-length-above-upper', 'terms', [dict(vars=[], coef='0' * 80 + '1')]),
            ('negative-coefficient-below-lower', 'terms', [dict(vars=[], coef='-1000000000001')])):
        query = copy.deepcopy(first)
        query[field] = value
        result.append((name, dict(version=1, queries=[query])))
    for name, n in (('n-below-lower', 1), ('n-above-upper-isolated', 33)):
        query = dict(id='n_bound', n=n, basis=[[]] + [[i] for i in range(n)],
                     terms=[dict(vars=[], coef='1')])
        result.append((name, dict(version=1, queries=[query])))
    queries = [dict(copy.deepcopy(first), id='overflow_%02d' % i) for i in range(17)]
    result.append(('queries-above-upper', dict(version=1, queries=queries)))
    query = boundary_inputs(first)[0][1][0]
    query['basis'].append([0, 2])
    result.append(('basis-above-upper', dict(version=1, queries=[query])))
    query = dict(id='degree_overflow', n=5, basis=[[]] + [[i] for i in range(5)],
                 terms=[dict(vars=[0, 1, 2, 3, 4], coef='1')])
    result.append(('term-degree-above-upper', dict(version=1, queries=[query])))
    monomials = itertools.chain.from_iterable(itertools.combinations(range(32), degree)
                                              for degree in range(5))
    query = dict(id='term_count_overflow', n=32, basis=[[]] + [[i] for i in range(32)],
                 terms=[dict(vars=list(mono), coef='1')
                        for mono in itertools.islice(monomials, 32769)])
    result.append(('term-count-above-upper', dict(version=1, queries=[query])))
    return result
