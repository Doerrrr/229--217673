"""Public C ABI client. No expected results or scoring logic live here.

One JSON request on stdin, one JSON result on stdout. Useful for independent
tests. Repair the native library, not this client.
"""
import argparse
import concurrent.futures
import ctypes as C
import hashlib
import json
import resource
from pathlib import Path
import threading
import time

U=C.c_uint64
I=C.c_uint32
P=C.c_void_p
SENTINEL=0xFEDCBA9876543210
class Edge(C.Structure):
    _fields_=[("d1",U),("type",I),("reserved",I),("d2",U),("support",U)]
class Change(C.Structure):
    _fields_=[("d1",U),("type",I),("reserved",I),("d2",U),("before",U),("after",U)]


class Client:
    def __init__(self,path):
        self.library=C.CDLL(str(Path(path).resolve()))
        signatures={
            "engine_new":[C.POINTER(P)],"engine_free":[P],"begin":[P,C.POINTER(P)],"tx_free":[P],
            "bind":[P,U,I,U],"event":[P,I,I],"put":[P,U,U,I,U],"remove":[P,U],
            "savepoint":[P,C.POINTER(U)],"rollback":[P,U],"release":[P,U],"rebase":[P],"commit":[P,C.POINTER(U)],
            "current":[P,C.POINTER(P)],"preview":[P,C.POINTER(P)],"snapshot_free":[P],"revision":[P],
            "edges":[P,C.POINTER(C.POINTER(Edge)),C.POINTER(C.c_size_t)],"counts":[P,C.POINTER(U)],
            "support":[P,U,I,U,C.POINTER(U)],"compare":[P,P,C.POINTER(P)],
            "changes":[P,C.POINTER(C.POINTER(Change)),C.POINTER(C.c_size_t)],"diff_free":[P],
        }
        for name,signature in signatures.items():
            fn=getattr(self.library,"ddi_"+name);fn.argtypes=signature
            fn.restype=None if name.endswith("_free") else U if name=="revision" else C.c_int
            setattr(self,name,fn)
        self.handles={"NULL":P()}
        self.kinds={}
        self.tokens={}

    def pointer(self,name): return self.handles[name]

    def read_snapshot(self,name):
        snap=self.pointer(name);ptr=C.POINTER(Edge)();n=C.c_size_t(SENTINEL)
        rc=self.edges(snap,C.byref(ptr),C.byref(n))
        if rc: return {"rc":rc}
        if n.value>1_000_000: raise ValueError("unreasonable edge array")
        counts=(U*8)(*[SENTINEL]*8);crc=self.counts(snap,counts)
        return {"rc":rc,"counts_rc":crc,"revision":self.revision(snap),
                "address":C.cast(ptr,P).value,"null":not bool(ptr),
                "rows":[[p.d1,p.type,p.d2,p.support,p.reserved] for p in ptr[:n.value]],
                "counts":list(counts)}

    def read_diff(self,name):
        ptr=C.POINTER(Change)();n=C.c_size_t(SENTINEL)
        rc=self.changes(self.pointer(name),C.byref(ptr),C.byref(n))
        if rc: return {"rc":rc}
        if n.value>1_000_000: raise ValueError("unreasonable delta array")
        return {"rc":rc,"address":C.cast(ptr,P).value,"null":not bool(ptr),
                "rows":[[p.d1,p.type,p.d2,p.before,p.after,p.reserved] for p in ptr[:n.value]]}

    def summarize_snapshot(self,name):
        data=self.read_snapshot(name)
        if data["rc"]:return data
        digest=hashlib.sha256()
        for row in data["rows"]:digest.update((",".join(map(str,row))+"\n").encode("ascii"))
        rows=data.pop("rows")
        data.update({"row_count":len(rows),"rows_sha256":digest.hexdigest()})
        return data

    def call(self,op):
        name=op[0]
        if name=="engine":
            out=P(SENTINEL);rc=self.engine_new(C.byref(out))
            if rc==0:self.handles[op[1]]=out;self.kinds[op[1]]="engine"
            return {"rc":rc,"output_preserved":out.value==SENTINEL}
        if name in ("begin","current","preview","compare"):
            out=P(SENTINEL);args=[self.pointer(h) for h in op[2:]]
            rc=getattr(self,name)(*args,C.byref(out))
            if rc==0:
                self.handles[op[1]]=out
                self.kinds[op[1]]="tx" if name=="begin" else "diff" if name=="compare" else "snapshot"
            return {"rc":rc,"output_preserved":out.value==SENTINEL}
        if name.endswith("_free"):
            getattr(self,name)(self.pointer(op[1]))
            if op[1]!="NULL":del self.handles[op[1]];del self.kinds[op[1]]
            return {"rc":0}
        if name=="snapshot":return self.read_snapshot(op[1])
        if name=="diff":return self.read_diff(op[1])
        if name in ("commit","savepoint","support"):
            out=U(SENTINEL);rc=getattr(self,name)(self.pointer(op[1]),*op[2:],C.byref(out))
            return {"rc":rc,"value":out.value,"output_preserved":out.value==SENTINEL}
        if name=="save":
            out=U(SENTINEL);rc=self.savepoint(self.pointer(op[2]),C.byref(out))
            if rc==0:self.tokens[op[1]]=out.value
            return {"rc":rc,"value":out.value,"output_preserved":out.value==SENTINEL}
        if name in ("rollback","release"):
            token=self.tokens[op[2]] if isinstance(op[2],str) else op[2]
            return {"rc":getattr(self,name)(self.pointer(op[1]),token)}
        if name=="parallel_commit":
            barrier=threading.Barrier(len(op[1]))
            def writer(h):
                barrier.wait(timeout=10);return self.call(["commit",h])
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(op[1])) as pool:
                return {"results":list(pool.map(writer,op[1]))}
        if name=="bulk":
            first_error=None
            for i,item in enumerate(op[1]):
                result=self.call(item)
                if result["rc"] and first_error is None:first_error={"index":i,"rc":result["rc"]}
            return {"count":len(op[1]),"first_error":first_error}
        if name=="parallel_read":
            barrier=threading.Barrier(op[2])
            def reader(_):
                barrier.wait(timeout=10)
                return [self.read_snapshot(op[1]) for i in range(op[3])]
            with concurrent.futures.ThreadPoolExecutor(max_workers=op[2]) as pool:
                return {"readings":list(pool.map(reader,range(op[2])))}
        if name=="invalid_outputs":
            # Exercises null arguments, never arbitrary/dangling addresses.
            snap=self.pointer(op[1]);out=P(SENTINEL);num=U(SENTINEL)
            edge=C.cast(P(SENTINEL),C.POINTER(Edge));n=C.c_size_t(SENTINEL)
            return {
                "preview_null":[self.preview(None,C.byref(out)),out.value],
                "support_null":[self.support(None,1,0,2,C.byref(num)),num.value],
                "edges_null_count":[self.edges(snap,C.byref(edge),None),C.cast(edge,P).value],
                "edges_null_output":[self.edges(snap,None,C.byref(n)),n.value],
                "counts_null":self.counts(snap,None),"new_null":self.engine_new(None),
                "revision_null":self.revision(None),
            }
        return {"rc":getattr(self,name)(self.pointer(op[1]),*op[2:])}

    def close(self):
        for kind in ("diff","snapshot","tx","engine"):
            for name in list(self.kinds):
                if self.kinds[name]==kind:self.call([kind+"_free",name])

    def sparse(self,count,revisions):
        start=time.monotonic();self.call(["engine","e"]);self.call(["begin","t","e"])
        init=[["bind","t",i,1,i] for i in range(1,2001)]+[["event","t",i,1] for i in range(10)]
        errors=[]
        for op in init:
            if self.call(op)["rc"]:errors.append(op[0])
        for i in range(count):
            a=i%1999+1;b=(i*31+97)%2000+1
            if a==b:b=b%2000+1
            if self.call(["put","t",i+1,a,i//2000%10,b])["rc"]:errors.append("put")
        committed=self.call(["commit","t"]);self.call(["tx_free","t"])
        self.call(["current","s0","e"])
        original=self.summarize_snapshot("s0")
        pinned=[("s0",1)];stable=True
        for i in range(revisions):
            self.call(["begin","t","e"])
            for op in (["put","t",i+1,1,i%10,2000],["remove","t",count-i]):
                if self.call(op)["rc"]:errors.append(op[0])
            result=self.call(["commit","t"])
            if result["rc"] or result["value"]!=i+2:errors.append("commit")
            self.call(["tx_free","t"])
            if i%32==0:
                name="s"+str(i+1);self.call(["current",name,"e"]);pinned.append((name,i+2))
            if i%11==0:stable=stable and self.summarize_snapshot("s0")==original
        self.call(["current","latest","e"]);pinned.append(("latest",revisions+1))
        self.call(["engine_free","e"])
        snapshots=[]
        for name,rev in pinned:
            snapshots.append({"revision":rev,"data":self.summarize_snapshot(name)})
            self.call(["snapshot_free",name])
        return {"committed":committed,"operation_errors":errors[:10],"stable":stable,
                "snapshots":snapshots,"elapsed_sec":time.monotonic()-start,
                "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--library",default="/opt/ddi-snapshot/libddi.so")
    args=parser.parse_args();request=json.load(__import__("sys").stdin)
    client=Client(args.library)
    result={"edge_bytes":C.sizeof(Edge),"change_bytes":C.sizeof(Change)}
    if "sparse" in request:result["sparse"]=client.sparse(*request["sparse"])
    else:result["results"]=[client.call(op) for op in request["operations"]]
    client.close()
    print(json.dumps(result,separators=(",",":")))
if __name__=="__main__":main()
