"""AUTHOR PRIVATE finite graph witnesses and exact clique checks, not a completion solver."""
import itertools
import random
import time

def adjacency(rows,color=1):
    n=len(rows)
    return [sum(1<<j for j in range(n) if i!=j and int(rows[i][j])==color) for i in range(n)]

def find_clique(adj,size):
    """Exact bitset branch search. Return a concrete clique or None."""
    def expand(candidates,chosen):
        need=size-len(chosen)
        if not need:return chosen
        while candidates.bit_count()>=need:
            bit=candidates&-candidates;candidates^=bit;v=bit.bit_length()-1
            got=expand(candidates&adj[v],chosen+[v])
            if got is not None:return got
        return None
    return expand((1<<len(adj))-1,[])

def max_clique(adj):
    size=1;witness=[0]
    while True:
        nxt=find_clique(adj,size+1)
        if nxt is None:return size,witness
        size+=1;witness=nxt

def paley(n):
    assert n%4==1 and n>2 and all(n%d for d in range(2,int(n**.5)+1))
    residues={i*i%n for i in range(1,n)}
    return [''.join('.' if i==j else str(int((j-i)%n in residues)) for j in range(n)) for i in range(n)]

def permute(rows,rng,complement=False):
    p=list(range(len(rows)));rng.shuffle(p)
    return [''.join('.' if i==j else str(int(rows[p[i]][p[j]])^int(complement)) for j in range(len(rows))) for i in range(len(rows))]

def recolor(rows,u,v):
    result=list(rows)
    a=list(result[u]);b=list(result[v]);a[v]=b[u]=str(1-int(a[v]));result[u]=''.join(a);result[v]=''.join(b)
    return result

def wiggle(rows,red_forbid,blue_forbid,rng,tries):
    """Produce finite witnesses by verified individual edge switches, no input solving."""
    n=len(rows);changed=0
    for _ in range(tries):
        u,v=rng.sample(range(n),2);candidate=recolor(rows,u,v)
        # A new forbidden clique, if any, must include the switched edge.
        new=int(candidate[u][v]);bound=red_forbid if new else blue_forbid
        adj=adjacency(candidate,new)
        common=adj[u]&adj[v]
        verts=[i for i in range(n) if common>>i&1]
        local=[sum(1<<j for j,w in enumerate(verts) if adj[z]>>w&1) for z in verts]
        if find_clique(local,bound-2) is None:rows=candidate;changed+=1
    assert find_clique(adjacency(rows),red_forbid) is None
    assert find_clique(adjacency(rows,0),blue_forbid) is None
    return rows,changed

def structural(q,row):
    n=q['n']
    if not isinstance(row,dict) or row.get('id')!=q['id'] or set(row)!={'id','state','rows'}:return False,'output object fields'
    if row['state']=='UNSOLVED' and row['rows'] is None:return False,'candidate explicitly returned UNSOLVED'
    rows=row['rows']
    if row['state']!='COMPLETE' or not isinstance(rows,list) or len(rows)!=n:return False,'matrix shape'
    if any(not isinstance(r,str) or len(r)!=n for r in rows):return False,'matrix width'
    if any(rows[i][j] not in ('.' if i==j else '01') or (i==j and rows[i][j]!='.') for i in range(n) for j in range(n)):return False,'matrix alphabet/diagonal'
    if any(rows[i][j]!=rows[j][i] for i in range(n) for j in range(i)):return False,'matrix asymmetry'
    for u,v,c in q['fixed']:
        if int(rows[u][v])!=c:return False,dict(fixed_edge=[u,v,c],actual=rows[u][v])
    for i,(low,high) in enumerate(q['degrees']):
        degree=rows[i].count('1')
        if not low<=degree<=high:return False,dict(degree_vertex=i,actual=degree,range=[low,high])
    for index,cut in enumerate(q['cuts']):
        A=set(cut['left']);B=set(cut['right']);value=sum(rows[i][j]=='1' for i in A for j in B)
        if not cut['min']<=value<=cut['max']:return False,dict(cut=index,actual=value,range=[cut['min'],cut['max']])
    for color,k in [(1,q['red_forbid']),(0,q['blue_forbid'])]:
        bad=find_clique(adjacency(rows,color),k)
        if bad is not None:return False,dict(monochromatic_color=color,clique=bad)
    return True,'complete exact verification'

def brute_clique(rows,k,color):
    for vertices in itertools.combinations(range(len(rows)),k):
        if all(rows[u][v]==str(color) for u,v in itertools.combinations(vertices,2)):return list(vertices)
    return None

def main():
    import json
    records=[]
    for n in (5,13,17,29,37,41,53,61,73):
        start=time.monotonic();r=paley(n)
        red,rv=max_clique(adjacency(r));blue,bv=max_clique(adjacency(r,0))
        records.append(dict(n=n,red_max=red,blue_max=blue,seconds=round(time.monotonic()-start,4)))
    print(json.dumps(records),flush=True)

if __name__=='__main__':main()
