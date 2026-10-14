"""Verifier safety probe only; no candidate score or answer-model call."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path('/author');runner=Path('/tmp/ddi018-fixed-id-runner')
build=subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror',ROOT/'tests/rss_runner.c','-o',runner],capture_output=True)
assert build.returncode==0,build.stderr.decode()
with tempfile.TemporaryDirectory(prefix='ddi018-uid-probe-') as temporary:
    root=Path(temporary);root.chmod(0o755);checks=[]
    for identity in ('-1','0','65535','65536','999999999999999999999999','abc','10001x'):
        stdout=root/(identity+'.stdout');stderr=root/(identity+'.stderr')
        p=subprocess.run([runner,'10',stdout,stderr,identity,'/bin/true'],capture_output=True,timeout=15)
        assert p.returncode==125 and not stdout.exists() and not stderr.exists()
        checks.append({'uid_argument':identity,'rejected_before_files_and_process':True})
    stdout=root/'valid.stdout';stderr=root/'valid.stderr'
    p=subprocess.run([runner,'10',stdout,stderr,'10001','python3','-c',
                      "import os; assert os.getuid()==10001 and os.getgid()==10001 and os.getgroups()==[]; print('FIXED_UID_GID_AND_EMPTY_GROUPS')"],
                     capture_output=True,timeout=15)
    result=json.loads(p.stdout)
    assert p.returncode==0 and result['returncode']==0 and not result['timed_out']
    assert stdout.read_text().strip()=='FIXED_UID_GID_AND_EMPTY_GROUPS'
    assert stderr.read_bytes()==b''
print(json.dumps({'status':'PASS','fixed_uid_gid':10001,'supplementary_groups':[],
                  'rejected_arguments':checks,'allowed_identity_normal_completion':True,'model_calls':0}))
