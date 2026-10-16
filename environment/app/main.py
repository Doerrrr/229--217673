"""Phase laboratory CLI. See packet/contract.md for the current service contract."""
import argparse
import json
import sys
import commands

def parser():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    legacy=s.add_parser('legacy-export');legacy.add_argument('--input',required=True)
    for name in ('prepare','resume','commit','rebase','query','verify'):
        q=s.add_parser(name);q.add_argument('--store',required=True)
        if name in ('prepare','resume'):q.add_argument('--manifest',required=True)
        if name in ('prepare','resume','commit','rebase'):q.add_argument('--ticket',required=True)
        if name in ('prepare','rebase'):q.add_argument('--base',required=True)
        if name=='commit':q.add_argument('--expect',required=True)
        if name in ('prepare','resume','rebase'):q.add_argument('--gate')
        if name=='prepare':q.add_argument('--checkpoint-bytes',type=int);q.add_argument('--checkpoint-gate')
        if name in ('query','verify'):q.add_argument('--generation',required=True)
        if name=='query':q.add_argument('--view',required=True,choices=['decision','calls','facts','provenance']);q.add_argument('--id')
    return p

def main():
    args=parser().parse_args()
    try:
        if args.command=='legacy-export':result=commands.legacy_export(args)
        elif args.command=='prepare':result=commands.prepare(args)
        else:raise NotImplementedError('requested service operation is not available in this adapter')
        print(json.dumps(result,ensure_ascii=False))
    except FileNotFoundError as e:print(str(e),file=sys.stderr);raise SystemExit(3)
    except (ValueError,KeyError,TypeError) as e:print(str(e),file=sys.stderr);raise SystemExit(4)
    except NotImplementedError as e:print(str(e),file=sys.stderr);raise SystemExit(8)
    except OSError as e:print(str(e),file=sys.stderr);raise SystemExit(6)

if __name__=='__main__':main()
