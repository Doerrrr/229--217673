"""Frozen behavioral groups; expectations are computed separately in batch_model."""
import random

WEIGHTS=[
    ("abi_and_invalid",.05),("directed_edges",.06),("alias_support",.06),
    ("drug_cascade",.07),("event_cascade",.05),("replacement_dependencies",.05),
    ("preview_isolation",.08),("nested_savepoints",.07),("rollback_rebase_log",.08),
    ("conflict_and_revision",.05),("net_diffs",.06),("snapshot_lifetime",.06),
    ("diff_lifetime",.04),("parallel_cas",.05),("parallel_readers",.04),
    ("random_histories",.05),("real_chemical_data",.04),("sparse_versions",.04),
]
assert abs(sum(w for _,w in WEIGHTS)-1)<1e-12


def seed():
    return [["engine","e"],["begin","t","e"],
            ["bind","t",1,1,10],["bind","t",2,1,20],["event","t",0,1]]
def read(tx="t",snapshot="s"):
    return [["preview",snapshot,tx],["snapshot",snapshot]]
def finish():return [["tx_free","t"],["engine_free","e"]]


def semantic_cases():
    result={}
    ops=seed()+read()
    for op in (["bind","t",0,1,1],["bind","t",1,1,0],["bind","t",1,2,3],
               ["bind","t",1,3,2],["bind","t",1,4,0],["event","t",0,3],
               ["put","t",0,1,0,2],["put","t",1,0,0,2],["put","t",1,1,0,0],
               ["remove","t",0],["rollback","t",999],["release","t",0]):
        ops.append(op);ops+=read(snapshot="s"+str(len(ops)))
    ops += [["invalid_outputs","s"],["support","NULL",1,0,2],
            ["begin","bad","NULL"],["preview","bad","NULL"],["compare","bad","s","NULL"],
            ["snapshot_free","NULL"],["diff_free","NULL"],["tx_free","NULL"],["engine_free","NULL"]]+finish()
    result["abi_and_invalid"]=[ops]
    ops=seed()+[["bind","t",3,1,18446744073709551615],["event","t",4294967295,1],
               ["put","t",7,2,0,1],["put","t",2,1,0,2],["put","t",99,3,4294967295,1]]+read()
    ops += [["support","s",10,0,20],["support","s",20,0,10],["support","s",777,0,888],
            ["support","s",0,0,20],["commit","t"],["current","c","e"],["snapshot","c"]]+finish()
    result["directed_edges"]=[ops]
    ops=seed()+[["bind","t",3,1,10],["put","t",1,1,0,2],["put","t",2,3,0,2],
               ["put","t",3,2,0,1],["put","t",4,1,0,3]]+read(snapshot="s0")
    ops += [["remove","t",1]]+read(snapshot="s1")+[["compare","d","s0","s1"],["diff","d"],
                ["put","t",2,2,0,3]]+read(snapshot="s2")+[["snapshot","s0"],["snapshot","s1"]]+finish()
    result["alias_support"]=[ops]
    ops=seed()+[["bind","t",3,3,0],["bind","t",4,2,0],
               ["put","t",1,1,0,2],["put","t",2,1,0,5],["put","t",3,3,0,4],
               ["put","t",4,3,0,2],["put","t",5,1,0,1]]+read(snapshot="a")
    for state,mol in ((2,0),(3,0),(0,0),(1,30),(1,20),(1,10)):
        ops += [["bind","t",1,state,mol]]+read(snapshot="v"+str(len(ops)))
    ops += [["bind","t",5,1,40],["bind","t",3,1,50],["bind","t",4,1,60]]+read(snapshot="b")
    ops += [["snapshot","a"],["compare","d","a","b"],["diff","d"]]+finish()
    result["drug_cascade"]=[ops]
    ops=seed()+[["put","t",1,1,0,2],["put","t",2,1,1,2],["put","t",3,9,0,2],
               ["put","t",4,1,0,1],["bind","t",3,1,10],["put","t",5,1,0,3]]+read(snapshot="a")
    for kind,state in ((0,2),(0,0),(1,2),(1,1),(0,1)):
        ops += [["event","t",kind,state]]+read(snapshot="v"+str(len(ops)))
    ops += [["snapshot","a"]]+finish();result["event_cascade"]=[ops]
    ops=seed()+[["bind","t",3,1,30],["bind","t",4,1,40],["event","t",1,1],
               ["put","t",11,1,0,2]]+read(snapshot="old")
    ops += [["put","t",11,3,1,4],["bind","t",1,2,0],["event","t",0,2]]+read(snapshot="new")
    ops += [["bind","t",3,0,0]]+read(snapshot="missing")
    ops += [["remove","t",11],["bind","t",3,1,30],["event","t",1,2],
            ["remove","t",12345]]+read(snapshot="empty")+[["snapshot","old"],["snapshot","new"]]+finish()
    result["replacement_dependencies"]=[ops]
    return result


def version_cases():
    r={}
    ops=seed()+[["put","t",1,1,0,2]]+read(snapshot="p0")
    ops += [["current","c0","e"],["snapshot","c0"],["begin","b","e"],
            ["bind","t",1,1,30]]+read(snapshot="p1")
    ops += [["preview","bp","b"],["snapshot","bp"],["snapshot","p0"],["snapshot","c0"],
            ["commit","t"],["current","c1","e"],["snapshot","c1"],["snapshot","p0"],
            ["snapshot","p1"],["snapshot","c0"],["snapshot","bp"],["tx_free","b"]]+finish()
    r["preview_isolation"]=[ops]
    ops=seed()+[["put","t",1,1,0,2],["save","q0","t"],["bind","t",1,1,30],
               ["save","q1","t"],["remove","t",1]]+read(snapshot="deleted")
    ops += [["rollback","t","q1"]]+read(snapshot="back")+[["rollback","t","q1"],
            ["save","q2","t"],["bind","t",2,1,40],["rollback","t","q0"],
            ["rollback","t","q2"],["release","t","q1"]]+read(snapshot="origin")
    ops += [["save","q3","t"],["put","t",2,2,0,1],["save","q4","t"],
            ["release","t","q3"],["rollback","t","q4"],["rollback","t","q3"]]+read(snapshot="released")
    ops += [["snapshot","deleted"],["snapshot","back"],["snapshot","origin"]]+finish()
    r["nested_savepoints"]=[ops]
    ops=seed()+[["commit","t"],["tx_free","t"],["begin","t","e"],["begin","b","e"],
        ["bind","t",1,1,30],["save","q","t"],["bind","t",2,1,90],["put","t",999,2,0,1],
        ["rollback","t","q"],["put","t",8,1,0,2],["bind","b",2,1,40],["put","b",7,2,0,1],
        ["commit","b"],["preview","pre","t"],["snapshot","pre"],["commit","t"],
        ["preview","conflict","t"],["snapshot","conflict"],["rebase","t"],["rollback","t","q"]]+read(snapshot="rebased")
    ops += [["snapshot","pre"],["snapshot","conflict"],["save","q2","t"],["remove","t",7],
        ["rollback","t","q2"],["begin","b2","e"],["bind","b2",2,1,50],["commit","b2"],
        ["rebase","t"],["rollback","t","q2"]]+read(snapshot="twice")
    ops += [["commit","t"],["current","c","e"],["snapshot","c"],["tx_free","b"],["tx_free","b2"]]+finish()
    r["rollback_rebase_log"]=[ops]
    ops=seed()+[["begin","b","e"],["commit","t"],["commit","b"],["rebase","b"],
            ["commit","b"],["begin","c","e"],["commit","c"],["current","s","e"],["snapshot","s"],
            ["commit","t"],["bind","t",1,1,1],["event","t",0,1],["put","t",5,1,0,2],
            ["remove","t",1],["savepoint","t"],["rollback","t",999],["release","t",999],
            ["rebase","t"],["preview","bad","t"],["bind","t",0,1,1],
            ["begin","live","e"],["engine_free","e"],["commit","live"],
            ["bind","live",2,1,30],["preview","bad","live"],["snapshot","s"],
            ["tx_free","t"],["tx_free","b"],["tx_free","c"],["tx_free","live"]]
    r["conflict_and_revision"]=[ops]
    ops=seed()+[["put","t",1,1,0,2]]+read(snapshot="a")
    ops += [["put","t",2,1,0,2],["put","t",3,2,0,1]]+read(snapshot="b")
    ops += [["put","t",1,2,0,1],["remove","t",2]]+read(snapshot="c")
    ops += [["compare","ab","a","b"],["diff","ab"],["compare","bc","b","c"],["diff","bc"],
            ["compare","aa","a","a"],["diff","aa"],["engine","other"],["current","zero","other"],
            ["compare","az","a","zero"],["diff","az"],["compare","za","zero","a"],["diff","za"],
            ["diff","ab"],["engine_free","other"]]+finish()
    r["net_diffs"]=[ops]
    ops=seed()+[["put","t",1,1,0,2]]+read(snapshot="before")
    ops += [["commit","t"],["current","committed","e"],["snapshot","committed"],["tx_free","t"],
            ["begin","b","e"],["bind","b",1,1,30],["preview","after","b"],["snapshot","after"],
            ["tx_free","b"],["engine_free","e"],["snapshot","before"],["snapshot","committed"],
            ["snapshot","after"],["support","before",10,0,20],["snapshot_free","before"],
            ["snapshot","after"],["snapshot_free","after"],["snapshot_free","committed"]]
    r["snapshot_lifetime"]=[ops]
    ops=seed()+[["put","t",1,1,0,2]]+read(snapshot="before")
    ops += [["bind","t",2,1,30]]+read(snapshot="after")
    ops += [["compare","d","before","after"],["diff","d"],["snapshot_free","before"],
            ["snapshot_free","after"],["tx_free","t"],["engine_free","e"],["diff","d"],
            ["engine","e2"],["begin","t2","e2"],["bind","t2",1,1,999],["commit","t2"],
            ["diff","d"],["diff_free","d"],["tx_free","t2"],["engine_free","e2"]]
    r["diff_lifetime"]=[ops]
    return r


def thread_cases():
    r={};ops=[]
    for run in range(20):
        ops += [["engine","e"]]
        names=["w"+str(i) for i in range(4)]
        for i,name in enumerate(names):ops += [["begin",name,"e"],["bind",name,i+1,1,i+10]]
        ops += [["parallel_commit",names],["current","s","e"],["snapshot","s"]]
        for name in names:ops += [["rebase",name],["commit",name],["tx_free",name]]
        ops += [["current","last","e"],["snapshot","last"],["snapshot_free","s"],
                ["snapshot_free","last"],["engine_free","e"]]
    r["parallel_cas"]=[ops]
    ops=seed()+[["put","t",1,1,0,2],["put","t",2,2,0,1],["commit","t"],
                ["current","s","e"],["parallel_read","s",8,50],["engine_free","e"],
                ["parallel_read","s",8,20],["tx_free","t"],["snapshot_free","s"]]
    r["parallel_readers"]=[ops];return r


def random_traces(count=60):
    traces=[];rng=random.Random(20261012071)
    for run in range(count):
        ops=seed();labels=[];held=[]
        for step in range(70):
            roll=rng.randrange(10)
            if roll<2:ops.append(["bind","t",rng.randrange(1,24),1,rng.randrange(1,16)])
            elif roll==2:ops.append(["bind","t",rng.randrange(1,24),rng.choice([0,2,3]),0])
            elif roll==3:ops.append(["event","t",rng.randrange(5),rng.randrange(3)])
            elif roll<7:ops.append(["put","t",rng.randrange(1,90),rng.randrange(1,24),rng.randrange(5),rng.randrange(1,24)])
            elif roll==7:ops.append(["remove","t",rng.randrange(1,90)])
            elif roll==8 or not labels:
                label="q"+str(step);ops.append(["save",label,"t"]);labels.append(label)
            else:
                i=rng.randrange(len(labels));name=rng.choice(["rollback","release"])
                ops.append([name,"t",labels[i]]);labels=labels[:i+(name=="rollback")]
            if step%7==0:
                label="s"+str(step);held.append(label);ops+=read(snapshot=label)
        ops += [["commit","t"],["current","last","e"],["snapshot","last"],["engine_free","e"]]
        for label in held:ops += [["snapshot",label],["compare","d"+label,label,"last"],["diff","d"+label],
                                  ["snapshot_free",label],["diff","d"+label],["diff_free","d"+label]]
        ops += [["tx_free","t"],["snapshot_free","last"]];traces.append(ops)
    return traces


def all_cases():
    return {**semantic_cases(),**version_cases(),**thread_cases(),"random_histories":random_traces()}
