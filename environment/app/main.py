"""Incomplete graph completion prototype. Read packet/problem.md."""
import argparse,json
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--output');a=p.parse_args()
    if not a.input or not a.output:return
    try:
        qs=json.loads(Path(a.input).read_bytes().decode('utf-8-sig'))['queries']
        out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(''.join(json.dumps(dict(id=q['id'],state='UNSOLVED',rows=None))+'\n' for q in qs))
    except Exception:return
if __name__=='__main__':main()
