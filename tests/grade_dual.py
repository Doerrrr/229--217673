"""Isolated candidate build and full dual-publication verifier entrypoint."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SAFE=['/usr/bin/setpriv','--reuid=10001','--regid=10001','--clear-groups','--no-new-privs','--']

def main():
    p=argparse.ArgumentParser()
    for name in ('starter','private','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--overlay',type=Path)
    args=p.parse_args();os.chmod('/locked',0o700)
    args.out.mkdir(exist_ok=True)
    guard=subprocess.run(SAFE+[sys.executable,'-c',
        "import os;assert os.getuid()==10001 and os.getgid()==10001 and os.getgroups()==[];assert not os.access('/locked/private',os.R_OK);assert not os.access('/locked/results',os.W_OK)"],capture_output=True)
    assert guard.returncode==0,'private grading boundary failed'
    with tempfile.TemporaryDirectory(prefix='ddi019-dual-grade-') as temporary:
        root=Path(temporary);root.chmod(0o755);project=root/'project';project.mkdir()
        for source in (args.starter,args.overlay):
            if source is None:continue
            for file in source.rglob('*'):
                if file.is_dir():continue
                assert file.is_file() and not file.is_symlink()
                relative=file.relative_to(source)
                if source==args.starter and relative.parts[0] not in ('src','app','bin','Makefile'):continue
                if source==args.overlay and relative.parts[0] not in ('src','app','bin','Makefile','tests'):raise ValueError('answer modifies outside public engineering boundary')
                target=project/relative
                assert target.resolve().is_relative_to(project.resolve())
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
                target.chmod(0o755 if relative.parts[0]=='bin' or file.suffix=='.sh' else 0o644)
        for file in (project,*project.rglob('*')):os.chown(file,10001,10001)
        built=subprocess.run(SAFE+['make','-B'],cwd=project,capture_output=True,timeout=180)
        (args.out/'build.stdout').write_bytes(built.stdout);(args.out/'build.stderr').write_bytes(built.stderr)
        if built.returncode:
            result={'task_id':'DDI-019','version':'v02','execution_status':'BUILD_FAILURE',
                    'reward':None,'model_calls':0,'formal_platform_t1':False}
        else:
            runner=args.out/'measured-process';writer=args.out/'finite-resource-writer'
            for source,target in [('measured_process.c',runner),('finite_resource_writer.c',writer)]:
                compiled=subprocess.run(['gcc','-O2','-Werror','-Wall','-Wextra',str(args.private/source),'-o',str(target)],capture_output=True)
                assert compiled.returncode==0,compiled.stderr.decode()
            sys.path.insert(0,str(args.private))
            from native_process import Native
            from evaluate_dual import evaluate
            from resource_checks import measured_resource_cases
            native=Native(project/'cohort-release',runner,root,args.out,'/work/bcftools-1.20/bcftools')
            try:
                result=evaluate(native,Path('/packet/clients/read_store.py'),
                                lambda n:measured_resource_cases(n,writer))
                result['version']='v02'
            finally:native.cleanup()
            result.update(native_build='PASS',private_guard='PASS',full_verifier=True)
        (args.out/'driver_result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:result.get(k) for k in ('execution_status','reward','native_build','full_verifier')}),flush=True)

if __name__=='__main__':main()
