"""General exact roots in R_N with pi^2=p and pi^N=0."""
from math import comb
from contract import keys,integer
from padic_fiber import decimal

def validate(q):
    keys(q,('id','p','precision','polynomials','ranks','boxes','values'))
    if type(q['p'])is not int or q['p'] not in (2,3,5,7):raise ValueError('prime')
    integer(q['precision'],1,32)
    if type(q['polynomials'])is not list or not 1<=len(q['polynomials'])<=4:raise ValueError('polynomials')
    for poly in q['polynomials']:
        if type(poly)is not list or not 1<=len(poly)<=13:raise ValueError('degree')
        for coefficient in poly:
            if type(coefficient)is not list or len(coefficient)!=2:raise ValueError('coefficient pair')
            for x in coefficient:integer(x,-10**12,10**12)
    for name in ('ranks','boxes','values'):
        if type(q[name])is not list or len(q[name])>32:raise ValueError('query count')
    for rank in q['ranks']:decimal(rank,True)
    for value in q['values']:
        if type(value)is not list or len(value)!=2:raise ValueError('value pair')
        for x in value:decimal(x)
    for box in q['boxes']:
        if type(box)is not list or len(box)!=2:raise ValueError('box')
        for interval in box:
            if type(interval)is not list or len(interval)!=2:raise ValueError('interval')
            a,b=map(decimal,interval)
            if a>b:raise ValueError('interval order')

def moduli(p,n):return p**((n+1)//2),p**(n//2)
def reduce(x,p,n):
    a,b=moduli(p,n);return x[0]%a,x[1]%b
def add(a,b,p,n):return reduce((a[0]+b[0],a[1]+b[1]),p,n)
def mul(a,b,p,n):return reduce((a[0]*b[0]+p*a[1]*b[1],a[0]*b[1]+a[1]*b[0]),p,n)
def pi_power(p,n):return (p**(n//2),0) if n%2==0 else (0,p**(n//2))
def valuation(x,p,n):
    values=[]
    for part,offset in zip(x,(0,1)):
        if part==0:values.append(n);continue
        v=0
        while part%p==0:part//=p;v+=1
        values.append(2*v+offset)
    return min(n,*values)

def root_balls(polynomials,p,n):
    def visit(items,a,b,s):
        remaining=[]
        for coefficients,h in items:
            coefficients=[reduce(c,p,h) for c in coefficients]
            content=min((valuation(c,p,h) for c in coefficients),default=h)
            if content==h:continue
            for _ in range(content):
                assert all(c[0]%p==0 for c in coefficients)
                coefficients=[(c[1],c[0]//p) for c in coefficients]
            h-=content;coefficients=[reduce(c,p,h) for c in coefficients]
            remaining.append((coefficients,h))
        if not remaining:return [(a,b,s)]
        if s==n:return [(a,b,s)] if all(c[0]==(0,0) for c,h in remaining) else []
        result=[]
        for digit in range(p):
            if any(sum(c[i][0]*digit**i for i in range(len(c)))%p for c,h in remaining):continue
            next_items=[]
            for coefficients,h in remaining:
                translated=[(0,0)]*len(coefficients)
                for i,c in enumerate(coefficients):
                    for j in range(i+1):
                        scale=comb(i,j)*digit**(i-j);term=mul(c,pi_power(p,j),p,h)
                        translated[j]=add(translated[j],(term[0]*scale,term[1]*scale),p,h)
                next_items.append((translated,h))
            aa=a+(p**(s//2)*digit if s%2==0 else 0)
            bb=b+(p**(s//2)*digit if s%2 else 0)
            result.extend(visit(next_items,aa,bb,s+1))
        children={(a+(p**(s//2)*d if s%2==0 else 0),b+(p**(s//2)*d if s%2 else 0),s+1) for d in range(p)}
        return [(a,b,s)] if len(result)==p and set(result)==children else result
    return sorted(visit([(poly,n) for poly in polynomials],0,0,0),key=lambda item:(item[2],item[0],item[1]))

def solve(q):
    p,n=q['p'],q['precision'];A,B=moduli(p,n);balls=root_balls(q['polynomials'],p,n)
    count=sum(p**(n-s) for a,b,s in balls)
    def progression(base,step,lo,hi,M):
        lo=max(lo,0);hi=min(hi,M-1)
        return 0 if lo>hi else max(0,(hi-base)//step-(lo-1-base)//step)
    def cumulative(x,y):
        total=0
        for a,b,s in balls:
            sa,sb=moduli(p,s);nb=B//sb
            total+=progression(a,sa,0,x-1,A)*nb
            if 0<=x<A and (x-a)%sa==0:total+=progression(b,sb,0,y,B)
        return total
    selections=[]
    for raw in q['ranks']:
        rank=int(raw)
        if rank>=count:selections.append(None);continue
        lo,hi=0,A-1
        while lo<hi:
            mid=(lo+hi)//2
            if cumulative(mid,B-1)>rank:hi=mid
            else:lo=mid+1
        x=lo;lo,hi=0,B-1
        while lo<hi:
            mid=(lo+hi)//2
            if cumulative(x,mid)>rank:hi=mid
            else:lo=mid+1
        selections.append([str(x),str(lo)])
    box_counts=[]
    for box in q['boxes']:
        (al,ah),(bl,bh)=[list(map(int,pair)) for pair in box]
        box_counts.append(str(sum(progression(a,moduli(p,s)[0],al,ah,A)*progression(b,moduli(p,s)[1],bl,bh,B) for a,b,s in balls)))
    membership=[]
    for value in q['values']:
        x,y=map(int,value)
        membership.append(0<=x<A and 0<=y<B and any((x-a)%moduli(p,s)[0]==0 and (y-b)%moduli(p,s)[1]==0 for a,b,s in balls))
    return dict(moduli=[str(A),str(B)],count=str(count),balls=[dict(residues=[str(a),str(b)],exponent=s) for a,b,s in balls],selections=selections,box_counts=box_counts,membership=membership)
