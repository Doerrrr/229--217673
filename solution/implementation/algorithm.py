"""Generic exact orbit counts; no instance registry or supplied witnesses."""
from functools import lru_cache
from itertools import product
from math import factorial, gcd

COMP=(3,2,1,0)  # A,C,G,T

def validate(q):
    if not isinstance(q,dict) or set(q)!={'id','counts'}:raise ValueError('query fields')
    m=q['counts']
    if type(m)is not list or len(m)!=4 or any(type(row)is not list or len(row)!=4 for row in m):raise ValueError('counts shape')
    if any(type(x)is not int or not 0<=x<=96 for row in m for x in row):raise ValueError('counts integer')
    if not 1<=sum(map(sum,m))<=96:raise ValueError('total count')

def rc_matrix(m):
    return tuple(tuple(m[COMP[j]][COMP[i]] for j in range(4)) for i in range(4))

def det(a):
    if not a:return 1
    if len(a)==1:return a[0][0]
    return sum((-1)**j*x*det([r[:j]+r[j+1:] for r in a[1:]]) for j,x in enumerate(a[0]))

def trail_count(h,start,end):
    """Linear vertex strings with specified endpoints, no edge labels."""
    n=sum(map(sum,h))
    if not n:return int(start==end)
    outs=[sum(row) for row in h]
    ins=[sum(h[i][j] for i in range(4)) for j in range(4)]
    if any(outs[v]-ins[v] != int(v==start)-int(v==end) for v in range(4)):return 0
    active=[v for v in range(4) if outs[v]+ins[v] or v in (start,end)]
    minor=[[((outs[i] if i==j else 0)-h[i][j]) for j in active if j!=end] for i in active if i!=end]
    tree=det(minor)
    if not tree:return 0
    numerator=tree
    for v in active:
        k=outs[v]-1+int(v==end)
        if k<0:return 0
        numerator*=factorial(k)
    denominator=1
    for row in h:
        for x in row:denominator*=factorial(x)
    answer,remainder=divmod(numerator,denominator)
    assert remainder==0 and answer>=0
    return answer

@lru_cache(maxsize=4096)
def rooted(m):
    outs=[sum(row) for row in m]
    ins=[sum(m[i][j] for i in range(4)) for j in range(4)]
    if outs!=ins:return 0
    return sum(trail_count(m,v,v) for v in range(4) if outs[v])

def divisors(n):return [d for d in range(1,n+1) if n%d==0]

@lru_cache(maxsize=4096)
def reflection(m):
    """Fix of literal reverse complement, anchored at the two edge cuts."""
    n=sum(map(sum,m))
    if n%2 or m!=rc_matrix(m) or not rooted(m):return 0
    pairs=[];fixed=[];seen=set()
    for i in range(4):
        for j in range(4):
            if (i,j) in seen:continue
            partner=(COMP[j],COMP[i]);seen.update(((i,j),partner))
            (fixed if partner==(i,j) else pairs).append((i,j) if partner==(i,j) else ((i,j),partner))
    total=0
    for start in range(4):
        for end in range(4):
            residual=[list(row) for row in m]
            residual[end][COMP[end]]-=1
            residual[COMP[start]][start]-=1
            if any(x<0 for row in residual for x in row):continue
            if any(residual[i][j]%2 for i,j in fixed):continue
            h=[[0]*4 for _ in range(4)]
            for i,j in fixed:h[i][j]=residual[i][j]//2
            choices=[range(residual[a[0]][a[1]]+1) for a,b in pairs]
            for values in product(*choices):
                for ((i,j),(u,v)),value in zip(pairs,values):
                    h[i][j]=value;h[u][v]=residual[i][j]-value
                total+=trail_count(h,start,end)
    return total

def solve(q):
    m=tuple(tuple(row) for row in q['counts'])
    n=sum(map(sum,m));symmetric=m==rc_matrix(m)
    prim={};fixed_prim={};spectrum=[]
    for d in divisors(n):
        repeat=n//d
        if any(x%repeat for row in m for x in row):
            spectrum.append(dict(period=d,rotation_classes='0',self_reverse_complement='0',strand_classes='0'))
            continue
        reduced=tuple(tuple(x//repeat for x in row) for row in m)
        p=rooted(reduced)-sum(value for e,value in prim.items() if d%e==0)
        prim[d]=p
        assert p>=0 and p%d==0
        oriented=p//d
        if symmetric:
            f=reflection(reduced)-sum(value for e,value in fixed_prim.items() if d%e==0)
            fixed_prim[d]=f
            assert f>=0 and f%2==0
            self_rc=f//2
            assert 0<=self_rc<=oriented and (oriented+self_rc)%2==0
            strand=(oriented+self_rc)//2
        else:
            oriented*=2;self_rc=0;strand=oriented//2
        spectrum.append(dict(period=d,rotation_classes=str(oriented),self_reverse_complement=str(self_rc),strand_classes=str(strand)))
    return dict(length=n,linear_words=str(rooted(m)*(1 if symmetric else 2)),
                rotation_classes=str(sum(int(r['rotation_classes']) for r in spectrum)),
                strand_classes=str(sum(int(r['strand_classes']) for r in spectrum)),period_spectrum=spectrum)
