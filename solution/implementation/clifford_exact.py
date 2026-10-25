"""Exact Clifford amplitudes by affine paths and quadratic Z/4 Gauss sums."""
from fractions import Fraction
from contract import keys,integer

def validate(q):
    keys(q,('id','n','gates','targets'));integer(q['n'],1,64);n=q['n']
    if type(q['gates'])is not list or len(q['gates'])>512:raise ValueError('gates')
    hs=0
    for gate in q['gates']:
        if type(gate)is not dict:raise ValueError('gate')
        kind=gate.get('gate')
        if kind in ('H','S','SDG','X','Y','Z'):
            keys(gate,('gate','q'));integer(gate['q'],0,n-1);hs+=int(kind=='H')
        elif kind in ('CX','CZ','SWAP'):
            keys(gate,('gate','a','b'));integer(gate['a'],0,n-1);integer(gate['b'],0,n-1)
            if gate['a']==gate['b']:raise ValueError('distinct wires')
        else:raise ValueError('gate kind')
    if hs>96:raise ValueError('Hadamard count')
    ts=q['targets']
    if type(ts)is not list or not 1<=len(ts)<=8 or any(type(s)is not str or len(s)!=n or any(x not in '01' for x in s) for s in ts) or len(set(ts))!=len(ts):raise ValueError('targets')

def bits(mask):
    while mask:
        b=mask&-mask;yield b.bit_length()-1;mask-=b

def xor(a,b):return (a[0]^b[0],a[1]^b[1])

class Phase:
    def __init__(self,n):self.n=n;self.constant=0;self.linear=[0]*n;self.adj=[0]*n;self.active=(1<<n)-1
    def cross(self,i,j):
        if i==j:self.linear[i]=(self.linear[i]+2)%4
        else:self.adj[i]^=1<<j;self.adj[j]^=1<<i
    def add_bit(self,expr,weight):
        c,mask=expr;weight%=4;self.constant=(self.constant+weight*c)%4
        if not weight:return
        indices=list(bits(mask))
        for i in indices:self.linear[i]=(self.linear[i]+weight*(1-2*c))%4
        if weight%2:
            for at,i in enumerate(indices):
                for j in indices[at+1:]:self.cross(i,j)
    def add_product2(self,a,b):
        ca,ma=a;cb,mb=b;self.constant=(self.constant+2*ca*cb)%4
        if ca:
            for j in bits(mb):self.linear[j]=(self.linear[j]+2)%4
        if cb:
            for i in bits(ma):self.linear[i]=(self.linear[i]+2)%4
        for i in bits(ma):
            for j in bits(mb):self.cross(i,j)
    def remove(self,i):
        c=self.linear[i];adj=self.adj[i]
        for j in bits(adj):self.adj[j]&=~(1<<i)
        self.linear[i]=0;self.adj[i]=0;self.active&=~(1<<i)
        return c,adj
    def substitute(self,i,expr):
        c,adj=self.remove(i);self.add_bit(expr,c)
        for j in bits(adj):self.add_product2(expr,(0,1<<j))
    def gauss(self):
        real,imag=1,0
        while self.active:
            i=next((j for j in bits(self.active) if self.linear[j]%2),None)
            if i is not None:
                c,adj=self.remove(i);sign=1 if c==1 else -1
                real,imag=real-sign*imag,imag+sign*real
                self.add_bit((0,adj),-c)
                continue
            i=next(bits(self.active));c,adj=self.remove(i)
            if not adj:
                if c==2:return 0,0
                real*=2;imag*=2
            else:
                j=next(bits(adj));self.substitute(j,(c//2,adj&~(1<<j)));real*=2;imag*=2
        for _ in range(self.constant%4):real,imag=-imag,real
        return real,imag

def compile_circuit(q,collect_projects=False):
    count=sum(g['gate']=='H' for g in q['gates']);phase=Phase(count);labels=[(0,0)]*q['n'];h=0;projects=[]
    for g in q['gates']:
        tag=g['gate']
        if tag in ('H','S','SDG','X','Y','Z'):
            wire=g['q'];old=labels[wire]
            if tag=='H':
                fresh=(0,1<<h);h+=1;phase.add_product2(old,fresh);labels[wire]=fresh
            elif tag in ('S','SDG','Z'):phase.add_bit(old,{'S':1,'SDG':3,'Z':2}[tag])
            else:
                if tag=='Y':phase.constant=(phase.constant+1)%4;phase.add_bit(old,2)
                labels[wire]=(old[0]^1,old[1])
        elif tag=='POST':projects.append((labels[g['q']],g['outcome']))
        elif tag=='CX':labels[g['b']]=xor(labels[g['b']],labels[g['a']])
        elif tag=='CZ':phase.add_product2(labels[g['a']],labels[g['b']])
        else:labels[g['a']],labels[g['b']]=labels[g['b']],labels[g['a']]
    return (phase,labels,count,projects) if collect_projects else (phase,labels,count)

def constrained_gauss(phase,labels,target,constraints=()):
    pivots={}
    for expr,value in list(zip(labels,target))+list(constraints):
        rhs=expr[0]^int(value);mask=expr[1]
        while mask:
            i=mask.bit_length()-1
            if i in pivots:other,bit=pivots[i];mask^=other;rhs^=bit
            else:pivots[i]=(mask,rhs);break
        if not mask and rhs:return 0,0
    free=[i for i in range(phase.n) if i not in pivots];exprs=[None]*phase.n
    for j,i in enumerate(free):exprs[i]=(0,1<<j)
    for i in sorted(pivots):
        mask,rhs=pivots[i];expr=(rhs,0)
        for j in bits(mask&~(1<<i)):expr=xor(expr,exprs[j])
        exprs[i]=expr
    reduced=Phase(len(free));reduced.constant=phase.constant
    for i,c in enumerate(phase.linear):
        if c:reduced.add_bit(exprs[i],c)
    for i,adj in enumerate(phase.adj):
        for j in bits(adj&~((1<<(i+1))-1)):reduced.add_product2(exprs[i],exprs[j])
    return reduced.gauss()

def solve(q):
    phase,labels,h=compile_circuit(q);amplitudes=[];probabilities=[]
    for target in q['targets']:
        a,b=constrained_gauss(phase,labels,target);den=1<<((h+1)//2)
        aa=str(Fraction(a,den));bb=str(Fraction(b,den))
        amplitudes.append(dict(real=[aa,'0'] if h%2==0 else ['0',aa],imag=[bb,'0'] if h%2==0 else ['0',bb]))
        probabilities.append(str(Fraction(a*a+b*b,1<<h)))
    return dict(amplitudes=amplitudes,probabilities=probabilities)
