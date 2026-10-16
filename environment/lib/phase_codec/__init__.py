"""Public phase-cnf-v1 protocol encoder. No optimizer or publication implementation."""
from collections import Counter
import hashlib
import json

VERSION='phase-cnf-v1'

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def normalize_condition(record):
    """Record structural validation is the caller's responsibility."""
    if record['type']=='XOR':
        vs=sorted(v for v,n in Counter(record['vars']).items() if n%2)
        return dict(type='XOR',vars=vs,bit=record['bit'])
    seen={}
    for v,b in zip(record['vars'],record['bits']):
        if v in seen and seen[v]!=b:return dict(type='XOR',vars=[],bit=0)
        seen[v]=b
    vs=sorted(seen)
    if not vs:return dict(type='XOR',vars=[],bit=1)
    return dict(type='FORBID',vars=vs,bits=[seen[v] for v in vs])

def model_from_records(variables,records):
    """Streaming aggregation: logical groups retain costs and source multiplicities."""
    groups={};quotas={};sources=set();known=set(variables)
    for entry in records:
        kind=entry['kind'];r=entry['record']
        if kind=='QUOTA':quotas[entry['id']]=r['max_drops'];sources.add(entry['id']);continue
        sources.add(r['source'])
        if kind!='EVIDENCE':continue
        if any(v not in known for v in r['vars']):raise ValueError('undeclared variable')
        condition=normalize_condition(r);key=canonical(condition)
        if key not in groups:groups[key]=dict(condition=condition,protected=False,weight=0,counts={})
        g=groups[key]
        if r['protected']:g['protected']=True
        else:
            g['weight']+=r['cost'];g['counts'][r['source']]=g['counts'].get(r['source'],0)+1
    if len(groups)>4096 or len(sources)>64:raise ValueError('model size outside domain')
    if sum(g['weight'] for g in groups.values())>2**63-1:raise ValueError('total cost overflow')
    result=dict(version=VERSION,variables=sorted(known),groups=[groups[k] for k in sorted(groups)],quotas=quotas)
    return result

def violated(condition,assignment):
    if condition['type']=='XOR':
        v=0
        for name in condition['vars']:v^=assignment[name]
        return v!=condition['bit']
    return all(assignment[v]==b for v,b in zip(condition['vars'],condition['bits']))

def evaluate(model,assignment):
    if set(assignment)!=set(model['variables']) or any(type(v)is not int or v not in (0,1) for v in assignment.values()):raise ValueError('invalid assignment')
    cost=0;used=Counter()
    for g in model['groups']:
        if violated(g['condition'],assignment):
            if g['protected']:return False,None,dict(reason='protected condition')
            cost+=g['weight'];used.update(g['counts'])
    if any(used[s]>limit for s,limit in model['quotas'].items()):return False,None,dict(reason='source quota',used=dict(used))
    return True,cost,dict(used)

class CNF:
    """Variable 1 is true. Clause and gate construction order is normative."""
    def __init__(self):self.variables=1;self.clauses=[[1]];self.cache={}
    def new(self):self.variables+=1;return self.variables
    def clause(self,*items):
        if 1 in items:return
        values=set(items);values.discard(-1)
        if any(-v in values for v in values):return
        self.clauses.append(sorted(values,key=lambda x:(abs(x),x<0)))
    def and_(self,a,b):
        if a==-1 or b==-1 or a==-b:return -1
        if a==1:return b
        if b==1 or a==b:return a
        key=('and',*sorted((a,b)))
        if key not in self.cache:
            z=self.new();self.clause(-z,a);self.clause(-z,b);self.clause(z,-a,-b);self.cache[key]=z
        return self.cache[key]
    def or_(self,a,b):return -self.and_(-a,-b)
    def xor(self,a,b):
        if a==1:return -b
        if b==1:return -a
        if a==-1:return b
        if b==-1:return a
        if a==b:return -1
        if a==-b:return 1
        key=('xor',*sorted((a,b)))
        if key not in self.cache:
            z=self.new();self.clause(a,b,-z);self.clause(-a,-b,-z);self.clause(a,-b,z);self.clause(-a,b,z);self.cache[key]=z
        return self.cache[key]
    def weighted_sum(self,terms):
        terms=[(lit,weight) for lit,weight in terms if weight]
        width=max(1,sum(weight for _,weight in terms).bit_length());acc=[-1]*width
        for lit,weight in terms:
            carry=-1;out=[]
            for i,a in enumerate(acc):
                b=lit if weight>>i&1 else -1
                t=self.xor(a,b);out.append(self.xor(t,carry));carry=self.or_(self.and_(a,b),self.and_(t,carry))
            acc=out
        return acc
    def at_most(self,terms,bound):
        if bound<0:self.clause();return
        total=sum(w for _,w in terms)
        if bound>=total:return
        bits=self.weighted_sum(terms);equal=1
        for i in range(len(bits)-1,-1,-1):
            if bound>>i&1:equal=self.and_(equal,bits[i])
            else:self.clause(-equal,-bits[i]);equal=self.and_(equal,-bits[i])
    def bytes(self):
        header=f'p cnf {self.variables} {len(self.clauses)}\n'
        return (header+''.join(' '.join(map(str,row))+(' ' if row else '')+'0\n' for row in self.clauses)).encode('ascii')

def encode(model,bound=None):
    c=CNF();mapping={v:c.new() for v in model['variables']};bad=[]
    for g in model['groups']:
        r=g['condition']
        if r['type']=='XOR':
            lit=-1
            for v in r['vars']:lit=c.xor(lit,mapping[v])
            if r['bit']:lit=-lit
        else:
            lit=1
            for v,b in zip(r['vars'],r['bits']):lit=c.and_(lit,mapping[v] if b else -mapping[v])
        bad.append(lit)
        if g['protected']:c.clause(-lit)
    for source,limit in sorted(model['quotas'].items()):
        c.at_most([(lit,g['counts'].get(source,0)) for lit,g in zip(bad,model['groups']) if g['counts'].get(source,0)],limit)
    if bound is not None:c.at_most([(lit,g['weight']) for lit,g in zip(bad,model['groups']) if g['weight']],bound)
    return c.bytes(),mapping

def statement(model,status,cost):
    bound=None if status=='UNSAT' else cost-1
    raw,_=encode(model,bound)
    claim=dict(codec=VERSION,model_id=digest(model),claim='unsat' if status=='UNSAT' else 'lower_bound',bound=bound,cnf_sha256=hashlib.sha256(raw).hexdigest())
    return claim,raw
