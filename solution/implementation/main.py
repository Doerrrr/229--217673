"""Production reference CLI. All durable work remains inside the caller's store."""
from pathlib import Path
import argparse
import collections
import json
import shutil
import sys
from phase_codec import canonical
from core import Failure, require, keys, identifier, generation, manifest_input, save, read_json, lock, wait_gate
from capture import receive
from publication import prepare_artifacts, verify_folder, resolve, commit, query_output, is_descendant

def arguments():
    root=argparse.ArgumentParser(prog='phase-lab');subs=root.add_subparsers(dest='command',required=True)
    old=subs.add_parser('legacy-export');old.add_argument('--input',required=True)
    for name in ['prepare','resume','commit','rebase','query','verify']:
        cmd=subs.add_parser(name);cmd.add_argument('--store',required=True)
        for flag in (['manifest','ticket'] if name in ('prepare','resume') else ['ticket'] if name in ('commit','rebase') else ['generation']):cmd.add_argument('--'+flag,required=True)
        if name in ('prepare','rebase'):cmd.add_argument('--base',required=True)
        if name=='commit':cmd.add_argument('--expect',required=True)
        if name in ('prepare','resume','rebase'):cmd.add_argument('--gate')
        if name=='prepare':cmd.add_argument('--checkpoint-bytes',type=int);cmd.add_argument('--checkpoint-gate')
        if name=='query':cmd.add_argument('--view',choices=('decision','calls','facts','provenance'),required=True);cmd.add_argument('--id')
    return root.parse_args()

def legacy(path):
    obj=read_json(path,2);variables=obj['variables'];graph={v:[] for v in variables}
    for edge in obj['relations']:
        graph[edge['a']].append((edge['b'],edge['bit']));graph[edge['b']].append((edge['a'],edge['bit']))
    point={}
    for root in sorted(variables):
        if root in point:continue
        point[root]=0;queue=collections.deque([root])
        while queue:
            v=queue.popleft()
            for other,bit in graph[v]:
                expected=point[v]^bit
                if other in point:require(point[other]==expected,'legacy relations conflict')
                else:point[other]=expected;queue.append(other)
    calls=[]
    for row in obj['observations']:
        value=dict(row)
        if point[value['block']]:value['gt']=value['gt'][::-1]
        calls.append(value)
    calls.sort(key=lambda r:(r['chrom'],r['position'],r['sample'],r['id']))
    return dict(assignment=point,calls=calls)

def execute(args):
    if args.command=='legacy-export':return legacy(args.input)
    store=Path(args.store).resolve()
    if args.command in ('query','verify'):
        if args.command=='verify':m=verify_folder(resolve(store,args.generation),store);return dict(status='VERIFIED',generation=m['generation'])
        with query_output(store,args) as output:shutil.copyfileobj(output,sys.stdout.buffer)
        return None
    require(identifier(args.ticket),'invalid ticket',2)
    for field in ('base','expect'):
        if hasattr(args,field):require(generation(getattr(args,field)),'invalid generation argument',2)
    store.mkdir(parents=True,exist_ok=True);session=store/'sessions'/args.ticket
    with lock(store/('.ticket-'+args.ticket+'.lock'),False):
        if args.command=='prepare':
            inp,source=manifest_input(args.manifest)
            checkpoint=args.checkpoint_bytes
            require((checkpoint is None and not args.checkpoint_gate) or type(checkpoint)is int and 0<checkpoint<inp['source']['bytes'] and args.checkpoint_gate,'invalid checkpoint arguments',2)
            if args.base!='NONE':verify_folder(resolve(store,args.base),store)
            if session.exists():
                meta=read_json(session/'session.json');require(meta['input']==inp and meta['base']==args.base,'ticket identity mismatch',4)
                require(meta['state']!='CAPTURING','use resume with the remaining suffix',4)
            else:
                session.mkdir(parents=True);meta=dict(ticket=args.ticket,input=inp,base=args.base,state='CAPTURING');save(session/'session.json',meta)
            receive(session,meta,source,checkpoint,args.checkpoint_gate)
        else:
            require((session/'session.json').is_file(),'unknown ticket',5);meta=read_json(session/'session.json')
            if args.command=='commit':return commit(store,session,meta,args.expect)
            if args.command=='resume':
                inp,source=manifest_input(args.manifest);require(meta['input']==inp,'resume identity changed',4);receive(session,meta,source)
            else:
                require(meta['state']!='CAPTURING','cannot rebase incomplete capture',8)
                verify_folder(resolve(store,args.base),store);require(is_descendant(store,args.base,meta['base']),'rebase is not a descendant',4)
                # Byte identity is checked even though no source is reopened.
                receive(session,meta,Path('/nonexistent-source'))
                meta['base']=args.base;meta['state']='CAPTURED';meta.pop('generation',None);save(session/'session.json',meta)
        if meta['state']=='COMMITTED':return dict(stage='COMMITTED',ticket=args.ticket,generation=meta['generation'])
        if meta['state']=='PREPARED':
            installed=store/'generations'/meta['generation']
            verify_folder(installed if installed.exists() else session/'prepared',store);receipt={k:meta[k] for k in ('ticket','generation','model_id','statement_id')};receipt['stage']='PREPARED'
        else:receipt=prepare_artifacts(store,session,meta)
        wait_gate(args.gate,receipt);return receipt

def main():
    args=arguments()
    try:
        result=execute(args)
        if result is not None:sys.stdout.buffer.write(canonical(result)+b'\n')
    except Failure as e:print(str(e),file=sys.stderr);raise SystemExit(e.code)
    except OSError as e:print('storage I/O: '+str(e),file=sys.stderr);raise SystemExit(6)
    except (ValueError,KeyError,TypeError,UnicodeError) as e:print('invalid stored or input value: '+str(e),file=sys.stderr);raise SystemExit(5)

if __name__=='__main__':main()
