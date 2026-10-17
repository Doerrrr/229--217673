"""PRIVATE exact verifier, not an optimization algorithm."""
from fractions import Fraction
import re

RATIONAL=re.compile(r'[+-]?[0-9]+(?:/[0-9]+)?\Z')

def rational(s,limit=128):
    if not isinstance(s,str) or not 1<=len(s)<=limit or not RATIONAL.fullmatch(s):raise ValueError('rational string required')
    if '/' in s and int(s.split('/')[1])<=0:raise ValueError('positive denominator required')
    return Fraction(s)

def mask(vs):
    b=0
    for i in vs:b|=1<<i
    return b

def value(q,x):
    result=Fraction(0)
    for term in q['terms']:
        sign=1
        for i in term['vars']:sign*=x[i]
        result+=rational(term['coef'],80)*sign
    return result

def psd_exact(matrix):
    """Rational Schur complements. Zero pivot with nonzero row is not PSD."""
    A=[r[:] for r in matrix];n=len(A)
    if any(A[i][j]!=A[j][i] for i in range(n) for j in range(i)):return False,'asymmetric Gram'
    for k in range(n):
        p=A[k][k]
        if p<0:return False,dict(negative_pivot=k,pivot=str(p))
        if p==0:
            if any(A[k][j] for j in range(k+1,n)):return False,dict(zero_pivot_nonzero_row=k)
            continue
        for i in range(k+1,n):
            if not A[i][k]:continue
            ratio=A[i][k]/p
            for j in range(i,n):
                A[i][j]-=ratio*A[k][j]
                A[j][i]=A[i][j]
    return True,'exact PSD'

def check(q,row,optimum):
    evidence={};point=False;proof=False
    try:
        if not isinstance(row,dict) or set(row)!={'id','state','assignment','value','gram'} or row['id']!=q['id']:return False,False,'output fields/id'
        if row['state']=='UNSOLVED':
            return False,False,'UNSOLVED' if all(row[k] is None for k in ('assignment','value','gram')) else 'malformed UNSOLVED'
        if row['state'] not in ('INCUMBENT','CERTIFIED'):return False,False,'output state'
        x=row['assignment']
        if not isinstance(x,list) or len(x)!=q['n'] or any(type(z)is not int or z not in (-1,1) for z in x):return False,False,'assignment'
        declared=rational(row['value']);actual=value(q,x);opt=rational(optimum)
        point=declared==actual==opt
        evidence.update(actual=str(actual),certified_optimum=optimum,declared_matches_actual=declared==actual)
        if row['state']=='INCUMBENT':return point,False,{**evidence,'proof':'not supplied' if row['gram'] is None else 'INCUMBENT must have null Gram'}
        m=len(q['basis']);raw=row['gram']
        if not isinstance(raw,list) or len(raw)!=m or any(not isinstance(r,list) or len(r)!=m for r in raw):return point,False,{**evidence,'proof':'Gram shape'}
        Q=[[rational(z) for z in line] for line in raw]
        got={};basis=[mask(z) for z in q['basis']]
        for i in range(m):
            for j in range(m):
                key=basis[i]^basis[j];got[key]=got.get(key,Fraction(0))+Q[i][j]
        want={mask(t['vars']):rational(t['coef'],80) for t in q['terms']}
        want[0]=want.get(0,Fraction(0))-declared
        keys=set(got)|set(want)
        bad=next((k for k in sorted(keys) if got.get(k,0)!=want.get(k,0)),None)
        if bad is not None:return point,False,{**evidence,'proof':'identity mismatch','monomial_mask':bad,'gap':str(got.get(bad,0)-want.get(bad,0))}
        okay,why=psd_exact(Q)
        return point,point and okay,{**evidence,'proof':why}
    except (ValueError,TypeError,KeyError,ZeroDivisionError,ArithmeticError,OverflowError):
        return point,False,{**evidence,'proof':'malformed rational/certificate'}
