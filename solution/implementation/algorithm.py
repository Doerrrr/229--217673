"""Exact coherent postselection: affine path constraints and doubled-path norm."""
from fractions import Fraction as F
from contract import keys,integer
import clifford_exact as c

def validate(q):
    keys(q,('id','n','gates','targets'))
    if type(q['gates'])is not list or len(q['gates'])>512:raise ValueError('gates')
    rest=[];posts=0
    for gate in q['gates']:
        if type(gate)is dict and gate.get('gate')=='POST':
            keys(gate,('gate','q','outcome'));integer(gate['q'],0,q['n']-1);integer(gate['outcome'],0,1);posts+=1
        else:rest.append(gate)
    if posts>32:raise ValueError('projector count')
    other={**q,'gates':rest};c.validate(other)

def norm(phase,labels,h,projects):
    double=c.Phase(2*h);double.constant=0
    for i,x in enumerate(phase.linear):double.linear[i]=x;double.linear[h+i]=(-x)%4
    for i,adj in enumerate(phase.adj):
        for j in c.bits(adj&~((1<<(i+1))-1)):
            double.cross(i,j);double.cross(h+i,h+j)
    constraints=[((0,mask^(mask<<h)),0) for constant,mask in labels]
    for (constant,mask),outcome in projects:
        constraints.extend([((constant,mask),outcome),((constant,mask<<h),outcome)])
    real,imag=c.constrained_gauss(double,[],'',constraints)
    assert imag==0 and real>=0
    return F(real,1<<h)

def solve(q):
    phase,labels,h,projects=c.compile_circuit(q,collect_projects=True)
    success=norm(phase,labels,h,projects)
    if not success:return dict(success='0',amplitudes=[dict(real=['0','0'],imag=['0','0']) for _ in q['targets']],probabilities=['0']*len(q['targets']))
    assert success.numerator==1 and success.denominator&(success.denominator-1)==0
    r=success.denominator.bit_length()-1;effective=h-r;assert effective>=0
    denominator=1<<((effective+1)//2);amplitudes=[];probabilities=[]
    for target in q['targets']:
        a,b=c.constrained_gauss(phase,labels,target,projects);aa=str(F(a,denominator));bb=str(F(b,denominator))
        amplitudes.append(dict(real=[aa,'0'] if effective%2==0 else ['0',aa],imag=[bb,'0'] if effective%2==0 else ['0',bb]))
        probabilities.append(str(F(a*a+b*b,1<<h)/success))
    return dict(success=str(success),amplitudes=amplitudes,probabilities=probabilities)
