"""Non-scoring author regressions: invariant scores, resource faults and CLI edges."""
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

CONTROL='''import argparse,copy,hashlib,json,sys
from pathlib import Path
def sig(q):return hashlib.sha256(json.dumps(q,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def pairs(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        obj=json.loads(Path(a.input).read_bytes().decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
        if set(obj)!={'version','queries'} or type(obj['version']) is not int or obj['version']!=1 or not 1<=len(obj['queries'])<=16:raise ValueError('document')
        if len({q['id'] for q in obj['queries']})!=len(obj['queries']):raise ValueError('duplicate id')
        registry=json.loads(Path(__file__).with_name('registry.json').read_bytes())
        rows=[registry[sig(q)] for q in obj['queries']]
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(''.join(json.dumps(r)+'\\n' for r in rows))
    except Exception as e:print(str(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
'''

def score_equivalence(repo,results,workspace):
    tests=repo/'tests';baseline=workspace/'baseline';baseline.mkdir()
    for p in (repo/'validation/eb032_platform/author_baseline').glob('*.py'):shutil.copyfile(p,baseline/p.name)
    shutil.copyfile(tests/'cases032.json',baseline/'cases032.json')
    cases=json.loads((tests/'cases032.json').read_bytes());records=[]
    expected={'nop':0.0,'point':.4,'quadratic':.55,'finite':1.0,'wrong_identity':.4,'indefinite':.4}
    for profile in expected:
        project=workspace/('project-'+profile);shutil.copytree(repo/'environment',project,ignore=shutil.ignore_patterns('data','Dockerfile'))
        if profile!='nop':
            (project/'app/main.py').write_text(CONTROL)
            registry={}
            for c in cases:
                row=copy.deepcopy(c['answer'])
                if profile=='point' or (profile=='quadratic' and c['group']!='quadratic_proof'):row.update(state='INCUMBENT',gram=None)
                if profile=='wrong_identity':row['gram'][0][0]=str(Fraction(row['gram'][0][0])+Fraction(1,10**40))
                if profile=='indefinite':
                    move=abs(Fraction(row['gram'][0][0]))+1
                    row['gram'][0][0]=str(Fraction(row['gram'][0][0])-move)
                    row['gram'][1][1]=str(Fraction(row['gram'][1][1])+move)
                key=sha(json.dumps(c['query'],sort_keys=True,separators=(',',':')).encode());registry[key]=row
            dump(project/'app/registry.json',registry)
        paired=[]
        for label,grader in [('baseline',baseline),('revised',tests)]:
            target=results/'equivalence'/profile/label
            got=subprocess.run([sys.executable,str(grader/'grade032.py'),'--project',str(project),'--results',str(target)],capture_output=True,timeout=600)
            target.mkdir(parents=True,exist_ok=True)
            (target/'driver.stdout').write_bytes(got.stdout);(target/'driver.stderr').write_bytes(got.stderr)
            require(got.returncode==0,got.stderr.decode(errors='replace')[-4000:])
            r=json.loads((target/'result.json').read_bytes())
            if label=='revised':
                provenance=subprocess.run([sys.executable,str(tests/'provenance.py'),'--results',str(target)],capture_output=True,timeout=15)
                require(provenance.returncode==0,provenance.stderr.decode(errors='replace'))
                r=json.loads((target/'result.json').read_bytes())
                observed=r['verification_provenance']
                require(len(observed['inputs'])==47 and observed['source_files_sha256']['cases032.json']==sha((tests/'cases032.json').read_bytes()),'runtime provenance missing')
                require(sum(v['input_sha256'] is not None for v in observed['inputs'])==44,'CLI input digests not captured')
            require(r['execution_status']=='NORMAL' and r['reward']==expected[profile],profile+': '+str(r))
            require(len(r['cases'])==66,'scored assertion count changed')
            paired.append(r)
        require(paired[0]['groups']==paired[1]['groups'] and paired[0]['cases']==paired[1]['cases'],'graded evidence changed: '+profile)
        records.append(dict(profile=profile,baseline=paired[0]['reward'],revised=paired[1]['reward'],all_66_assertions_and_groups_equal=True))
        dump(results/'score_equivalence.json',dict(status='IN_PROGRESS',records=records))
        print(json.dumps(dict(event='SCORE_EQUIVALENCE',**records[-1])),flush=True)
    report=dict(status='PASS',records=records,paired_grader_runs=12,total_scored_assertions=12*66,
                scope='AUTHOR_CONTROLS_ONLY_NOT_REPLAYS_OF_PLATFORM_CANDIDATES',model_calls=0)
    dump(results/'score_equivalence.json',report);return report

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
    report['score_equivalence']=score_equivalence(a.repo,a.results,workspace)
    report['runner_faults']=runner_faults(a.repo,a.results,workspace)
    report['checker_faults']=checker_faults(a.repo,a.results)
    report['reference_boundaries']=reference_boundaries(a.repo,a.results,workspace)
    report.update(status='PASS',seconds=time.monotonic()-start,payload_digest=manifest['payload_digest'],
                  cases_sha256=sha((a.repo/'tests/cases032.json').read_bytes()),old_t1_candidates_replayed=False)
    dump(a.results/'summary.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
