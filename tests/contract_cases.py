"""Public-contract boundary inputs shared by scoring and author regression."""
import copy


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
