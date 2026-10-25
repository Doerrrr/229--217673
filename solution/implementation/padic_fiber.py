"""General digit-lifting with content reduction and canonical ball coalescing."""
from math import comb
import re
from contract import keys,integer

DECIMAL=re.compile(r'[+-]?[0-9]+\Z',re.ASCII)

def decimal(x,nonnegative=False):
    if not isinstance(x,str) or not 1<=len(x)<=80 or not DECIMAL.fullmatch(x):raise ValueError('integer string')
    value=int(x)
    if nonnegative and value<0:raise ValueError('negative rank')
    return value

def validate(q):
    keys(q,('id','p','k','coefficients','ranks','ranges','values'))
    if type(q['p']) is not int or q['p'] not in (2,3,5,7):raise ValueError('prime')
    integer(q['k'],1,24)
    cs=q['coefficients']
    if not isinstance(cs,list) or not 1<=len(cs)<=13:raise ValueError('degree')
    for c in cs:integer(c,-10**12,10**12)
    for name in ('ranks','ranges','values'):
        if not isinstance(q[name],list) or len(q[name])>32:raise ValueError('query list size')
    for x in q['ranks']:decimal(x,True)
    for x in q['values']:decimal(x)
    for pair in q['ranges']:
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('range shape')
        a,b=map(decimal,pair)
        if a>b:raise ValueError('range order')

def evaluate(c,x,mod):
    value=0
    for a in reversed(c):value=(value*x+a)%mod
    return value

def root_balls(coeff,p,k):
    def visit(c,h,a,s):
        mod=p**h;c=[x%mod for x in c]
        valuation=h
        for x in c:
            if not x:continue
            v=0
            while x%p==0:x//=p;v+=1
            valuation=min(valuation,v)
        if valuation>=h:return [(a,s)]
        c=[x//(p**valuation) for x in c];h-=valuation;mod=p**h
        if s==k:return [(a,s)] if c[0]%mod==0 else []
        result=[]
        for digit in range(p):
            if evaluate(c,digit,p):continue
            next_c=[sum(c[i]*comb(i,j)*digit**(i-j) for i in range(j,len(c)))*(p**j)%mod for j in range(len(c))]
            result.extend(visit(next_c,h,a+(p**s)*digit,s+1))
        if len(result)==p and set(result)=={(a+(p**s)*digit,s+1) for digit in range(p)}:return [(a,s)]
        return result
    return sorted(visit(coeff,k,0,0),key=lambda b:(b[1],b[0]))

def solve(q):
    p,k=q['p'],q['k'];mod=p**k
    balls=root_balls(q['coefficients'],p,k)
    count=sum(p**(k-s) for a,s in balls)
    def at_most(x):
        if x<0:return 0
        if x>=mod:return count
        return sum(max(0,min(p**(k-s),(x-a)//(p**s)+1)) for a,s in balls)
    selections=[]
    for raw in q['ranks']:
        rank=int(raw)
        if rank>=count:selections.append(None);continue
        left,right=0,mod-1
        while left<right:
            middle=(left+right)//2
            if at_most(middle)>rank:right=middle
            else:left=middle+1
        selections.append(str(left))
    ranges=[str(at_most(int(b))-at_most(int(a)-1)) for a,b in q['ranges']]
    membership=[0<=int(raw)<mod and any((int(raw)-a)%(p**s)==0 for a,s in balls) for raw in q['values']]
    return dict(modulus=str(mod),count=str(count),balls=[dict(residue=str(a),exponent=s) for a,s in balls],selections=selections,range_counts=ranges,membership=membership)
