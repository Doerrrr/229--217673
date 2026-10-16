"""Immutable generation construction, verification, CAS, and pinned reads."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
from phase_codec import canonical, digest, model_from_records, violated, evaluate, statement
import ledger
from prover import optimize, check_certificate
from core import Failure, require, read_json, keys, generation, hash_file, save, sync_dir, lock, loads

def switch_pointer(store,value):
    """On an explicit post-rename sync error, restore the previous pointer.

    SIGKILL is different: it may leave either complete generation selected.
    The immutable data files were synced before this function is entered.
    """
    fd,name=tempfile.mkstemp(prefix='.CURRENT-new-',dir=store);backup=name+'-old';changed=False
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(canonical(value)+b'\n');stream.flush();os.fsync(stream.fileno())
        if (store/'CURRENT').exists():os.link(store/'CURRENT',backup)
        sync_dir(store)
        try:os.replace(name,store/'CURRENT');changed=True;sync_dir(store)
        except OSError:
            if changed:
                if os.path.exists(backup):os.replace(backup,store/'CURRENT')
                else:(store/'CURRENT').unlink(missing_ok=True)
                try:sync_dir(store)
                except OSError:pass
            raise
    finally:
        for temporary in (name,backup):
            try:os.unlink(temporary)
            except FileNotFoundError:pass

def current(store):
    path=store/'CURRENT'
    if not path.exists():return 'NONE'
    value=read_json(path);keys(value,('generation','manifest_sha256'),5)
    require(generation(value['generation']) and value['generation']!='NONE','invalid current pointer',5)
    require(hash_file(store/'generations'/value['generation']/'manifest.json')['sha256']==value['manifest_sha256'],'current manifest digest mismatch',5)
    return value['generation']

def row_stream(path):
    with open(path,'rb') as f:
        for line in f:
            require(bool(line.strip()),'empty artifact row',5);yield loads(line,5)

def write_rows(path,rows):
    with open(path,'wb') as f:
        for row in rows:f.write(canonical(row)+b'\n')
        f.flush();os.fsync(f.fileno())

def projection(fact,point,gid):
    value=dict(fact['record']);gt=value['gt']
    if point[value['block']]:value['gt']=gt[::-1]
    return dict(value,id=fact['id'],origin=fact['origin'],generation=gid)

def provenance(fact,decision):
    kind=fact['kind'];r=fact['record']
    if kind=='QUOTA':source=fact['id'];outcome='POLICY'
    else:
        source=r['source']
        if decision['status']=='UNSAT':outcome='UNRESOLVED'
        elif kind=='OBSERVATION':outcome='PROJECTED'
        else:outcome='DROPPED' if violated(r,decision['assignment']) else 'KEPT'
    return dict(kind=kind,id=fact['id'],origin=fact['origin'],source=source,outcome=outcome)

def prepare_artifacts(store,session,meta):
    gid=digest(dict(version=1,parent=meta['base'],input=meta['input']));folder=session/'prepared'
    # Only this ticket's disposable, uncommitted workspace is replaced.
    if folder.exists():shutil.rmtree(folder)
    folder.mkdir();parent=None if meta['base']=='NONE' else store/'generations'/meta['base']/'ledger.sqlite'
    db,variables=ledger.build(folder/'ledger.sqlite',parent,session/'capture.raw',meta['input'])
    try:
        model=model_from_records(variables,ledger.records(db));meta['state']='MODELED';meta['model_id']=digest(model);save(session/'session.json',meta)
        save(folder/'model.json',model)
        decision,claim=optimize(model,folder)
        if decision['status']!='UNSAT':decision['dropped']=[e['id'] for e in ledger.records(db,'EVIDENCE') if violated(e['record'],decision['assignment'])]
        save(folder/'decision.json',decision);save(folder/'statement.json',claim)
        meta['state']='PROVED';meta['statement_id']=digest(claim);save(session/'session.json',meta)
        write_rows(folder/'facts.jsonl',ledger.records(db))
        write_rows(folder/'provenance.jsonl',(provenance(f,decision) for f in ledger.records(db)))
        db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,chrom TEXT,pos INTEGER,sample TEXT,payload TEXT)');db.execute('DELETE FROM calls')
        if decision['status']!='UNSAT':
            for f in ledger.records(db,'OBSERVATION'):
                value=projection(f,decision['assignment'],gid)
                db.execute('INSERT INTO calls VALUES(?,?,?,?,?)',(f['id'],value['chrom'],value['position'],value['sample'],canonical(value).decode()))
        db.execute('CREATE INDEX IF NOT EXISTS calls_order ON calls(chrom,pos,sample,id)');db.commit()
        write_rows(folder/'calls.jsonl',(loads(r[0]) for r in db.execute('SELECT payload FROM calls ORDER BY chrom,pos,sample,id')))
    finally:db.close()
    shutil.copyfile(session/'capture.raw',folder/'input.raw')
    # Search CNFs are scratch. The independently reconstructed CNF is the authority.
    for name in ('problem.cnf','checked.cnf'):
        (folder/name).unlink(missing_ok=True)
    files={}
    for path in sorted(folder.iterdir()):
        with path.open('rb') as f:os.fsync(f.fileno())
        files[path.name]=hash_file(path)
    manifest=dict(version=1,generation=gid,parent=meta['base'],input=meta['input'],variables=variables,model_id=digest(model),provenance_id=files['provenance.jsonl']['sha256'],statement_id=digest(claim),files=files)
    save(folder/'manifest.json',manifest);sync_dir(folder)
    manifest=verify_folder(folder,store)
    require(manifest['parent']==meta['base'] and manifest['input']==meta['input'] and manifest['generation']==gid,'prepared declaration no longer belongs to ticket baseline',5)
    meta['generation']=gid;meta['state']='PREPARED';save(session/'session.json',meta)
    return dict(stage='PREPARED',ticket=meta['ticket'],generation=gid,model_id=manifest['model_id'],statement_id=manifest['statement_id'])

def inspect_files(folder):
    manifest=read_json(folder/'manifest.json');keys(manifest,('version','generation','parent','input','variables','model_id','provenance_id','statement_id','files'),5)
    require(type(manifest['version'])is int and manifest['version']==1 and generation(manifest['parent']),'invalid manifest identity',5)
    require(manifest['generation']==digest(dict(version=1,parent=manifest['parent'],input=manifest['input'])),'generation does not bind input',5)
    files=manifest['files'];require(type(files)is dict,'invalid files manifest',5)
    required={'facts.jsonl','model.json','decision.json','statement.json','certificate.drat','calls.jsonl','provenance.jsonl','input.raw','ledger.sqlite'}
    require(required<=set(files),'incomplete generation',5)
    require(set(files)=={p.name for p in folder.iterdir()}-{'manifest.json'},'unlisted generation files',5)
    for name,want in files.items():
        p=folder/name;require(p.name==name and not p.is_symlink() and p.is_file(),'invalid generation file',5)
        require(hash_file(p)==want,'generation file digest mismatch: '+name,5)
    require(hash_file(folder/'input.raw')==manifest['input']['source'],'raw source binding mismatch',5)
    return manifest

def verify_folder(folder,store):
    """Reconstruct all ancestral inputs, not just a candidate-supplied CNF or cost."""
    chain=[];seen=set();cursor=folder
    while True:
        m=inspect_files(cursor);gid=m['generation'];require(gid not in seen,'generation cycle',5);seen.add(gid);chain.append((cursor,m))
        if m['parent']=='NONE':break
        cursor=store/'generations'/m['parent']
    with tempfile.TemporaryDirectory(prefix='phase-verify-') as tmp:
        previous=None
        for index,(source,m) in enumerate(reversed(chain)):
            rebuilt=Path(tmp)/('replay-'+str(index)+'.sqlite')
            try:db,variables=ledger.build(rebuilt,previous,source/'input.raw',m['input'])
            except Failure as e:raise Failure(5,'archived history is not valid') from e
            try:
                rows=iter(row_stream(source/'facts.jsonl'))
                for expected in ledger.records(db):require(next(rows,None)==expected,'facts do not replay from original bytes',5)
                require(next(rows,None) is None,'extra active facts',5)
                model=model_from_records(variables,ledger.records(db));require(model==read_json(source/'model.json') and m['variables']==variables and m['model_id']==digest(model),'mathematical model binding mismatch',5)
            finally:db.close()
            if previous:Path(previous).unlink()
            previous=rebuilt
        db=sqlite3.connect(previous)
        try:
            decision=read_json(folder/'decision.json');keys(decision,('status','assignment','dropped','cost'),5)
            if decision['status']=='UNSAT':require(all(decision[k] is None for k in ('assignment','dropped','cost')),'invalid UNSAT result',5)
            else:
                require(decision['status'] in ('SAT','REPAIRED'),'uncertified decision',5)
                try:valid,cost,_=evaluate(model,decision['assignment'])
                except (ValueError,TypeError) as e:raise Failure(5,'invalid point') from e
                drops=[f['id'] for f in ledger.records(db,'EVIDENCE') if violated(f['record'],decision['assignment'])]
                require(valid and type(decision['cost'])is int and cost==decision['cost'] and decision['dropped']==drops and (cost==0)==(decision['status']=='SAT'),'invalid cost, quota, or withdrawal',5)
            expected,raw=statement(model,decision['status'],decision['cost']);claim=read_json(folder/'statement.json')
            require(claim==expected and digest(claim)==chain[0][1]['statement_id'],'certificate declaration mismatch',5)
            check_certificate(raw,folder/'certificate.drat',tmp)
            require(hash_file(folder/'provenance.jsonl')['sha256']==chain[0][1]['provenance_id'],'provenance identity mismatch',5)
            rows=iter(row_stream(folder/'provenance.jsonl'))
            for f in ledger.records(db):require(next(rows,None)==provenance(f,decision),'provenance outcome mismatch',5)
            require(next(rows,None) is None,'extra provenance',5)
            db.execute('CREATE TABLE expected_calls(id TEXT PRIMARY KEY,chrom TEXT,pos INTEGER,sample TEXT,payload TEXT)')
            if decision['status']!='UNSAT':
                for f in ledger.records(db,'OBSERVATION'):
                    r=projection(f,decision['assignment'],chain[0][1]['generation']);db.execute('INSERT INTO expected_calls VALUES(?,?,?,?,?)',(f['id'],r['chrom'],r['position'],r['sample'],canonical(r).decode()))
            rows=iter(row_stream(folder/'calls.jsonl'))
            for row in db.execute('SELECT payload FROM expected_calls ORDER BY chrom,pos,sample,id'):require(next(rows,None)==loads(row[0]),'phase projection mismatch',5)
            require(next(rows,None) is None,'unexpected calls for this conclusion',5)
            index_db=sqlite3.connect('file:'+str(folder/'ledger.sqlite')+'?mode=ro',uri=True)
            try:
                actual=iter(ledger.records(index_db))
                for fact in ledger.records(db):require(next(actual,None)==fact,'active index is not bound to facts',5)
                require(next(actual,None) is None,'extra indexed fact',5)
                actual=iter(index_db.execute('SELECT payload FROM calls ORDER BY chrom,pos,sample,id'))
                for row in db.execute('SELECT payload FROM expected_calls ORDER BY chrom,pos,sample,id'):require(next(actual,None)==row,'query index is not bound to calls',5)
                require(next(actual,None) is None,'extra indexed observation',5)
            finally:index_db.close()
        finally:db.close()
    return chain[0][1]

def commit(store,session,meta,expect):
    require(meta['state'] in ('PREPARED','COMMITTED'),'ticket has no certified version',8)
    gid=meta['generation'];target=store/'generations'/gid
    folder=target if target.exists() else session/'prepared'
    manifest=verify_folder(folder,store)
    require(manifest['parent']==meta['base'] and manifest['input']==meta['input'] and manifest['generation']==gid,'ticket baseline and prepared declaration differ',5)
    with lock(store/'.commit.lock'):
        now=current(store)
        if now==gid:
            require(expect==meta['base'],'idempotent request has wrong baseline',7)
        else:
            require(now==expect==meta['base'],'current version changed',7)
            if target.exists():
                # A previous crash may have installed the immutable directory only.
                require(read_json(target/'manifest.json')==read_json(folder/'manifest.json'),'generation collision',5)
            else:
                target.parent.mkdir(parents=True,exist_ok=True);os.rename(folder,target);sync_dir(target.parent)
            switch_pointer(store,dict(generation=gid,manifest_sha256=hash_file(target/'manifest.json')['sha256']))
    meta['state']='COMMITTED'
    # CURRENT is the commit record. Session labels are recoverable bookkeeping;
    # an error updating that label cannot undo an already acknowledged commit.
    try:save(session/'session.json',meta)
    except OSError:pass
    return dict(stage='COMMITTED',ticket=meta['ticket'],generation=gid)

def is_descendant(store,new,old):
    while new!='NONE':
        if new==old:return True
        new=read_json(store/'generations'/new/'manifest.json')['parent']
    return old=='NONE'

def resolve(store,gid):
    if gid=='CURRENT':gid=current(store)
    require(generation(gid) and gid!='NONE','no selected generation',5)
    return store/'generations'/gid

@contextmanager
def query_output(store,args):
    folder=resolve(store,args.generation);verify_folder(folder,store)
    # Complete validation precedes stdout, including indexes used for point queries.
    with tempfile.TemporaryFile(mode='w+b') as out:
        if args.view=='decision':out.write(canonical(read_json(folder/'decision.json'))+b'\n')
        elif args.view=='calls' and args.id:
            db=sqlite3.connect('file:'+str(folder/'ledger.sqlite')+'?mode=ro',uri=True)
            try:
                for row in db.execute('SELECT payload FROM calls WHERE id=?',(args.id,)):out.write(canonical(loads(row[0]))+b'\n')
            finally:db.close()
        else:
            for row in row_stream(folder/(args.view+'.jsonl')):
                if not args.id or row['id']==args.id:out.write(canonical(row)+b'\n')
        out.seek(0);yield out
