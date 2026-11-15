"""Author regressions for v05 Oracle, runtime faults and public CLI boundaries."""
import argparse,copy,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,tempfile,time
from fractions import Fraction
from pathlib import Path

def sha(raw):return hashlib.sha256(raw).hexdigest()
def dump(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def require(condition,message):
    if not condition:raise AssertionError(message)
def own(p):
    os.chown(p,10001,10001)
    if p.is_dir():
        for item in p.rglob('*'):os.chown(item,10001,10001)

def score_controls(repo, results, workspace):
    records = []
    for profile in ('general', 'point', 'rounding', 'nop'):
        project = workspace / ('project-' + profile)
        shutil.copytree(repo / 'environment', project,
                        ignore=shutil.ignore_patterns('data', 'Dockerfile'))
        if profile != 'nop':
            for source in (repo / 'solution/implementation').glob('*.py'):
                shutil.copyfile(source, project / 'app' / source.name)
        if profile == 'point':
            main = project / 'app/main.py'
            code = main.read_text()
            wrapper = """from solver import optimize, string_of, value_at

def solve(query, budget):
    qid, n, basis, polynomial = query
    assignment = optimize(n, polynomial, min(10, budget))
    return dict(id=qid, state='INCUMBENT', assignment=assignment,
                value=string_of(value_at(polynomial, assignment)), gram=None)

"""
            main.write_text(code.replace("if __name__ == '__main__':", wrapper + "if __name__ == '__main__':"))
        if profile == 'rounding':
            recovery = project / 'app/recovery.py'
            recovery.write_text(recovery.read_text() + "\n\ndef recover_gram(basis, poly, assignment, approximate, deadline, solver):\n    return None\n")
        target = results / ('scoring-' + profile)
        got = subprocess.run([sys.executable, str(repo / 'tests/grade032.py'),
                              '--project', str(project), '--results', str(target)],
                             capture_output=True, timeout=1800)
        target.mkdir(parents=True, exist_ok=True)
        (target / 'grader-stdout.txt').write_bytes(got.stdout)
        (target / 'grader-stderr.txt').write_bytes(got.stderr)
        require(got.returncode == 0, 'grader execution failed: ' + profile)
        record = json.loads((target / 'result.json').read_bytes())
        require(record['execution_status'] == 'NORMAL', 'abnormal control: ' + profile)
        require(len(record['cases']) == 82, 'v05 assertion count changed')
        groups = {g['name']: g for g in record['groups']}
        if profile == 'general':
            require(record['reward'] == 1.0, 'Oracle must score exactly 1.0')
            require(groups['witness']['passed'] == groups['witness']['total'], 'reference assignment regression')
            require(groups['failure']['passed'] == groups['failure']['total'], 'reference contract regression')
        elif profile == 'point':
            require(record['reward'] == 0.4, 'partial-credit regression')
        elif profile == 'rounding':
            require(record['reward'] < 0.7, 'direct-rounding control exceeds design threshold')
        else:
            require(record['reward'] == round(0.1 * 3 / 44, 6), 'empty scaffold control changed')
        records.append(dict(profile=profile, reward=record['reward'], groups=record['groups']))
    report = dict(status='PASS', records=records, scoring_version='v05',
                  formal_platform_t1=False, new_model_calls=0)
    dump(results / 'score_controls.json', report)
    return report


def runner_faults(repo,results,workspace):
    measure=repo/'tests/measure.py'
    # This test home must be reachable by UID10001; author fixture ancestors
    # deliberately remain 0700 and are never made candidate-readable.
    home=Path(tempfile.mkdtemp(prefix='eb032-fault-home-',dir='/tmp'));own(home)
    records=[]
    def run(name,code,seconds=5):
        out=results/'faults'/name;out.mkdir(parents=True)
        got=subprocess.run([sys.executable,str(measure),'publish',str(seconds),str(out/'stdout'),str(out/'stderr'),str(home),str(home),sys.executable,'-c',code],capture_output=True,timeout=20)
        require(got.returncode==0,got.stderr.decode(errors='replace'))
        r=json.loads(got.stdout.splitlines()[-1]);require(r['descendants_remaining']==0,'descendants survived')
        records.append(dict(name=name,**r));return r,out
    r,_=run('successful-exit','pass');require(r['returncode']==0 and not r['timed_out'],'normal status changed')
    r,_=run('failed-exit','raise SystemExit(7)');require(r['returncode']==7,'ordinary failure reclassified')
    r,_=run('command-timeout','import time;time.sleep(30)',1);require(r['timed_out'] and r['returncode']<0,'command not bounded')
    for detached in (False,True):
        name='detached-background' if detached else 'same-group-background'
        pidfile=home/(name+'.pid')
        code="import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session="+str(detached)+",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);Path("+repr(str(pidfile))+").write_text(str(p.pid))"
        r,_=run(name,code);pid=int(pidfile.read_text())
        require(r['returncode']==0 and not Path('/proc/'+str(pid)).exists(),name+' still alive')
    r,out=run('ordinary-stderr','import sys;sys.stderr.write("x"*2097152)')
    require(r['returncode']==0 and not r.get('log_truncated', False) and (out/'stderr').stat().st_size==2097152,'ordinary capture altered')
    # Exercise the real Runner classification, not just a helper boolean.
    sys.path.insert(0,str(repo/'tests'));from common import Runner
    project=workspace/'cap-project';shutil.copytree(repo/'environment',project,ignore=shutil.ignore_patterns('data','Dockerfile'))
    runner=Runner(str(project),'certified-minimum',str(results/'capture-classification'))
    r=runner.call([sys.executable,'-c','import os;block=b"x"*1048576\nfor i in range(80):os.write(1,block)'],absolute=True)
    require(r['log_truncated'] and r['captured_bytes']<=64*1024*1024 and bool(r['stdout']),'capture exceeded hard limit')
    runner.check('author','capture-guard',False)
    score=runner.save('AUTHOR_CAPTURE',{'author':1})
    require(score['reward']==0 and score['execution_status']=='NORMAL','diagnostic capture changed ordinary execution classification')
    records.append(dict(name='capture-limit',log_truncated=True,reward=0,captured_bytes=r['captured_bytes']))
    # A cleanup failure is never quietly accepted as a completed command.
    report=dict(status='PASS',records=records,capture_limit_is_for_stdout_stderr_not_answer_jsonl=True)
    dump(results/'runner_faults.json',report);return report

def checker_faults(repo,results):
    sys.path.insert(0,str(repo/'tests'));import guarded_check as guard
    cases=json.loads((repo/'tests/cases032.json').read_bytes())
    from algebra import check as direct
    guard.configure_results(results/'checker-normal')
    for c in cases:
        require(guard.check(c['query'],c['answer'],c['optimum'])==direct(c['query'],c['answer'],c['optimum']),'exact checker result changed')
    actual=guard._algebra_check;prior_timeout=guard.CHECK_TIMEOUT_SECONDS;prior_total=guard.CHECK_TOTAL_SECONDS
    records=[]
    try:
        guard.configure_results(results/'checker-timeout');guard.CHECK_TIMEOUT_SECONDS=.15
        guard._algebra_check=lambda *args:time.sleep(5)
        start=time.monotonic()
        try:guard.check(cases[0]['query'],cases[0]['answer'],cases[0]['optimum'])
        except guard.CheckerFailure:pass
        else:raise AssertionError('checker timeout converted to a mathematical result')
        require(time.monotonic()-start<3,'checker not terminated promptly')
        log=json.loads(next((results/'checker-timeout/checker').glob('*.json')).read_bytes())
        require(log['status']=='VERIFIER_CHECKER_ERROR' and log['reward'] is None,'checker timeout became zero')
        records.append(dict(name='independent-timeout',status=log['status'],reward=None))
        for name,callback in [('exception',lambda *args:(_ for _ in ()).throw(RuntimeError('author injected checker error'))),('abrupt-exit',lambda *args:os._exit(23))]:
            guard.configure_results(results/('checker-'+name));guard._algebra_check=callback
            try:guard.check(cases[0]['query'],cases[0]['answer'],cases[0]['optimum'])
            except guard.CheckerFailure:pass
            else:raise AssertionError('checker '+name+' became a mathematical result')
            log=json.loads(next((results/('checker-'+name)/'checker').glob('*.json')).read_bytes())
            require(log['status']=='VERIFIER_CHECKER_ERROR' and log['reward'] is None,'checker '+name+' became a score')
            records.append(dict(name=name,status=log['status'],reward=None))
        guard.configure_results(results/'checker-budget');guard.CHECK_TOTAL_SECONDS=0
        try:guard.check(cases[0]['query'],cases[0]['answer'],cases[0]['optimum'])
        except guard.CheckerFailure:pass
        else:raise AssertionError('aggregate checker budget ignored')
        records.append(dict(name='aggregate-budget',status='VERIFIER_CHECKER_ERROR'))
    finally:
        guard._algebra_check=actual;guard.CHECK_TIMEOUT_SECONDS=prior_timeout;guard.CHECK_TOTAL_SECONDS=prior_total
    report=dict(status='PASS',all_18_direct_checks_equal=True,faults=records)
    dump(results/'checker_faults.json',report);return report

def reference_boundaries(repo,results,workspace):
    sys.path.insert(0,str(repo/'solution/implementation'));from interface import parse_document
    checks=[]
    base=dict(id='edge',n=2,basis=[[],[0],[1]],terms=[dict(vars=[],coef='1')])
    def parse(name,queries,valid):
        try:parse_document(json.dumps(dict(version=1,queries=queries)))
        except Exception:
            require(not valid,'valid input rejected: '+name)
        else:require(valid,'invalid input accepted: '+name)
        checks.append(dict(name=name,expected_valid=valid))
    for value in ('1/-2','-1/-2','1/+2','1/0','-3/7','+05/10','1/'+'9'*78):
        q=copy.deepcopy(base);q['terms'][0]['coef']=value
        parse('rational-'+value[:12],[q],value not in ('1/-2','-1/-2','1/+2','1/0'))
    q=copy.deepcopy(base);q['n']=1;parse('n-lower-invalid',[q],False)
    q=copy.deepcopy(base);q['n']=33;parse('n-upper-invalid',[q],False)
    q=dict(id='n32',n=32,basis=[[]]+[[i] for i in range(32)]+[[0,i] for i in range(1,32)]+[[1,2]],terms=[dict(vars=[],coef='1')])
    require(len(q['basis'])==65,'fixture');parse('n32-basis65',[q],True)
    q['basis'].append([1,3]);parse('basis66',[q],False)
    from itertools import combinations
    monomials = [list(m) for degree in range(5) for m in combinations(range(32), degree)]
    q = dict(id='terms_limit', n=32, basis=[[]]+[[i] for i in range(32)],
             terms=[dict(vars=m, coef='1') for m in monomials[:32768]])
    parse('terms32768', [q], True)
    q['terms'].append(dict(vars=monomials[32768], coef='1'))
    parse('terms32769', [q], False)
    q=copy.deepcopy(base);q['terms'][0]['coef']='0'*79+'1';parse('coefficient80',[q],True)
    q['terms'][0]['coef']='0'*80+'1';parse('coefficient81',[q],False)
    q=copy.deepcopy(base);q['id']='i'*64;parse('id64',[q],True)
    q['id']='i'*65;parse('id65',[q],False)
    many=[{**base,'id':'q'+str(i)} for i in range(16)];parse('queries16',many,True);parse('queries17',many+[{**base,'id':'last'}],False)
    # Use the real author reference under candidate UID, including denied writes.
    project=workspace/'reference';shutil.copytree(repo/'environment',project,ignore=shutil.ignore_patterns('data','Dockerfile'))
    for p in (repo/'solution/implementation').glob('*'):
        if p.is_file():shutil.copyfile(p,project/'app'/p.name)
    from common import Runner
    runner=Runner(str(project),'certified-minimum',str(results/'reference-boundaries'))
    c=json.loads((repo/'tests/cases032.json').read_bytes())[0]
    source=runner.file('valid.json',json.dumps(dict(version=1,queries=[c['query']])).encode())
    denied=runner.home/'denied';denied.mkdir(mode=0o555);os.chown(denied,0,0)
    got=runner.call(['--input',str(source),'--output',str(denied/'answer.jsonl')])
    require(got['returncode']!=0 and got['stdout']==b'' and got['stderr'].strip(),'write failure accepted')
    checks.append(dict(name='output-permission-denied',expected_valid=False))
    sentinel=runner.file('blocked-parent',b'KEEP_PARENT');got=runner.call(['--input',str(source),'--output',str(sentinel/'answer.jsonl')])
    require(got['returncode']!=0 and sentinel.read_bytes()==b'KEEP_PARENT','invalid output parent damaged')
    checks.append(dict(name='output-parent-is-file',expected_valid=False))
    target=runner.directory('directory-target');sentinel=runner.file('directory-target/sentinel',b'KEEP_CHILD')
    got=runner.call(['--input',str(source),'--output',str(target)])
    require(got['returncode']!=0 and sentinel.read_bytes()==b'KEEP_CHILD','failed atomic replacement damaged old directory')
    checks.append(dict(name='atomic-replacement-fails',expected_valid=False))
    for value in ('1/-2','1/0'):
        q=copy.deepcopy(c['query']);q['terms'][0]['coef']=value
        bad=runner.file('bad.json',json.dumps(dict(version=1,queries=[q])).encode());old=runner.file('old',b'OLD_SENTINEL')
        got=runner.call(['--input',str(bad),'--output',str(old)])
        require(got['returncode']!=0 and b'coef' in got['stderr'] and not got['stdout'] and old.read_bytes()==b'OLD_SENTINEL','rational boundary diagnostic')
        checks.append(dict(name='cli-rational-'+value,field_diagnostic=True,old_output_preserved=True))
    report=dict(status='PASS',checks=checks,scope='NON_SCORING_AUTHOR_REFERENCE_REGRESSIONS',candidate_scoring_cases_added=0)
    dump(results/'reference_boundaries.json',report);return report

def generated_reference_checks(repo, results, workspace):
    import random
    from collections import defaultdict
    sys.path.insert(0, str(repo / 'tests'))
    from algebra import check
    from common import Runner, success
    project = workspace / 'generated-reference'
    shutil.copytree(repo / 'environment', project, ignore=shutil.ignore_patterns('data', 'Dockerfile'))
    for source in (repo / 'solution/implementation').glob('*.py'):
        shutil.copyfile(source, project / 'app' / source.name)
    runner = Runner(str(project), 'certified-minimum', str(results / 'generated-runtime'))
    records = []
    for seed, n, pair_count, rank in [(701, 4, 0, 4), (702, 4, 3, 7),
                                       (703, 4, 3, 2), (704, 8, 4, 12),
                                       (705, 8, 4, 3), (706, 6, 3, 9),
                                       (707, 8, 6, 3), (708, 8, 6, 2)]:
        rng = random.Random(seed)
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        rng.shuffle(pairs)
        basis = [()] + [(i,) for i in range(n)] + pairs[:pair_count]
        if seed >= 707:
            reordered = basis[1:]
            rng.shuffle(reordered)
            basis = [()] + reordered
        masks = [sum(1 << i for i in mono) for mono in basis]
        dimension = len(basis) - 1
        coefficients = defaultdict(Fraction)
        coefficients[0] = Fraction(-3, 7)
        for row in range(rank):
            bound = 10000 if seed >= 707 else 2
            values = [rng.randint(-bound, bound) for _ in range(dimension)]
            if rank == dimension:
                values = [0 if j > row else values[j] for j in range(dimension)]
                values[row] = 3
            vector = [-sum(values)] + values
            weight = Fraction(1, (1, 17**2, 257**2)[row]) if seed == 707 else 1
            for i, left in enumerate(vector):
                for j, right in enumerate(vector):
                    coefficients[masks[i] ^ masks[j]] += weight * left * right
        query = dict(id='generated_%d' % seed, n=n, basis=[list(v) for v in basis],
                     terms=[dict(vars=[i for i in range(n) if mask >> i & 1], coef=str(value))
                            for mask, value in sorted(coefficients.items()) if value])
        source = runner.file(query['id'] + '.json', json.dumps(dict(version=1, queries=[query])).encode())
        output = runner.home / (query['id'] + '.jsonl')
        got = runner.call(['--input', source, '--output', output])
        require(success(got) and not got['stdout'] and output.is_file(), 'generated CLI failure')
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        require(len(rows) == 1, 'generated row count')
        point, proof, evidence = check(query, rows[0], '-3/7')
        require(point and proof, 'generated exact certificate missing: ' + query['id'] + ' ' + str(evidence))
        records.append(dict(id=query['id'], n=n, basis_size=len(basis), rank=rank,
                            state=rows[0]['state'], input_sha256=sha(source.read_bytes())))
    require(any(r['state'] == 'CERTIFIED' and r['basis_size'] > r['n'] + 1 for r in records), 'quartic certificate capability missing')
    report = dict(status='PASS', records=records, source='GENERATED_FROM_EXACT_SUMS_OF_SQUARES',
                  cases032_used_for_generation=False, formal_platform_t1=False)
    dump(results / 'generated_reference.json', report)
    shutil.copytree(runner.private, results / 'generated-calls')
    return report


def exact_search_checks(repo, results):
    import random
    sys.path.insert(0, str(repo / 'solution/implementation'))
    import solver
    rng = random.Random(20261114)
    records = []
    for n in range(2, 9):
        polynomial = {mask: Fraction(rng.randint(-20, 20), rng.randint(1, 23))
                      for mask in range(1 << n) if mask.bit_count() <= 4}
        values, common = solver.boolean_values(n, polynomial)
        for bits, value in enumerate(values):
            assignment = [1 - 2 * (bits >> i & 1) for i in range(n)]
            require(Fraction(value, common) == solver.value_at(polynomial, assignment),
                    'exact Boolean transform differs from direct evaluation')
        assignment = solver.optimize(n, polynomial, 1)
        require(solver.value_at(polynomial, assignment) == Fraction(min(values), common),
                'exact assignment search lost the minimum')
        records.append(dict(n=n, points_checked=len(values)))
    require(solver.boolean_values(15, {0: Fraction(1)}) is None, 'enumeration bound changed')
    report = dict(status='PASS', records=records, method='exact transform versus direct rational sum')
    dump(results / 'exact_search.json', report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--results',type=Path,required=True);a=p.parse_args()
    os.chmod('/root',0o700);a.results.mkdir(parents=True,exist_ok=True);os.chmod(a.results,0o700)
    start=time.monotonic();workspace=Path(tempfile.mkdtemp(prefix='eb032-author-',dir='/tmp'));workspace.chmod(0o700)
    manifest=json.loads((a.repo/'validation/eb032_platform/payload.json').read_bytes())
    require(all(sha((a.repo/n).read_bytes())==v for n,v in manifest['files'].items()),'payload hash mismatch')
    baseline=json.loads((a.repo/'validation/eb032_platform/author_baseline/source.json').read_bytes())
    require(all(sha((a.repo/'validation/eb032_platform/author_baseline'/n).read_bytes())==v for n,v in baseline['files'].items()),'baseline fixture changed')
    report=dict(status='IN_PROGRESS',scope='AUTHOR_REGRESSION_ONLY',formal_platform_t1=False,new_model_calls=0)
    dump(a.results/'summary.json',report)
    report['score_controls']=score_controls(a.repo,a.results,workspace)
    report['runner_faults']=runner_faults(a.repo,a.results,workspace)
    report['checker_faults']=checker_faults(a.repo,a.results)
    report['reference_boundaries']=reference_boundaries(a.repo,a.results,workspace)
    report['exact_search']=exact_search_checks(a.repo,a.results)
    from certificate_regressions import run as certificate_regressions
    report['certificate_regressions']=certificate_regressions(a.repo,a.results,workspace)
    report['generated_reference']=generated_reference_checks(a.repo,a.results,workspace)
    identity_result=a.results/'output_reader_identities.json'
    subprocess.run([sys.executable,str(a.repo/'validation/eb032_platform/identity_checks.py'),
                    '--tests',str(a.repo/'tests'),'--results',str(identity_result)],
                   check=True,timeout=30)
    report['output_reader_identities']=json.loads(identity_result.read_bytes())
    report.update(status='PASS',seconds=time.monotonic()-start,payload_digest=manifest['payload_digest'],
                  cases_sha256=sha((a.repo/'tests/cases032.json').read_bytes()),old_t1_candidates_replayed=False)
    dump(a.results/'summary.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
