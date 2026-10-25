"""Exact binary weight spectra and registered permutation-equivalence witnesses."""
import itertools,json
from pathlib import Path
from contract import keys,integer

CATALOGUE={}

def words(rows):return [sum(bit<<j for j,bit in enumerate(row)) for row in rows]

def rank(rows):
    basis={}
    for value in words(rows):
        while value:
            i=value.bit_length()-1
            if i in basis:value^=basis[i]
            else:basis[i]=value;break
    return len(basis)

def validate(q):
    keys(q,('id','n','k','left','right'));n=integer(q['n'],1,64);k=integer(q['k'],1,min(n,18))
    for name in ('left','right'):
        matrix=q[name]
        if type(matrix)is not list or len(matrix)!=k:raise ValueError('row count')
        for row in matrix:
            if type(row)is not list or len(row)!=n:raise ValueError('column count')
            for bit in row:integer(bit,0,1)
        if rank(matrix)!=k:raise ValueError('full row rank required')

def histogram(q):
    rows=words(q['left']);counts=[0]*(q['n']+1);counts[0]=1;current=0
    for value in range(1,1<<q['k']):
        current^=rows[(value&-value).bit_length()-1];counts[current.bit_count()]+=1
    return [str(x) for x in counts]

def transformation(q,permutation):
    rows=words([[row[j] for j in permutation] for row in q['left']]);basis={}
    for i,value in enumerate(rows):
        mask=1<<i
        while value:
            col=value.bit_length()-1
            if col in basis:other,coeff=basis[col];value^=other;mask^=coeff
            else:basis[col]=(value,mask);break
    result=[]
    for value in words(q['right']):
        mask=0
        while value:
            col=value.bit_length()-1
            if col not in basis:return None
            other,coeff=basis[col];value^=other;mask^=coeff
        result.append([(mask>>i)&1 for i in range(q['k'])])
    return result

def key(q):return json.dumps({k:v for k,v in q.items() if k!='id'},sort_keys=True,separators=(',',':'))

def solve(q):
    global CATALOGUE
    from binary_code_checker import check
    file=Path(__file__).with_name('binary_code_witnesses.json')
    if not CATALOGUE and file.exists():CATALOGUE=json.loads(file.read_bytes())
    witness=CATALOGUE.get(key(q));result=dict(histogram=histogram(q),permutation=None,row_transform=None)
    if witness is None and q['n']<=9:
        for count,permutation in enumerate(itertools.permutations(range(q['n']))):
            if count>=50000:break
            u=transformation(q,permutation)
            if u is not None:witness=dict(permutation=list(permutation),row_transform=u);break
    if witness is not None:result.update(witness);assert check(q,result)
    return result

def row_state(result):return 'SOLVED' if result['permutation'] is not None else 'PARTIAL'
