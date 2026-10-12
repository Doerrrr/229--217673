"""Independent scalar/batch specification; never imports the reference library."""
import collections
import copy

SENTINEL=0xFEDCBA9876543210


class State:
    def __init__(self):self.drugs={};self.events={};self.raw={}
    def mutate(self,op):
        name,_,*a=op
        if name=="bind":
            key,state,mol=a
            if not key or state not in (0,1,2,3) or (state==1)!=(mol>0):return 1
            if state:self.drugs[key]=(state,mol)
            else:self.drugs.pop(key,None)
        elif name=="event":
            kind,state=a
            if state not in (0,1,2):return 1
            if state:self.events[kind]=state
            else:self.events.pop(kind,None)
        elif name=="put":
            key,d1,kind,d2=a
            if not key or not d1 or not d2:return 1
            self.raw[key]=(d1,kind,d2)
        elif name=="remove":
            if not a[0]:return 1
            self.raw.pop(a[0],None)
        else:raise ValueError(name)
        return 0
    def view(self,revision):
        reason=[0]*8;edges=collections.Counter()
        for d1,kind,d2 in self.raw.values():
            a=self.drugs.get(d1);b=self.drugs.get(d2)
            if a is None or b is None:r=0
            elif 2 in (a[0],b[0]):r=1
            elif 3 in (a[0],b[0]):r=2
            elif kind not in self.events:r=3
            elif self.events[kind]==2:r=4
            elif d1==d2:r=5
            elif a[1]==b[1]:r=6
            else:r=7;edges[(a[1],kind,b[1])]+=1
            reason[r]+=1
        return {"rc":0,"counts_rc":0,"revision":revision,
                "rows":[[*key,value,0] for key,value in sorted(edges.items())],
                "counts":reason,"null":not edges}


def subset(want,got):
    for key,value in want.items():
        if key not in got or got[key]!=value:
            observed=got.get(key)
            if isinstance(value,list) and isinstance(observed,list):
                first=next((i for i,(a,b) in enumerate(zip(value,observed)) if a!=b),min(len(value),len(observed)))
                expected=value[first] if first<len(value) else "END"
                actual=observed[first] if first<len(observed) else "END"
                raise AssertionError(f"{key}: lengths {len(value)}/{len(observed)}; first mismatch {first}: expected {expected!r}, got {actual!r}")
            raise AssertionError(f"{key}: expected {value!r}, got {observed!r}")


class Model:
    def __init__(self):
        self.engines={};self.txs={};self.snaps={};self.diffs={}
        self.addresses={};self.tokens=set();self.token_values={}
    def open_rc(self,name):
        if name=="NULL":return 1
        tx=self.txs[name]
        return 3 if not tx["open"] or self.engines[tx["engine"]]["closed"] else 0
    def mutation(self,op):
        # Scalar argument validation precedes closed-state checks.
        temporary=State()
        if temporary.mutate(op):return 1
        rc=self.open_rc(op[1])
        if rc:return rc
        tx=self.txs[op[1]];tx["state"].mutate(op);tx["log"].append(op);return 0
    def commit(self,name):
        rc=self.open_rc(name)
        if rc:return {"rc":rc,"value":SENTINEL,"output_preserved":True}
        tx=self.txs[name];engine=self.engines[tx["engine"]]
        if tx["base"]!=engine["revision"]:return {"rc":2,"value":SENTINEL,"output_preserved":True}
        engine["revision"]+=1;engine["state"]=copy.deepcopy(tx["state"]);tx["open"]=False
        return {"rc":0,"value":engine["revision"],"output_preserved":False}
    def inspect_view(self,name,want,got):
        subset(want,got)
        address=got["address"]
        assert (address is None)==want["null"]
        if name in self.addresses:assert self.addresses[name]==address, "borrowed address changed"
        self.addresses[name]=address
    def step(self,op,got):
        name=op[0]
        if name=="engine":
            self.engines[op[1]]={"closed":False,"revision":0,"state":State()}
            subset({"rc":0,"output_preserved":False},got)
        elif name=="begin":
            if op[2]=="NULL":subset({"rc":1,"output_preserved":True},got);return
            e=self.engines[op[2]]
            self.txs[op[1]]={"engine":op[2],"base":e["revision"],"state":copy.deepcopy(e["state"]),
                             "open":True,"log":[],"points":[]}
            self.tokens={item for item in self.tokens if item[0]!=op[1]}
            subset({"rc":0,"output_preserved":False},got)
        elif name in ("bind","event","put","remove"):subset({"rc":self.mutation(op)},got)
        elif name=="bulk":
            first=None
            for i,item in enumerate(op[1]):
                rc=self.mutation(item)
                if rc and first is None:first={"index":i,"rc":rc}
            subset({"count":len(op[1]),"first_error":first},got)
        elif name=="commit":subset(self.commit(op[1]),got)
        elif name in ("current","preview"):
            if op[2]=="NULL":rc=1
            elif name=="preview":rc=self.open_rc(op[2])
            else:rc=0
            subset({"rc":rc,"output_preserved":bool(rc)},got)
            if not rc:
                owner=self.engines[op[2]] if name=="current" else self.txs[op[2]]
                revision=owner["revision"] if name=="current" else owner["base"]
                self.snaps[op[1]]=copy.deepcopy(owner["state"]).view(revision)
                self.addresses.pop(op[1],None)
        elif name=="snapshot":self.inspect_view(op[1],self.snaps[op[1]],got)
        elif name=="support":
            _,snap,d1,kind,d2=op
            if snap=="NULL" or not d1 or not d2:want={"rc":1,"value":SENTINEL,"output_preserved":True}
            else:
                value=next((row[3] for row in self.snaps[snap]["rows"] if row[:3]==[d1,kind,d2]),0)
                want={"rc":0,"value":value,"output_preserved":False}
            subset(want,got)
        elif name in ("save","savepoint"):
            txname=op[2] if name=="save" else op[1];rc=self.open_rc(txname)
            subset({"rc":rc},got)
            if rc:subset({"value":SENTINEL,"output_preserved":True},got);return
            # Tokens are opaque positive uint64 values, not small ordinals.
            # A legal token can equal our output sentinel on a successful call.
            value=got["value"];assert 0<value<=2**64-1
            assert (txname,value) not in self.tokens, "reused savepoint token"
            self.tokens.add((txname,value))
            label=op[1] if name=="save" else value;self.token_values[label]=value
            tx=self.txs[txname]
            tx["points"].append((label,copy.deepcopy(tx["state"]),len(tx["log"])))
        elif name in ("rollback","release"):
            tx=self.txs[op[1]];rc=self.open_rc(op[1])
            index=next((i for i,p in enumerate(tx["points"]) if p[0]==op[2]),None)
            if not rc and index is None:rc=1
            subset({"rc":rc},got)
            if rc:return
            point=tx["points"][index]
            if name=="rollback":
                tx["state"]=copy.deepcopy(point[1]);tx["log"]=tx["log"][:point[2]];tx["points"]=tx["points"][:index+1]
            else:tx["points"]=tx["points"][:index]
        elif name=="rebase":
            rc=self.open_rc(op[1]);subset({"rc":rc},got)
            if not rc:
                tx=self.txs[op[1]];engine=self.engines[tx["engine"]]
                tx["state"]=copy.deepcopy(engine["state"]);tx["base"]=engine["revision"]
                for mutation in tx["log"]:tx["state"].mutate(mutation)
                tx["points"]=[]
        elif name=="compare":
            if "NULL" in op[2:]:subset({"rc":1,"output_preserved":True},got);return
            a={tuple(row[:3]):row[3] for row in self.snaps[op[2]]["rows"]}
            b={tuple(row[:3]):row[3] for row in self.snaps[op[3]]["rows"]}
            rows=[[*key,a.get(key,0),b.get(key,0),0] for key in sorted(a.keys()|b.keys()) if a.get(key,0)!=b.get(key,0)]
            self.diffs[op[1]]={"rc":0,"rows":rows,"null":not rows}
            self.addresses.pop(op[1],None)
            subset({"rc":0,"output_preserved":False},got)
        elif name=="diff":self.inspect_view(op[1],self.diffs[op[1]],got)
        elif name=="engine_free":
            if op[1]!="NULL":self.engines[op[1]]["closed"]=True
            subset({"rc":0},got)
        elif name.endswith("_free"):subset({"rc":0},got)
        elif name=="parallel_commit":
            responses=got["results"];assert len(responses)==len(op[1])
            assert sorted(r["rc"] for r in responses)==[0]+[2]*(len(responses)-1)
            winner=next(i for i,r in enumerate(responses) if r["rc"]==0)
            subset(self.commit(op[1][winner]),responses[winner])
            for i,r in enumerate(responses):
                if i!=winner:subset(self.commit(op[1][i]),r)
        elif name=="parallel_read":
            assert len(got["readings"])==op[2]
            for readings in got["readings"]:
                assert len(readings)==op[3]
                for reading in readings:self.inspect_view(op[1],self.snaps[op[1]],reading)
        elif name=="invalid_outputs":
            subset({"preview_null":[1,SENTINEL],"support_null":[1,SENTINEL],
                    "edges_null_count":[1,SENTINEL],"edges_null_output":[1,SENTINEL],
                    "counts_null":1,"new_null":1,"revision_null":0},got)
        else:raise ValueError(name)


def verify_trace(operations,answer):
    subset({"edge_bytes":32,"change_bytes":40},answer)
    assert len(answer["results"])==len(operations), "missing results"
    model=Model()
    for i,(op,got) in enumerate(zip(operations,answer["results"])):
        try:model.step(op,got)
        except Exception as exc:raise AssertionError(f"operation {i}: {op[:3]}: {exc}") from exc
    return model
