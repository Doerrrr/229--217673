"""Non-scoring CLI regressions for singular recovery, short budgets and retries."""
import json
from pathlib import Path
import shutil
import sys


def run(repo, results, workspace):
    sys.path.insert(0, str(repo / 'tests'))
    sys.path.insert(0, str(repo / 'solution/implementation'))
    from algebra import check
    from common import Runner, success
    from interface import parse_query
    import solver

    cases = json.loads((repo / 'tests/cases032.json').read_bytes())
    singular = [case for case in cases if case['group'] == 'singular_proof']
    assert len(singular) == 6
    records = []
    for profile in ('standard', 'short-budget', 'empty-ties-retry'):
        project = workspace / ('certificate-' + profile)
        shutil.copytree(repo / 'environment', project,
                        ignore=shutil.ignore_patterns('data', 'Dockerfile', '__pycache__', '*.pyc'))
        for source in (repo / 'solution/implementation').glob('*.py'):
            shutil.copyfile(source, project / 'app' / source.name)
        if profile == 'short-budget':
            path = project / 'app/main.py'
            text = path.read_text()
            assert 'budget = 260.0 / len(queries)' in text
            path.write_text(text.replace('budget = 260.0 / len(queries)', 'budget = 1.0'))
        if profile == 'empty-ties-retry':
            path = project / 'app/solver.py'
            injected = """
_original_certificate = certificate
_author_attempt = 0


def certificate(*args, **kwargs):
    global _author_attempt
    _author_attempt += 1
    print(json.dumps(dict(event='author_fault_injection', attempt=_author_attempt,
                          method=kwargs.get('method'))), file=sys.stderr, flush=True)
    if _author_attempt == 1:
        raise TimeoutError('author-injected first-attempt exhaustion')
    return _original_certificate(*args, **kwargs)


def equal_minima(*args, **kwargs):
    return []
"""
            path.write_text(path.read_text() + injected)

        target = results / ('certificate-' + profile)
        target.mkdir(parents=True)
        runner = Runner(str(project), 'certified-minimum', str(target))
        selected = singular
        for case in selected:
            raw = case['query']
            query = parse_query(raw, 0)
            basis = [sum(1 << i for i in mono) for mono in query['basis']]
            polynomial = {sum(1 << i for i in mono): coefficient for mono, coefficient in query['terms']}
            assignment = solver.optimize(query['n'], polynomial, 5)
            ties = solver.equal_minima(query['n'], polynomial, assignment, 5)
            source = runner.file(raw['id'] + '.json', json.dumps(dict(version=1, queries=[raw])).encode())
            output = runner.home / (raw['id'] + '.jsonl')
            measured = runner.call(['--input', source, '--output', output])
            assert success(measured) and not measured['stdout'] and output.is_file()
            answers = [json.loads(line) for line in output.read_text().splitlines()]
            assert len(answers) == 1
            answer = answers[0]
            point, proof, evidence = check(raw, answer, case['optimum'])
            assert point
            events = []
            for line in measured['stderr'].decode(errors='replace').splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
            if profile == 'standard':
                assert answer['state'] == 'CERTIFIED' and proof
                assert not ties, 'singular fixtures no longer exercise the zero-tie path'
            elif profile == 'short-budget':
                assert not ties
                if answer['state'] == 'INCUMBENT':
                    assert not proof
                    assert any(event.get('event') == 'certificate_incomplete' for event in events)
            else:
                assert answer['state'] == 'CERTIFIED' and proof
                assert [event['attempt'] for event in events if event.get('event') == 'author_fault_injection'] == [1, 2]
                assert any(event.get('event') == 'certificate_attempt_failed' and event.get('reason') == 'TimeoutError' for event in events)
            (target / (raw['id'] + '.jsonl')).write_bytes(output.read_bytes())
            (target / (raw['id'] + '.stderr')).write_bytes(measured['stderr'])
            records.append(dict(profile=profile, id=raw['id'], state=answer['state'],
                                point=point, proof=proof, ties=0 if profile == 'empty-ties-retry' else len(ties),
                                budget_sec=1.0 if profile == 'short-budget' else 260.0,
                                elapsed_sec=measured['elapsed_seconds'], events=events,
                                fault_injection=profile == 'empty-ties-retry', evidence=evidence))
        shutil.copytree(runner.private, target / 'measurements')
    failures = [record for record in records if record['profile'] == 'short-budget' and record['state'] == 'INCUMBENT']
    assert {'eb014', 'eb015', 'eb017', 'eb018'}.issubset({record['id'] for record in failures})
    report = dict(status='PASS', scope='NON_SCORING_AUTHOR_REGRESSION', records=records,
                  short_budget_counterexamples=len(failures), formal_platform_t1=False)
    (results / 'certificate_regressions.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
