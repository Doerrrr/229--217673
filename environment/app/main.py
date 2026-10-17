"""Incomplete phase-repair prototype. Read packet/problem.md."""
import argparse,json
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--output');a=p.parse_args()
    if not a.input or not a.output:return
    try:
        queries=json.loads(Path(a.input).read_text(encoding='utf-8-sig'))['queries']
        rows=[dict(id=q['id'],assignment={m:0 for m in q['markers']},dropped=[],cost=0) for q in queries]
        target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    except Exception:return
if __name__=='__main__':main()
