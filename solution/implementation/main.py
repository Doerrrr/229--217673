"""AUTHOR finite witness startup control, not a general optimizer."""
import argparse,copy,json,os,sys,tempfile
from pathlib import Path
from interface import parse_document,parse_query
from algebra import check

def key(q):
    return (q['n'],tuple(q['basis']),tuple(sorted(q['terms'])))

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        queries=parse_document(Path(a.input).read_bytes().decode('utf-8-sig'))
        catalogue=json.loads(Path(__file__).with_name('finite_witnesses.json').read_bytes())
        catalogue={key(parse_query(c['query'],0)):c for c in catalogue}
        rows=[]
        for q in queries:
            c=catalogue.get(key(q))
            row=dict(id=q['id'],state='UNSOLVED',assignment=None,value=None,gram=None)
            if c:
                row=copy.deepcopy(c['answer']);row['id']=q['id']
                # Recheck exact identity, attained value and PSD before emission.
                target=dict(id=q['id'],n=q['n'],basis=[list(v) for v in q['basis']],terms=[dict(vars=list(v),coef=str(k)) for v,k in q['terms']])
                assert check(target,row,c['optimum'])[:2]==(True,True)
            rows.append(row)
    except Exception as e:
        print('invalid input or witness: '+str(e),file=sys.stderr);raise SystemExit(2)
    temporary=None;target=Path(a.output)
    try:
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',dir=target.parent)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            for row in rows:f.write(json.dumps(row,separators=(',',':'))+'\n')
        os.replace(temporary,target)
    except OSError as e:
        print(str(e),file=sys.stderr);raise SystemExit(3)
    finally:
        if temporary and Path(temporary).exists():Path(temporary).unlink()
if __name__=='__main__':main()
