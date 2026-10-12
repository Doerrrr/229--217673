"""Protected supervisor: expectations never enter the candidate native process."""
from __future__ import annotations
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from rdkit import Chem, RDLogger
from batch_model import Model, State, subset, verify_trace
from cases import WEIGHTS, all_cases

APP=Path("/opt/ddi-snapshot")
HERE=Path(__file__).resolve().parent
LOG=Path("/logs/verifier")
SENTINEL=0xFEDCBA9876543210


def restrict():
    resource.setrlimit(resource.RLIMIT_CPU,(140,140))
    resource.setrlimit(resource.RLIMIT_AS,(2_147_483_648,2_147_483_648))
    resource.setrlimit(resource.RLIMIT_FSIZE,(33_554_432,33_554_432))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.setgroups([]);os.setgid(65534);os.setuid(65534)


def run_process(command,input_bytes=None,timeout=30):
    with tempfile.TemporaryDirectory(prefix="ddi-native-worker-") as folder:
        root=Path(folder);os.chown(root,65534,65534);os.chmod(root,0o700)
        with (root/"stdout").open("wb") as out,(root/"stderr").open("wb") as err:
            started=time.monotonic()
            result=subprocess.run(command,input=input_bytes,stdout=out,stderr=err,
                                  cwd=root,timeout=timeout,preexec_fn=restrict,
                                  env={"PATH":"/usr/local/bin:/usr/bin:/bin","PYTHONDONTWRITEBYTECODE":"1"})
        output=(root/"stdout").read_bytes()
        error=(root/"stderr").read_bytes()[:4096].decode("utf-8",errors="replace")
        assert result.returncode==0, f"candidate process exit={result.returncode}: {error}"
        return output,time.monotonic()-started


def worker(library,request,timeout=30):
    payload=json.dumps(request,separators=(",",":")).encode()
    output,elapsed=run_process(["python",str(APP/"client.py"),"--library",str(library)],payload,timeout)
    return json.loads(output),elapsed


def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        for row in csv.reader(stream,strict=True):
            row=[v.strip() for v in row]
            if any(row):yield row


def chemical_operations():
    RDLogger.DisableLog("rdApp.error");structures=collections.defaultdict(set)
    for row in rows(Path("/data/drug_list.csv")):
        if row[0]:structures[row[0]]
        if len(row)!=2 or not all(row):continue
        mol=Chem.MolFromSmiles(row[1])
        if mol is not None:structures[row[0]].add(Chem.MolToSmiles(mol,canonical=True,isomericSmiles=True))
    ids={key:i+1 for i,key in enumerate(sorted(structures))}
    unique={next(iter(value)) for value in structures.values() if len(value)==1}
    molecule={key:i+1 for i,key in enumerate(sorted(unique))}
    descriptions=collections.defaultdict(set)
    for row in rows(Path("/data/DDI_event.csv")):
        if len(row)==2 and row[0].isascii() and row[0].isdecimal() and row[1]:descriptions[int(row[0])].add(row[1])
    bulk=[]
    for key,values in structures.items():
        state=1 if len(values)==1 else 2 if values else 3
        bulk.append(["bind","t",ids[key],state,molecule[next(iter(values))] if state==1 else 0])
    bulk += [["event","t",kind,1 if len(values)==1 else 2] for kind,values in descriptions.items()]
    interactions=iter(rows(Path("/data/newddi.csv")));assert next(interactions)==["d1","type","d2"]
    incident=collections.Counter()
    for key,row in enumerate(interactions,1):
        if len(row)!=3 or not row[0] or not row[2] or not row[1].isascii() or not row[1].isdecimal():continue
        for endpoint in (row[0],row[2]):
            if endpoint not in ids:ids[endpoint]=len(ids)+1
        a,b=ids[row[0]],ids[row[2]];incident.update({a,b})
        bulk.append(["put","t",key,a,int(row[1]),b])
    chosen=max(incident,key=incident.get)
    return [["engine","e"],["begin","t","e"],["bulk",bulk],["commit","t"],["tx_free","t"],
        ["current","baseline","e"],["snapshot","baseline"],["begin","u","e"],
        ["bind","u",chosen,2,0],["preview","changed","u"],["snapshot","changed"],
        ["compare","d","baseline","changed"],["diff","d"],["commit","u"],
        ["snapshot","baseline"],["tx_free","u"],["engine_free","e"],
        ["snapshot","changed"],["snapshot","baseline"],["diff","d"]]


def verify_sparse(answer,count=200_000,revisions=1000):
    result=answer["sparse"]
    assert result["committed"]=={"rc":0,"value":1,"output_preserved":False}
    assert result["operation_errors"]==[] and result["stable"] is True
    assert result["elapsed_sec"]<=120, "published sparse workload deadline exceeded"
    assert result["peak_rss_kib"]<=1536*1024, "published sparse RSS ceiling exceeded"
    base=State();base.drugs={i:(1,i) for i in range(1,2001)};base.events={i:1 for i in range(10)}
    for i in range(count):
        a=i%1999+1;b=(i*31+97)%2000+1
        if a==b:b=b%2000+1
        base.raw[i+1]=(a,i//2000%10,b)
    requested={1,*[i+2 for i in range(revisions) if i%32==0],revisions+1}
    assert len(result["snapshots"])==len(requested)
    def compact_view(revision):
        view=base.view(revision);digest=hashlib.sha256()
        for row in view["rows"]:digest.update((",".join(map(str,row))+"\n").encode("ascii"))
        rows=view.pop("rows");view.update({"row_count":len(rows),"rows_sha256":digest.hexdigest()})
        return view
    wanted={1:compact_view(1)}
    for i in range(revisions):
        base.raw[i+1]=(1,i%10,2000);base.raw.pop(count-i,None)
        if i+2 in requested:wanted[i+2]=compact_view(i+2)
    for item in result["snapshots"]:
        rev=item["revision"];assert rev in wanted
        view=wanted.pop(rev);subset(view,item["data"])
        assert (item["data"]["address"] is None)==view["null"]
    assert not wanted


def compile_library():
    build=Path(tempfile.mkdtemp(prefix="ddi-native-build-"));os.chown(build,65534,65534);os.chmod(build,0o755)
    library=build/"libddi.so"
    sources=sorted((APP/"src").glob("*.cpp"));assert sources,"no submitted C++ sources"
    run_process(["g++","-std=c++20","-O2","-Wall","-Wextra","-Wpedantic","-fPIC","-shared","-pthread",
                 "-I",str(APP/"include"),*map(str,sources),"-o",str(library)],timeout=120)
    return library


def main():
    started=time.monotonic();LOG.mkdir(parents=True,exist_ok=True)
    checks=[];library=None;build_error=None
    try:library=compile_library()
    except Exception as exc:build_error=f"{type(exc).__name__}: {exc}"
    suites=all_cases()
    for name,weight in WEIGHTS:
        group_start=time.monotonic();error=build_error
        if error is None:
            try:
                if name=="real_chemical_data":
                    ops=chemical_operations();answer,_=worker(library,{"operations":ops},60);verify_trace(ops,answer)
                elif name=="sparse_versions":
                    answer,_=worker(library,{"sparse":[200_000,1000]},130);verify_sparse(answer)
                else:
                    for ops in suites[name]:
                        answer,_=worker(library,{"operations":ops});verify_trace(ops,answer)
            except Exception as exc:error=f"{type(exc).__name__}: {exc}"[:4096]
        checks.append({"name":name,"weight":weight,"passed":error is None,"error":error,
                       "elapsed_sec":round(time.monotonic()-group_start,3)})
        print(json.dumps(checks[-1]),flush=True)
    reward=round(sum(check["weight"] for check in checks if check["passed"]),6)
    details={"checks":checks,"raw_reward":reward,"reward":reward,"elapsed_sec":round(time.monotonic()-started,3),
             "verifier_completed":True,"scoring":"independent partial credit; no score caps"}
    (LOG/"details.json").write_text(json.dumps(details,indent=2)+"\n",encoding="utf-8")
    (LOG/"reward.txt").write_text(f"{reward:.6f}\n",encoding="ascii")
    print(json.dumps({"reward":reward,"elapsed_sec":details["elapsed_sec"]}),flush=True)

if __name__=="__main__":main()
