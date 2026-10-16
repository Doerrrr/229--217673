"""Production CLI; it reads only the supplied input, never a registered fixture."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from interface import parse_document
from certificate import solve

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);a=parser.parse_args()
    try:raw=Path(a.input).read_bytes()
    except OSError as e:print(str(e),file=sys.stderr);raise SystemExit(3)
    try:queries=parse_document(raw.decode('utf-8-sig'))
    except Exception as e:print('invalid input: '+str(e),file=sys.stderr);raise SystemExit(4)
    results=[];begin=time.monotonic()
    for index,q in enumerate(queries):
        seconds=max(2,(270-(time.monotonic()-begin))/(len(queries)-index));results.append(solve(q,seconds))
    target=Path(a.output);temporary=None
    try:
        target.parent.mkdir(parents=True,exist_ok=True);fd,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',dir=target.parent)
        with os.fdopen(fd,'w') as out:
            for r in results:out.write(json.dumps(r,separators=(',',':'))+'\n')
            out.flush();os.fsync(out.fileno())
        os.replace(temporary,target)
    except OSError as e:print(str(e),file=sys.stderr);raise SystemExit(6)
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)

if __name__=='__main__':main()
