"""Public command/input/output support for the sequence statistics tool."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from fractions import Fraction as F

RAT = re.compile(r'[+-]?[0-9]+(?:/[0-9]+)?\Z', re.ASCII)
IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z', re.ASCII)

def keys(o, expected):
    if not isinstance(o, dict) or set(o) != set(expected):
        raise ValueError('object fields')

def integer(v, low, high):
    if type(v) is not int or not low <= v <= high:
        raise ValueError('integer range')
    return v

def rational(v):
    if not isinstance(v, str) or not 1 <= len(v) <= 80 or not RAT.fullmatch(v):
        raise ValueError('rational syntax')
    if '/' in v and int(v.split('/')[1]) <= 0:
        raise ValueError('denominator')
    result = F(v)
    if abs(result) > 10**12:
        raise ValueError('rational magnitude')
    return result

def pairs(items):
    out = {}
    for k,v in items:
        if k in out:
            raise ValueError('duplicate JSON key')
        out[k] = v
    return out

def reject_constant(v):
    raise ValueError('nonfinite JSON constant')

def document(raw, validate):
    data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=reject_constant)
    keys(data, ('version','queries'))
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('version')
    qs = data['queries']
    if not isinstance(qs,list) or not 1 <= len(qs) <= 16:
        raise ValueError('query count')
    seen = set()
    for q in qs:
        if not isinstance(q,dict) or not isinstance(q.get('id'),str) or not IDENT.fullmatch(q['id']) or q['id'] in seen:
            raise ValueError('id')
        seen.add(q['id'])
        validate(q)
    return qs

def cli(validate, solve, row_state=None):
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    try:
        qs = document(Path(a.input).read_bytes(), validate)
        rows=[]
        for q in qs:
            result=solve(q)
            rows.append(dict(id=q['id'],state=row_state(result) if row_state else 'SOLVED',result=result))
    except Exception as e:
        print('input or computation error: '+str(e), file=sys.stderr)
        return 2
    temporary = None
    try:
        dst = Path(a.output)
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.'+dst.name+'-', dir=dst.parent)
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as h:
            for row in rows:
                h.write(json.dumps(row,separators=(',',':'))+'\n')
            h.flush()
            os.fsync(h.fileno())
        os.replace(temporary,dst)
        temporary = None
        return 0
    except OSError as e:
        print('output error: '+str(e),file=sys.stderr)
        return 3
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink()
