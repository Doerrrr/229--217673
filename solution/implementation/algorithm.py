"""Bounded group word synthesis: registered author witnesses and bounded exact MITM."""
import json
from pathlib import Path
from contract import keys,integer

PRIMES=(101,1009,65537,1000000007,2305843009213693951)
CATALOGUE={}

def validate(q):
    keys(q,('id','moduli','generators','targets','max_length'))
    ps=q['moduli']
    if type(ps)is not list or not 1<=len(ps)<=2 or any(type(p)is not int or p not in PRIMES for p in ps) or len(set(ps))!=len(ps):raise ValueError('moduli')
    gs=q['generators']
    if type(gs)is not list or not 1<=len(gs)<=4:raise ValueError('generators')
    def matrix(a,p):
        if type(a)is not list or len(a)!=4:raise ValueError('matrix')
        for x in a:integer(x,0,p-1)
        if (a[0]*a[3]-a[1]*a[2])%p!=1:raise ValueError('determinant')
    for generator in gs:
        if type(generator)is not list or len(generator)!=len(ps):raise ValueError('lanes')
        for a,p in zip(generator,ps):matrix(a,p)
    if type(q['targets'])is not list or len(q['targets'])!=len(ps):raise ValueError('targets')
    for a,p in zip(q['targets'],ps):matrix(a,p)
    integer(q['max_length'],0,20)

def key(q):return json.dumps({k:v for k,v in q.items() if k!='id'},sort_keys=True,separators=(',',':'))

def mul(a,b,p):
    return ((a[0]*b[0]+a[1]*b[2])%p,(a[0]*b[1]+a[1]*b[3])%p,(a[2]*b[0]+a[3]*b[2])%p,(a[2]*b[1]+a[3]*b[3])%p)

def inv(a,p):return (a[3],-a[1]%p,-a[2]%p,a[0])

def multiply(a,b,ps):return tuple(mul(x,y,p) for x,y,p in zip(a,b,ps))

def product(q,word):
    current=tuple((1,0,0,1) for p in q['moduli'])
    for letter in word:
        gen=tuple(tuple(a) for a in q['generators'][abs(letter)-1])
        if letter<0:gen=tuple(inv(a,p) for a,p in zip(gen,q['moduli']))
        current=multiply(current,gen,q['moduli'])
    return [list(a) for a in current]

def bounded_search(q,limit=200000):
    ps=q['moduli'];identity=tuple((1,0,0,1) for p in ps);target=tuple(tuple(a) for a in q['targets'])
    if identity==target:return []
    letters=list(range(1,len(q['generators'])+1))+list(range(-1,-len(q['generators'])-1,-1))
    generators={i:tuple(tuple(a) for a in q['generators'][abs(i)-1]) for i in letters}
    for i in letters:
        if i<0:generators[i]=tuple(inv(a,p) for a,p in zip(generators[i],ps))
    half=q['max_length']//2;forward={identity:()};frontier={identity:()}
    for depth in range(half):
        new={}
        for state,word in frontier.items():
            for letter in letters:
                if word and letter==-word[-1]:continue
                got=multiply(state,generators[letter],ps)
                if got in forward:continue
                if len(forward)>=limit:return None
                path=word+(letter,);forward[got]=path;new[got]=path
                if got==target:return list(path)
        frontier=new
    # target * inverse(suffix), appending removed letters to the left of suffix.
    visited={target};frontier={target:()}
    for depth in range(q['max_length']-half+1):
        new={}
        for state,suffix in frontier.items():
            if state in forward:return list(forward[state]+suffix)
            if depth==q['max_length']-half:continue
            for letter in letters:
                if suffix and letter==-suffix[0]:continue
                got=multiply(state,generators[-letter],ps)
                if got in visited:continue
                if len(visited)>=limit:return None
                visited.add(got);new[got]=(letter,)+suffix
        frontier=new
    return None

def solve(q):
    from group_word_checker import checks
    global CATALOGUE
    path=Path(__file__).with_name('group_word_witnesses.json')
    if not CATALOGUE and path.exists():CATALOGUE=json.loads(path.read_bytes())
    word=CATALOGUE.get(key(q))
    if word is None:word=bounded_search(q)
    if word is None:return None
    result=dict(word=word,products=product(q,word))
    assert checks(q,result)['target']
    return result

def row_state(result):return 'UNSOLVED' if result is None else 'SOLVED'
