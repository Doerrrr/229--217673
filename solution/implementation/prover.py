"""Exact integer cost search followed by a checked lower-bound DRAT proof."""
import subprocess
from pathlib import Path
from phase_codec import encode, evaluate, statement
from core import Failure, require, atomic_bytes

def solve_once(model,bound,work,proof=False):
    raw,mapping=encode(model,bound);cnf=Path(work)/'problem.cnf';atomic_bytes(cnf,raw)
    args=['cadical','--no-binary',str(cnf)]
    if proof:args.append(str(Path(work)/'certificate.drat'))
    try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
    except subprocess.TimeoutExpired as e:raise Failure(8,'solver did not finish certification') from e
    if p.returncode not in (10,20):raise Failure(8,'solver returned no certified status')
    assignment=None
    if p.returncode==10:
        positive=set()
        for line in p.stdout.splitlines():
            if line.startswith(b'v '):positive.update(int(v) for v in line[2:].split() if int(v)>0)
        assignment={name:int(index in positive) for name,index in mapping.items()}
        valid,cost,_=evaluate(model,assignment);require(valid and (bound is None or cost<=bound),'solver witness is invalid',8)
    return p.returncode==10,assignment

def check_certificate(raw,path,work):
    path=Path(path);require(path.is_file() and path.stat().st_size<=256*1024*1024,'certificate is missing or too large',5)
    try:
        with path.open('rb') as f:
            while block:=f.read(1024*1024):require(all(b in (9,10,13,32,45,100) or 48<=b<=57 for b in block),'not ASCII DRAT',5)
        cnf=Path(work)/'checked.cnf';atomic_bytes(cnf,raw)
        p=subprocess.run(['drat-trim',str(cnf),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
    except subprocess.TimeoutExpired as e:raise Failure(8,'certificate checker timeout') from e
    # This pinned DRAT-trim returns 1 (not 0) for a formula already containing
    # the empty clause. Its explicit VERIFIED verdict remains authoritative.
    require(p.returncode in (0,1) and b's VERIFIED' in p.stdout.splitlines() and b's NOT VERIFIED' not in p.stdout.splitlines(),'DRAT proof is not valid for this declaration',5)

def optimize(model,work):
    feasible,point=solve_once(model,None,work)
    if not feasible:decision=dict(status='UNSAT',assignment=None,dropped=None,cost=None)
    else:
        high=evaluate(model,point)[1];low=0
        while low<high:
            mid=(low+high)//2;sat,trial=solve_once(model,mid,work)
            if sat:point=trial;high=evaluate(model,point)[1]
            else:low=mid+1
        decision=dict(status='SAT' if high==0 else 'REPAIRED',assignment=point,dropped=[],cost=high)
    claim,cnf=statement(model,decision['status'],decision['cost'])
    if decision['cost']==0:atomic_bytes(Path(work)/'certificate.drat',b'0\n')
    else:
        sat,_=solve_once(model,claim['bound'],work,True);require(not sat,'claimed cost is not optimal',8)
    check_certificate(cnf,Path(work)/'certificate.drat',work)
    return decision,claim
