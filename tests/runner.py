"""Private fixed-UID runner, independent of the candidate's implementation."""
from pathlib import Path
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

class Runner:
    def __init__(self,project,results):
        self.root=Path(tempfile.mkdtemp(prefix='ddi033-'));self.root.chmod(0o755)
        self.home=self.root/'candidate';self.home.mkdir();self.project=self.home/'project'
        shutil.copytree(project,self.project,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        self.logs=self.root/'private';self.logs.mkdir(mode=0o700);self.results=Path(results);self.results.mkdir(parents=True,exist_ok=True)
        self.own(self.home);self.number=0;self.jobs=[];self.records=[];self.runtime=[]
        for p in (self.project/'bin').iterdir():p.chmod(0o755)
        self.command=[str(self.project/'bin/phase-lab')]
        if (self.project/'build.sh').exists():
            result=self.call(['bash',str(self.project/'build.sh')],absolute=True);assert result['returncode']==0,'candidate build failed'

    def own(self,path):
        os.chown(path,10001,10001,follow_symlinks=False)
        if path.is_dir():
            for p in path.rglob('*'):os.chown(p,10001,10001,follow_symlinks=False)

    def directory(self,name):
        p=self.home/name;p.mkdir(parents=True,exist_ok=True);self.own(p);return p

    def file(self,name,raw):
        p=self.home/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);self.own(p.parent);return p

    def start(self,args,absolute=False,env=None):
        self.number+=1;stem=self.logs/f'{self.number:04d}';cmd=list(map(str,args)) if absolute else self.command+list(map(str,args))
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('meter.py')),str(stem),str(self.home),str(self.project),json.dumps(env or {}),*cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        first=process.stdout.readline();identity=json.loads(first)
        job=dict(process=process,group=identity['group'],stem=stem,command=cmd);self.jobs.append(job);return job

    def finish(self,job,killed=False):
        if 'result' in job:return job['result']
        output,error=job['process'].communicate(timeout=190)
        assert job['process'].returncode==0,('measurement failed',output,error)
        result=json.loads(output);result['stdout']=Path(str(job['stem'])+'.out').read_bytes();result['stderr']=Path(str(job['stem'])+'.err').read_bytes()
        if result['timed_out'] or result['residual_processes'] or (result['returncode']<0 and (not killed or result['returncode']!=-9)):self.runtime.append(dict(command=job['command'],**{k:v for k,v in result.items() if k not in ('stdout','stderr')}))
        log={k:v for k,v in result.items() if k not in ('stdout','stderr')};log.update(command=job['command'],intentional_kill=killed)
        Path(str(job['stem'])+'.json').write_text(json.dumps(log,indent=2));job['result']=result;return result

    def call(self,args,absolute=False,env=None):return self.finish(self.start(args,absolute,env))

    def kill(self,job):
        try:os.killpg(job['group'],signal.SIGKILL)
        except ProcessLookupError:pass
        return self.finish(job,True)

    def ready(self,job,path):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if path.is_file():return json.loads(path.read_bytes())
            if job['process'].poll() is not None:return None
            time.sleep(.01)
        return None

    def close(self):
        for job in self.jobs:
            if 'result' not in job:self.kill(job)

    def save(self,weights):
        self.close();groups=[]
        for name,weight in weights.items():
            selected=[r for r in self.records if r['group']==name];assert selected
            passed=sum(r['passed'] for r in selected);groups.append(dict(name=name,weight=weight,passed=passed,total=len(selected),earned=weight*passed/len(selected),aggregation='PROPORTIONAL'))
        result=dict(task='DDI-033',version='v01',execution_status='CANDIDATE_RUNTIME_ERROR' if self.runtime else 'NORMAL',reward=None if self.runtime else round(sum(r['earned'] for r in groups),8),groups=groups,cases=self.records,runtime_issues=self.runtime,model_calls=0,formal_platform_t1=False)
        shutil.copytree(self.logs,self.results/'runtime');(self.results/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('cases','runtime_issues')},ensure_ascii=False),flush=True)
        return result

def good(value):
    assert value['returncode']==0 and not value['timed_out'],dict(code=value['returncode'],stderr=value['stderr'][:1000].decode(errors='replace'))
    return json.loads(value['stdout']) if value['stdout'].strip() else None

def rejected(value,code):assert value['returncode']==code and not value['stdout'] and value['stderr'].strip(),(value['returncode'],value['stdout'],value['stderr'])
