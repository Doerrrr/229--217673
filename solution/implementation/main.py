"""General Boolean optimizer with independently checked exact certificates."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

from interface import Bad, parse_document
from solver import solve


def solve_queries(queries):
    answers = []
    cache = {}
    budget = 260.0 / len(queries)
    for query in queries:
        basis = [sum(1 << i for i in mono) for mono in query['basis']]
        polynomial = {sum(1 << i for i in mono): coefficient
                      for mono, coefficient in query['terms']}
        key = (query['n'], tuple(basis), tuple(sorted(polynomial.items())))
        if key not in cache:
            cache[key] = solve((query['id'], query['n'], basis, polynomial), budget)
        answer = copy.deepcopy(cache[key])
        answer['id'] = query['id']
        answers.append(answer)
    return answers


def write_output(target, answers):
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=target.parent,
                                         prefix='.certified-minimum-',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            for answer in answers:
                stream.write(json.dumps(answer, separators=(',', ':')) + '\n')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        text = Path(args.input).read_bytes().decode('utf-8-sig')
        queries = parse_document(text)
    except (OSError, UnicodeError, ValueError, Bad) as error:
        print('invalid input: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
    try:
        answers = solve_queries(queries)
        write_output(Path(args.output), answers)
    except OSError as error:
        print('cannot write output: ' + str(error), file=sys.stderr)
        raise SystemExit(3)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
