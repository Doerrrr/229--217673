"""AUTHOR finite-witness startup control. Not a general completion algorithm.

This is used only in the privileged Oracle startup trial; it is never copied
into the public candidate image or presented as an external model answer.
"""
import argparse,json,os,sys,tempfile
from pathlib import Path
from interface import load_document
from graphs import structural

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:queries=load_document(a.input)
    except Exception as e:print('invalid input: '+str(e),file=sys.stderr);raise SystemExit(2)
    catalogue=json.loads(Path(__file__).with_name('finite_witnesses.json').read_bytes());results=[]
    for ident,n,kr,kb,fixed,degrees,cuts in queries:
        query=dict(id=ident,n=n,red_forbid=kr,blue_forbid=kb,fixed=fixed,degrees=degrees,
                   cuts=[dict(left=[i for i in range(n) if left>>i&1],right=[i for i in range(n) if right>>i&1],min=low,max=high) for left,right,low,high in cuts])
        result=dict(id=ident,state='UNSOLVED',rows=None)
        # Catalogue feasibility is checked against every supplied constraint;
        # there is no equality check against an instance ID or input digest.
        for rows in catalogue:
            if len(rows)!=n:continue
            candidate=dict(id=ident,state='COMPLETE',rows=rows)
            if structural(query,candidate)[0]:result=candidate;break
        results.append(result)
    temporary=None;target=Path(a.output)
    try:
        target.parent.mkdir(parents=True,exist_ok=True);fd,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',dir=target.parent)
        with os.fdopen(fd,'w') as f:
            for row in results:f.write(json.dumps(row,separators=(',',':'))+'\n')
        os.replace(temporary,target)
    except OSError as e:print(str(e),file=sys.stderr);raise SystemExit(3)
    finally:
        if temporary and Path(temporary).exists():Path(temporary).unlink()
if __name__=='__main__':main()
