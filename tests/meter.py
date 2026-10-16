"""wait4 peak RSS, fixed identity, no dynamically computed UID/GID operations."""
from pathlib import Path
import json
import os
import resource
import signal
import sys
import time

stem,home,cwd,extra,*command=sys.argv[1:]
pid=os.fork()
if pid==0:
    os.setsid();os.umask(0o077)
    for target,suffix in ((1,'.out'),(2,'.err')):
        fd=os.open(stem+suffix,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.dup2(fd,target);os.close(fd)
    settings=json.loads(extra);limit=settings.pop('PHASE_TEST_FILE_LIMIT',None)
    if limit is not None:
        signal.signal(signal.SIGXFSZ,signal.SIG_IGN);resource.setrlimit(resource.RLIMIT_FSIZE,(int(limit),int(limit)))
    os.chdir(cwd);os.environ.update(HOME=home,TMPDIR=home,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1');os.environ.update(settings)
    os.execv('/usr/bin/setpriv',['setpriv','--reuid=10001','--regid=10001','--clear-groups','--no-new-privs','--',*command])
print(json.dumps(dict(group=pid)),flush=True);start=time.monotonic();timeout=False
while True:
    finished,status,usage=os.wait4(pid,os.WNOHANG)
    if finished:break
    if time.monotonic()-start>180:
        timeout=True
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        _,status,usage=os.wait4(pid,0);break
    time.sleep(.01)
residual=[]
for path in Path('/proc').iterdir():
    if not path.name.isdecimal():continue
    try:
        # pgrp is field five; comm can contain spaces and parentheses.
        fields=(path/'stat').read_text().rsplit(')',1)[1].split()
        if int(fields[2])==pid and fields[0]!='Z':residual.append(int(path.name))
    except (OSError,ValueError,IndexError):pass
if residual:
    try:os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:pass
print(json.dumps(dict(returncode=os.waitstatus_to_exitcode(status),timed_out=timeout,peak_rss_kib=usage.ru_maxrss,elapsed_seconds=round(time.monotonic()-start,4),residual_processes=residual)),flush=True)
