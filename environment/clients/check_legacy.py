"""Old automation's public compatibility smoke, not a new-domain scorer."""
from pathlib import Path
import json
import subprocess

project=Path(__file__).resolve().parents[1]
p=subprocess.run([str(project/'bin/phase-lab'),'legacy-export','--input',str(project/'packet/legacy.json')],capture_output=True)
assert p.returncode==0,p.stderr
obj=json.loads(p.stdout)
assert obj['assignment']=={'a':0,'b':1,'c':0}
assert obj['calls'][0]['gt']=='1|0'
print('legacy consumer: PASS')
