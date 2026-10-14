"""Frozen finite business evaluation. No source-to-release reference program."""
import json
from pathlib import Path
import subprocess
import time
from fixtures import CASES, vcf_bytes
from business_checks import accepts

GROUPS=(('projection',.45),('priority',.25),('grouping',.15),('resources',.10),('completion',.05))


class Native:
    def __init__(self,binary,codec,root,runner,receipts):
        self.binary,self.codec,self.root,self.runner,self.receipts=binary,codec,root,runner,receipts
        self.calls=[];self.abnormal=[]

    def invoke(self,label,manifest,selected,limit=180):
        stdout=self.receipts/(label+'.stdout');stderr=self.receipts/(label+'.stderr')
        p=subprocess.run([self.runner,str(limit),stdout,stderr,'10001',self.binary,
                          '--manifest',str(manifest),'--samples',','.join(selected)],capture_output=True,timeout=limit+15)
        if p.returncode:raise RuntimeError('author measuring process failed: '+p.stderr.decode(errors='replace'))
        result=json.loads(p.stdout);result.update(stdout=stdout,stderr=stderr.read_text(errors='replace'))
        self.calls.append({key:str(value) if isinstance(value,Path) else value for key,value in result.items()})
        if result['timed_out'] or result['returncode']<0:self.abnormal.append({'case':label,**result})
        return result

    def __call__(self,case):
        directory=self.root/case.name;directory.mkdir();directory.chmod(0o755)
        paths=[]
        for i,batch in enumerate(case.batches):
            path=directory/('source_'+str(i)+'.vcf')
            if batch.fault!='missing':
                raw=vcf_bytes(batch)
                if batch.fault=='header':raw=b'not a VCF header\n'
                elif batch.fault=='columns':raw=b'\n'.join(line.rsplit(b'\t',1)[0] if not line.startswith(b'#') else line for line in raw.splitlines())+b'\n'
                path.write_bytes(raw);path.chmod(0o444)
                if batch.encoding in ('bcf','vcfgz'):
                    converted=path.with_suffix('.bcf' if batch.encoding=='bcf' else '.vcf.gz')
                    p=subprocess.run([self.codec,'view','-Ob' if batch.encoding=='bcf' else '-Oz','-o',converted,path],capture_output=True,timeout=60)
                    if p.returncode:raise RuntimeError('author BCF fixture conversion failed: '+p.stderr.decode())
                    converted.chmod(0o444);path=converted
            paths.append(path.name if case.relative else str(path))
        manifest=directory/'batches.tsv'
        manifest.write_text('source\tpath\n'+''.join(batch.source+'\t'+path+'\n' for batch,path in zip(case.batches,paths)))
        manifest.chmod(0o444)
        result=self.invoke(case.name,manifest,case.selected)
        if case.success and result['returncode']!=0:self.abnormal.append({'case':case.name,'reason':'valid_input_nonzero'})
        try:result['rows']=[json.loads(line) for line in result['stdout'].read_bytes().splitlines()]
        except (ValueError,UnicodeError):result['rows']=None
        return result


def evaluate(execute,resource_check):
    start=time.monotonic();groups=[]
    for group,weight in GROUPS:
        checks=[]
        if group=='resources':checks=resource_check(execute)
        else:
            for case in CASES[group]:
                result=execute(case)
                checks.append({'name':case.name,'passed':accepts(group,case,result),
                               'returncode':result['returncode'],'expected_success':case.success})
        passed=sum(c['passed'] for c in checks)
        groups.append({'name':group,'weight':weight,'passed':passed,'total':len(checks),
                       'earned':weight*passed/len(checks),'cases':checks})
    score=round(sum(g['earned'] for g in groups),6)
    abnormal=execute.abnormal
    return {'task_id':'DDI-018','version':'v01','execution_status':'ANSWER_RUNTIME_FAILURE' if abnormal else 'NORMAL',
            'reward':None if abnormal else score,'provisional_behavior_score':score,'groups':groups,
            'abnormal':[{k:str(v) if isinstance(v,Path) else v for k,v in r.items()} for r in abnormal],
            'calls':execute.calls,'model_calls':0,'formal_platform_t1':False,
            'elapsed_seconds':round(time.monotonic()-start,3)}
