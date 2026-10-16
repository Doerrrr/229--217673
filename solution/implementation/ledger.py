"""Disk-backed historical replay. A retraction disables its original operation."""
from pathlib import Path
import sqlite3
from core import Failure, require, loads, keys, identifier, integer, validate_record, canonical

SCHEMA='''
CREATE TABLE IF NOT EXISTS variables(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS history(n INTEGER PRIMARY KEY,batch TEXT,seq INTEGER,op TEXT,kind TEXT,id TEXT,payload TEXT,ordinal INTEGER,UNIQUE(batch,seq));
CREATE TABLE IF NOT EXISTS disabled(batch TEXT,seq INTEGER,PRIMARY KEY(batch,seq));
CREATE TABLE IF NOT EXISTS active(kind TEXT,id TEXT,payload TEXT,batch TEXT,seq INTEGER,ordinal INTEGER,PRIMARY KEY(kind,id));
'''

def connect(path):
    db=sqlite3.connect(path);db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA journal_mode=DELETE');db.executescript(SCHEMA);return db

def build(path,parent,raw,inp):
    if Path(path).exists():Path(path).unlink()
    db=connect(path)
    if parent:
        old=sqlite3.connect('file:'+str(parent)+'?mode=ro',uri=True)
        try:old.backup(db)
        finally:old.close()
    require(not db.execute('SELECT 1 FROM batches WHERE id=?',(inp['batch_id'],)).fetchone(),'batch is already in baseline')
    db.executemany('INSERT OR IGNORE INTO variables VALUES(?)',[(v,) for v in inp['variables']]);known={r[0] for r in db.execute('SELECT id FROM variables')}
    require(len(known)<=128,'too many phase variables')
    db.execute('INSERT INTO batches VALUES(?)',(inp['batch_id'],));ordinal=0;last_seq=0
    count=db.execute('SELECT COUNT(*) FROM history').fetchone()[0]
    try:
        with open(raw,'rb') as stream:
            first=True
            while True:
                line=stream.readline(65538)
                if not line:break
                require(len(line)<=65536,'event line exceeds limit')
                if first and line.startswith(b'\xef\xbb\xbf'):line=line[3:]
                first=False
                if not line.strip():continue
                ordinal+=1;event=loads(line);op=event.get('op') if type(event)is dict else None
                expected=('seq','op','target') if op=='RETRACT' else ('seq','op','kind','id','record') if op=='PUT' else ('seq','op','kind','id')
                keys(event,expected);seq=event['seq'];require(integer(seq,1) and seq>last_seq,'event seq is not increasing');last_seq=seq
                require(op in ('PUT','DELETE','RETRACT'),'unknown event operation')
                count+=1;require(count<=2000000,'history exceeds supported size')
                if op=='RETRACT':
                    target=event['target'];keys(target,('batch_id','seq'));require(identifier(target['batch_id']) and integer(target['seq'],1),'invalid target')
                    found=db.execute('SELECT op FROM history WHERE batch=? AND seq=?',(target['batch_id'],target['seq'])).fetchone()
                    require(found is not None and found[0]!='RETRACT','target is not an earlier PUT/DELETE')
                    db.execute('INSERT OR IGNORE INTO disabled VALUES(?,?)',(target['batch_id'],target['seq']))
                    kind=rid=None;payload=canonical(target).decode()
                else:
                    kind=event['kind'];rid=event['id'];require(kind in ('EVIDENCE','OBSERVATION','QUOTA') and identifier(rid),'invalid record identity')
                    if op=='PUT':validate_record(kind,event['record'],known);payload=canonical(event['record']).decode()
                    else:payload=None
                db.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?,?)',(count,inp['batch_id'],seq,op,kind,rid,payload,ordinal))
        db.execute('DELETE FROM active')
        for batch,seq,op,kind,rid,payload,ordinal in db.execute('SELECT h.batch,h.seq,h.op,h.kind,h.id,h.payload,h.ordinal FROM history h LEFT JOIN disabled d ON h.batch=d.batch AND h.seq=d.seq WHERE d.batch IS NULL AND h.op != ? ORDER BY h.n',('RETRACT',)):
            if op=='PUT':db.execute('INSERT OR REPLACE INTO active VALUES(?,?,?,?,?,?)',(kind,rid,payload,batch,seq,ordinal))
            else:db.execute('DELETE FROM active WHERE kind=? AND id=?',(kind,rid))
        db.commit();return db,sorted(known)
    except BaseException:db.close();raise

def records(db,kind=None):
    sql='SELECT kind,id,payload,batch,seq,ordinal FROM active';args=()
    if kind:sql+=' WHERE kind=?';args=(kind,)
    for k,rid,payload,batch,seq,ordinal in db.execute(sql+' ORDER BY kind,id',args):
        yield dict(kind=k,id=rid,record=loads(payload),origin=dict(batch_id=batch,seq=seq,ordinal=ordinal))
