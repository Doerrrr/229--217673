"""Input-driven finite Ramsey construction; no fixture files or query lookup."""
import argparse,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from interface import load_document
from graphs import structural
from repair import repair
from paley_search import construct

def solve(q,seconds):
    ident,n,kr,kb,fixed,degrees,cuts=q
    native_seconds=min(3,max(.05,seconds*.06));begin=time.monotonic()
    lines=[f'{n} {kr} {kb} {native_seconds:.3f}',str(len(fixed))]
    lines.extend(f'{u} {v} {c}' for u,v,c in fixed)
    lines.extend(f'{low} {high}' for low,high in degrees);lines.append(str(len(cuts)))
    for left,right,low,high in cuts:
        a=[i for i in range(n) if left>>i&1];b=[i for i in range(n) if right>>i&1]
        lines.append(' '.join(map(str,[len(a),len(b),low,high,*a,*b])))
    got=subprocess.run([str(Path(__file__).with_name('ramsey-native'))],input=('\n'.join(lines)+'\n').encode(),capture_output=True,timeout=native_seconds+3)
    rows=got.stdout.decode().splitlines();row=dict(id=ident,state='COMPLETE',rows=rows)
    query=dict(id=ident,n=n,red_forbid=kr,blue_forbid=kb,fixed=fixed,degrees=degrees,cuts=[dict(left=[i for i in range(n) if a>>i&1],right=[i for i in range(n) if b>>i&1],min=low,max=high) for a,b,low,high in cuts])
    if got.returncode==0 and structural(query,row)[0]:return row
    sat_seconds=max(.05,min(170,(seconds-(time.monotonic()-begin))*.8))
    try:
        sat=subprocess.run([sys.executable,str(Path(__file__).with_name('sat_search.py'))],input=json.dumps(dict(query=query,initial=rows,seconds=sat_seconds)).encode(),capture_output=True,timeout=sat_seconds)
        if os.environ.get('DDI031_PROFILE'):Path(os.environ['DDI031_PROFILE'],ident+'_sat.txt').write_bytes(sat.stderr)
        sat_row=dict(id=ident,state='COMPLETE',rows=sat.stdout.decode().splitlines())
        if sat.returncode==0 and structural(query,sat_row)[0]:return sat_row
    except subprocess.TimeoutExpired as e:
        if os.environ.get('DDI031_PROFILE'):Path(os.environ['DDI031_PROFILE'],ident+'_sat.txt').write_bytes(e.stderr or b'')
    embed_seconds=max(.01,min(100,(seconds-(time.monotonic()-begin))*.55));embed_lines=lines[:];embed_lines[0]=f'{n} {kr} {kb} {embed_seconds:.3f}'
    mode='embed-wide' if not cuts and all(lo==0 and hi==n-1 for lo,hi in degrees) else 'embed'
    got_embed=subprocess.run([str(Path(__file__).with_name('ramsey-native')),mode],input=('\n'.join(embed_lines)+'\n').encode(),capture_output=True,timeout=embed_seconds+3)
    if os.environ.get('DDI031_PROFILE'):
        Path(os.environ['DDI031_PROFILE'],ident+'_native.txt').write_bytes(got.stderr+got_embed.stderr)
    embedded_rows=got_embed.stdout.decode().splitlines();embedded_row=dict(id=ident,state='COMPLETE',rows=embedded_rows)
    if got_embed.returncode==0 and structural(query,embedded_row)[0]:return embedded_row
    embedded=construct(query,max(.01,min(120,(seconds-(time.monotonic()-begin))*.65)))
    if embedded is not None:return dict(id=ident,state='COMPLETE',rows=embedded)
    improved=repair(query,rows,max(.01,seconds-(time.monotonic()-begin)))
    if improved is not None:
        result=dict(id=ident,state='COMPLETE',rows=improved)
        if structural(query,result)[0]:return result
    return dict(id=ident,state='UNSOLVED',rows=None)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:queries=load_document(a.input)
    except Exception as e:print('invalid input: '+str(e),file=sys.stderr);raise SystemExit(2)
    deadline=time.monotonic()+270;rows=[]
    for i,q in enumerate(queries):
        seconds=max(.05,(deadline-time.monotonic())/(len(queries)-i));rows.append(solve(q,seconds))
    target=Path(a.output);temporary=None
    try:
        target.parent.mkdir(parents=True,exist_ok=True);fd,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',dir=target.parent)
        with os.fdopen(fd,'w') as f:
            for row in rows:f.write(json.dumps(row,separators=(',',':'))+'\n')
        os.replace(temporary,target)
    except OSError as e:print(str(e),file=sys.stderr);raise SystemExit(3)
    finally:
        if temporary and Path(temporary).exists():Path(temporary).unlink()
if __name__=='__main__':main()
