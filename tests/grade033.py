"""Frozen fifty-scenario judge. No answer lookup table and no candidate imports."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from runner import Runner,good,rejected
from business_check import wire,sha,replay,model,decision_ok,check_views,rows

WEIGHTS=dict(replay=.12,math=.26,proof=.20,publish=.14,recovery=.16,resource=.06,legacy=.06)

def put(kind,rid,record):return dict(op='PUT',kind=kind,id=rid,record=record)
def delete(kind,rid):return dict(op='DELETE',kind=kind,id=rid)
def retract(batch,seq):return dict(op='RETRACT',target=dict(batch_id=batch,seq=seq))
def ev(vs,bit,source='S',cost=1,protected=False):return dict(source=source,protected=protected,cost=0 if protected else cost,type='XOR',vars=vs,bit=bit)
def forbidden(vs,bits,source='S',cost=1,protected=False):return dict(source=source,protected=protected,cost=0 if protected else cost,type='FORBID',vars=vs,bits=bits)
def obs(block='x',source='O',position=1,gt='0|1'):return dict(source=source,sample='P',chrom='chr7',position=position,block=block,gt=gt)

class Scenario:
    def __init__(self,runner,name):self.r=runner;self.name=name;self.root=runner.directory(name);self.store=self.root/'store';self.history=[];self.base='NONE';self.counter=0
    def batch(self,events,variables=(),raw=None,name=None):
        self.counter+=1;name=name or ('B'+str(self.counter));events=[dict(e,seq=e.get('seq',i*3+1)) for i,e in enumerate(events)]
        if raw is None:raw=b''.join(wire(e)+b'\n' for e in events)
        source=self.r.file(self.name+'/'+name+'.jsonl',raw);manifest=self.root/(name+'.json')
        value=dict(version=1,batch_id=name,variables=list(variables),source=dict(path=str(source),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        self.r.file(self.name+'/'+name+'.json',wire(value));return manifest,(name,list(variables),raw)
    def prepare(self,manifest,ticket,base=None,extra=(),env=None):return self.r.call(['prepare','--manifest',manifest,'--store',self.store,'--base',self.base if base is None else base,'--ticket',ticket,*extra],env=env)
    def commit(self,ticket,base=None):return self.r.call(['commit','--store',self.store,'--ticket',ticket,'--expect',self.base if base is None else base])
    def publish(self,events,variables=(),raw=None):
        manifest,batch=self.batch(events,variables,raw);ticket='T'+str(self.counter)
        good(self.prepare(manifest,ticket));receipt=good(self.commit(ticket));self.base=receipt['generation'];self.history.append(batch);return self.folder()
    def folder(self):return self.store/'generations'/self.base
    def value(self):return json.loads((self.folder()/'decision.json').read_bytes())
    def expected(self):return replay(self.history)
    def check(self,views=True,expected='enumerate'):
        vs,facts=self.expected();value=self.value();decision_ok(vs,facts,value,expected)
        if views:check_views(self.folder(),vs,facts,value,self.base)
        return value
    def query(self,view='decision',gid='CURRENT',rid=None):return self.r.call(['query','--store',self.store,'--generation',gid,'--view',view,*(['--id',rid] if rid else [])])
    def verify(self):return self.r.call(['verify','--store',self.store,'--generation',self.base])

def proof_check(s):
    # The normative encoder is installed read-only, but the business model comes
    # from the independent checker above, not the candidate's model/CNF file.
    import phase_codec
    vs,facts=s.expected();value=s.value();actual_model=model(vs,facts)
    claim,cnf=phase_codec.statement(actual_model,value['status'],value['cost']);folder=s.folder()
    assert json.loads((folder/'statement.json').read_bytes())==claim
    m=json.loads((folder/'manifest.json').read_bytes());assert m['model_id']==sha(actual_model) and m['statement_id']==sha(claim)
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'expected.cnf';path.write_bytes(cnf)
        proof=folder/'certificate.drat';assert proof.stat().st_size<=256*1024*1024
        raw=proof.read_bytes();assert all(b in b'\t\n\r -d0123456789' for b in raw)
        p=subprocess.run(['drat-trim',str(path),str(proof)],capture_output=True,timeout=100)
        assert p.returncode in (0,1) and b's VERIFIED' in p.stdout.splitlines() and b's NOT VERIFIED' not in p.stdout.splitlines(),p.stdout[-1000:]

def rehash(s):
    folder=s.folder();m=json.loads((folder/'manifest.json').read_bytes())
    for name in m['files']:
        raw=(folder/name).read_bytes();m['files'][name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    m['model_id']=sha(json.loads((folder/'model.json').read_bytes()));m['statement_id']=sha(json.loads((folder/'statement.json').read_bytes()));m['provenance_id']=m['files']['provenance.jsonl']['sha256']
    (folder/'manifest.json').write_bytes(wire(m)+b'\n')
    (s.store/'CURRENT').write_bytes(wire(dict(generation=s.base,manifest_sha256=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()))+b'\n')

def suite(r,resource_size=1):
    scenarios=[]
    def case(group,name):
        def decorate(fn):scenarios.append((group,name,fn));return fn
        return decorate

    @case('replay','overwrite_retract_reveals_previous')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True))],['x'])
        s.publish([put('EVIDENCE','a',ev(['x'],1,protected=True))]);s.publish([retract('B2',1)]);s.check()
    @case('replay','delete_then_retract_delete')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True))],['x']);s.publish([delete('EVIDENCE','a')]);s.publish([retract('B2',1)]);s.check()
    @case('replay','retract_old_put_does_not_undo_new_put')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0))],['x']);s.publish([put('EVIDENCE','a',ev(['x'],1))]);s.publish([retract('B1',1)]);s.check()
    @case('replay','repeated_retraction_is_set_semantics')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],1,protected=True))],['x']);s.publish([retract('B1',1),retract('B1',1)]);s.check()
    @case('replay','component_join_and_split')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True)),put('EVIDENCE','b',ev(['y'],1,protected=True))],['x','y'])
        s.publish([put('EVIDENCE','bridge',ev(['x','y'],0,protected=True))]);assert s.check()['status']=='UNSAT'
        s.publish([retract('B2',1)]);assert s.check()['status']=='SAT'
    @case('replay','bom_blank_lines_and_nonconsecutive_seq')
    def _(s):
        events=[dict(put('OBSERVATION','o',obs()),seq=2),dict(put('EVIDENCE','a',ev(['x'],1,protected=True)),seq=19)]
        raw=b'\xef\xbb\xbf\n \t\n'+wire(events[0])+b'\n\n'+wire(events[1])+b'\n';s.publish(events,['x'],raw);s.check()
    @case('replay','replacement_changes_source_weight_and_protection')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,'A',3)),put('EVIDENCE','b',ev(['x'],1,'B',2))],['x']);s.publish([put('EVIDENCE','a',ev(['x'],0,'C',protected=True)),put('QUOTA','B',dict(max_drops=0))]);assert s.check()['status']=='UNSAT'
    @case('replay','same_logical_model_new_raw_provenance')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],1,'S',2))],['x','y']);old=json.loads((s.folder()/'manifest.json').read_bytes())
        s.publish([put('EVIDENCE','a',ev(['x','y','y'],1,'S',2))]);s.check();new=json.loads((s.folder()/'manifest.json').read_bytes())
        assert new['provenance_id']!=old['provenance_id'] and new['model_id']==old['model_id']

    math_cases=[
        ('zero_cost_phase',[put('EVIDENCE','a',ev(['x'],1,protected=True))],['x']),
        ('positive_weight_choice',[put('EVIDENCE','a',ev(['x'],0,cost=7)),put('EVIDENCE','b',ev(['x'],1,cost=3))],['x']),
        ('nonlinear_forbidden',[put('EVIDENCE','a',forbidden(['x','y'],[0,0],protected=True)),put('EVIDENCE','b',ev(['x'],0,cost=2)),put('EVIDENCE','c',ev(['y'],0,cost=4))],['x','y']),
        ('shared_source_limits_join_components',[put('EVIDENCE','a',ev(['x'],0,'A',1)),put('EVIDENCE','b',ev(['x'],1,'B',4)),put('EVIDENCE','c',ev(['y'],0,'A',1)),put('EVIDENCE','d',ev(['y'],1,'C',4)),put('QUOTA','A',dict(max_drops=1))],['x','y']),
        ('duplicate_condition_quota_multiplicity',[put('EVIDENCE','a',ev(['x'],0,'A',1)),put('EVIDENCE','b',ev(['x'],0,'A',2)),put('EVIDENCE','c',ev(['x'],1,protected=True)),put('QUOTA','A',dict(max_drops=1))],['x']),
        ('duplicate_cost_across_sources',[put('EVIDENCE','a',ev(['x'],0,'A',3)),put('EVIDENCE','b',ev(['x'],0,'B',3)),put('EVIDENCE','c',ev(['x'],1,'C',5))],['x']),
        ('protected_xor_cycle_unsat',[put('EVIDENCE','a',ev(['x','y'],0,protected=True)),put('EVIDENCE','b',ev(['y','z'],0,protected=True)),put('EVIDENCE','c',ev(['z','x'],1,protected=True))],['x','y','z']),
        ('empty_equations_and_cancellation',[put('EVIDENCE','a',ev(['x','x'],0,protected=True)),put('EVIDENCE','b',ev([],1,cost=3)),put('EVIDENCE','c',forbidden(['x','x'],[0,1],protected=True))],['x']),
        ('empty_forbid_is_impossible',[put('EVIDENCE','a',forbidden([],[],protected=True))],[]),
        ('large_integer_weights_no_float',[put('EVIDENCE','a',ev(['x'],0,cost=2**61+1)),put('EVIDENCE','b',ev(['x'],1,cost=2**61))],['x']),
        ('equal_cost_multiple_points',[put('EVIDENCE','a',ev(['x'],0,cost=3)),put('EVIDENCE','b',ev(['x'],1,cost=3))],['x','y']),
    ]
    for name,events,vs in math_cases:
        @case('math',name)
        def _(s,events=events,vs=vs):s.publish(events,vs);s.check(False)
    @case('math','coupled_random_exact_enumeration')
    def _(s):
        rng=random.Random(330120);vs=['v'+str(i) for i in range(10)];events=[]
        for i in range(60):
            subset=rng.sample(vs,rng.randint(1,5));source='S'+str(i%4)
            record=ev(subset,rng.randrange(2),source,rng.randint(1,20)) if i%2 else forbidden(subset,[rng.randrange(2) for v in subset],source,rng.randint(1,20))
            events.append(put('EVIDENCE','e'+str(i),record))
        events.extend(put('QUOTA','S'+str(i),dict(max_drops=7)) for i in range(4));s.publish(events,vs);s.check(False)

    for name,events in [('sat_lower_bound',[put('EVIDENCE','a',ev(['x'],1,protected=True))]),('repaired_lower_bound',[put('EVIDENCE','a',ev(['x'],0,cost=4)),put('EVIDENCE','b',ev(['x'],1,cost=3))]),('unsat_feasibility',[put('EVIDENCE','a',ev([],1,protected=True))])]:
        @case('proof',name)
        def _(s,events=events):s.publish(events,['x']);proof_check(s)
    @case('proof','wrong_threshold_rejected')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,cost=4)),put('EVIDENCE','b',ev(['x'],1,cost=3))],['x']);folder=s.folder();claim=json.loads((folder/'statement.json').read_bytes());claim['bound']-=1;(folder/'statement.json').write_bytes(wire(claim));rehash(s);rejected(s.verify(),5)
    @case('proof','same_cost_different_model_not_cache_key')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True)),put('EVIDENCE','b',ev(['x'],1,cost=2))],['x']);first=json.loads((s.folder()/'manifest.json').read_bytes())['statement_id']
        s.publish([put('EVIDENCE','a',ev(['x'],1,protected=True)),put('EVIDENCE','b',ev(['x'],0,cost=2))]);s.check();proof_check(s);assert json.loads((s.folder()/'manifest.json').read_bytes())['statement_id']!=first
    @case('proof','proof_bound_to_original_input')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True))],['x']);folder=s.folder();facts=rows(folder/'facts.jsonl');facts[0]['record']['bit']=1;(folder/'facts.jsonl').write_bytes(b''.join(wire(f)+b'\n' for f in facts));rehash(s);rejected(s.verify(),5)
    @case('proof','counterfeit_empty_proof_rejected')
    def _(s):
        events=[put('EVIDENCE','f'+str(i),forbidden(['x','y'],list(bits),protected=True)) for i,bits in enumerate(itertools.product((0,1),repeat=2))]
        s.publish(events,['x','y']);(s.folder()/'certificate.drat').write_bytes(b'');rehash(s);rejected(s.verify(),5)
    @case('proof','quota_update_invalidates_declaration')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,'A',2)),put('EVIDENCE','b',ev(['x'],1,'B',3))],['x']);s.publish([put('QUOTA','A',dict(max_drops=0))]);s.check();proof_check(s)

    @case('publish','phase_projection_matches_assignment')
    def _(s):s.publish([put('EVIDENCE','a',ev(['x'],1,protected=True)),put('OBSERVATION','o',obs())],['x']);s.check();assert good(s.query('calls','CURRENT','o'))['gt']=='1|0'
    @case('publish','unsat_never_falls_back_to_old_calls')
    def _(s):
        s.publish([put('OBSERVATION','o',obs())],['x']);s.publish([put('EVIDENCE','a',ev([],1,protected=True))]);s.check();assert s.query('calls')['stdout']==b'';assert good(s.query())['status']=='UNSAT'
    @case('publish','source_observation_remains_original')
    def _(s):s.publish([put('OBSERVATION','o',obs()),put('EVIDENCE','a',ev(['x'],1,protected=True))],['x']);s.check();assert [f for f in rows(s.folder()/'facts.jsonl') if f['kind']=='OBSERVATION'][0]['record']['gt']=='0|1'
    @case('publish','fixed_old_generation_survives_new_commit')
    def _(s):
        s.publish([put('OBSERVATION','o',obs())],['x']);old=s.base;before=s.query('calls',old)['stdout'];s.publish([put('EVIDENCE','a',ev(['x'],1,protected=True))]);assert s.query('calls',old)['stdout']==before;s.check()
    @case('publish','query_id_and_multisource_audit')
    def _(s):
        s.publish([put('OBSERVATION','o2',obs('x','B',9)),put('OBSERVATION','o1',obs('x','A',2)),put('QUOTA','A',dict(max_drops=0))],['x']);s.check();assert good(s.query('facts','CURRENT','o1'))['record']['position']==2;assert good(s.query('calls','CURRENT','o2'))['position']==9
    @case('publish','self_consistent_digest_wrong_projection_rejected')
    def _(s):
        s.publish([put('OBSERVATION','o',obs()),put('EVIDENCE','a',ev(['x'],1,protected=True))],['x']);call=rows(s.folder()/'calls.jsonl')[0];call['gt']='0|1';(s.folder()/'calls.jsonl').write_bytes(wire(call)+b'\n');rehash(s);rejected(s.verify(),5);rejected(s.query('calls'),5)

    @case('recovery','four_writers_actual_commit_cas')
    def _(s):
        entries=[]
        for i in range(4):
            manifest,batch=s.batch([put('EVIDENCE','a',ev(['x'],i%2))],['x']);ticket='W'+str(i);good(s.prepare(manifest,ticket));entries.append(ticket)
        jobs=[r.start(['commit','--store',s.store,'--ticket',ticket,'--expect','NONE']) for ticket in entries];values=[r.finish(job) for job in jobs]
        assert sum(v['returncode']==0 for v in values)==1
        for v in values:
            if v['returncode']!=0:rejected(v,7)
    @case('recovery','two_prepared_gates_do_not_lock_each_other')
    def _(s):
        jobs=[]
        for i in range(2):
            manifest,batch=s.batch([put('EVIDENCE','a',ev(['x'],i))],['x']);gate=r.directory(s.name+'/gate'+str(i));job=r.start(['prepare','--manifest',manifest,'--store',s.store,'--base','NONE','--ticket','G'+str(i),'--gate',gate]);jobs.append((job,gate,manifest))
        try:
            for job,gate,manifest in jobs:assert r.ready(job,gate/'ready')['stage']=='PREPARED'
            r.kill(jobs[0][0]);r.file(s.name+'/gate1/go',b'go');good(r.finish(jobs[1][0]));good(s.commit('G1'))
            Path(json.loads(jobs[0][2].read_bytes())['source']['path']).unlink();good(r.call(['resume','--manifest',jobs[0][2],'--store',s.store,'--ticket','G0']));rejected(s.commit('G0'),7)
        finally:
            for job,gate,manifest in jobs:
                if 'result' not in job:r.kill(job)
    def checkpoint_case(s,bom,fifo):
        events=[dict(put('OBSERVATION','o',obs()),seq=1)];raw=(b'\xef\xbb\xbf' if bom else b'')+wire(events[0])+b'\n';manifest,batch=s.batch(events,['x'],raw)
        value=json.loads(manifest.read_bytes());n=1 if bom else 37;gate=r.directory(s.name+'/checkpoint');source=Path(value['source']['path'])
        writer=None
        if fifo:
            source.unlink();os.mkfifo(source);r.own(source)
            writer=subprocess.Popen([sys.executable,'-c','import sys;open(sys.argv[1],"wb",buffering=0).write(bytes.fromhex(sys.argv[2]))',str(source),raw.hex()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        job=r.start(['prepare','--manifest',manifest,'--store',s.store,'--base','NONE','--ticket','CUT','--checkpoint-bytes',n,'--checkpoint-gate',gate])
        try:
            ready=r.ready(job,gate/'ready');assert ready and ready['bytes']==n and ready['sha256']==hashlib.sha256(raw[:n]).hexdigest();r.kill(job)
            if writer:writer.wait(timeout=3)
            suffix=r.file(s.name+'/suffix',raw[n:]);value['source']['path']=str(suffix);r.file(s.name+'/resume.json',wire(value))
            good(r.call(['resume','--manifest',s.root/'resume.json','--store',s.store,'--ticket','CUT']));receipt=good(s.commit('CUT'));s.base=receipt['generation'];s.history=[batch];s.check()
        finally:
            if 'result' not in job:r.kill(job)
            if writer and writer.poll() is None:writer.kill();writer.wait()
    @case('recovery','checkpoint_inside_json_line')
    def _(s):checkpoint_case(s,False,False)
    @case('recovery','fifo_once_and_checkpoint_inside_utf8_bom')
    def _(s):checkpoint_case(s,True,True)
    @case('recovery','captured_source_disappears_resume_does_not_reopen')
    def _(s):
        manifest,batch=s.batch([put('OBSERVATION','o',obs())],['x']);good(s.prepare(manifest,'CAP'));Path(json.loads(manifest.read_bytes())['source']['path']).unlink();good(r.call(['resume','--manifest',manifest,'--store',s.store,'--ticket','CAP']));receipt=good(s.commit('CAP'));s.base=receipt['generation'];s.history=[batch];s.check()
    @case('recovery','kill_after_proof_prepared_then_resume')
    def _(s):
        manifest,batch=s.batch([put('EVIDENCE','a',ev(['x'],1,protected=True)),put('OBSERVATION','o',obs())],['x']);gate=r.directory(s.name+'/proofgate');job=r.start(['prepare','--manifest',manifest,'--store',s.store,'--base','NONE','--ticket','P','--gate',gate])
        try:
            assert r.ready(job,gate/'ready')['stage']=='PREPARED';r.kill(job);Path(json.loads(manifest.read_bytes())['source']['path']).unlink();good(r.call(['resume','--manifest',manifest,'--store',s.store,'--ticket','P']));receipt=good(s.commit('P'));s.base=receipt['generation'];s.history=[batch];s.check();proof_check(s)
        finally:
            if 'result' not in job:r.kill(job)
    @case('recovery','conflict_rebase_changes_model_and_statement')
    def _(s):
        s.publish([put('EVIDENCE','a',ev(['x'],0,protected=True))],['x']);old=s.base
        left,lb=s.batch([put('EVIDENCE','b',ev(['x'],1,'B',5))]);good(s.prepare(left,'L'));right,rb=s.batch([put('QUOTA','B',dict(max_drops=0))]);good(s.prepare(right,'R'));receipt=good(s.commit('R'));s.base=receipt['generation'];s.history.append(rb)
        rejected(s.commit('L',old),7);Path(json.loads(left.read_bytes())['source']['path']).unlink();good(r.call(['rebase','--store',s.store,'--ticket','L','--base',s.base]));receipt=good(s.commit('L'));s.base=receipt['generation'];s.history.append(lb);assert s.check()['status']=='UNSAT';proof_check(s)
    @case('recovery','kernel_write_failure_preserves_current')
    def _(s):
        s.publish([put('OBSERVATION','old',obs())],['x']);before=(s.store/'CURRENT').read_bytes();old_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.folder().iterdir()}
        events=[put('EVIDENCE','e'+str(i),ev(['x'],i%2,'S',1)) for i in range(1600)];manifest,batch=s.batch(events)
        # Kernel EFBIG, not an LD_PRELOAD assumption about implementation language.
        value=s.prepare(manifest,'IO',env=dict(PHASE_TEST_FILE_LIMIT='65536'));rejected(value,6);assert (s.store/'CURRENT').read_bytes()==before
        assert old_files=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.folder().iterdir()}
        # A fresh ticket using the same complete source can still prepare.
        good(s.prepare(manifest,'RETRY'));receipt=good(s.commit('RETRY'));s.base=receipt['generation'];s.history.append(batch);s.check()

    @case('resource','long_history_bounded_replay')
    def _(s):
        n=640000*resource_size;path=s.root/'long.jsonl'
        with path.open('wb') as f:
            for i in range(n):f.write(wire(dict(put('EVIDENCE','e'+str(i%97),ev(['x'],i%2)),seq=i+1))+b'\n')
        raw=path.read_bytes();manifest,batch=s.batch([],['x'],raw);result=s.prepare(manifest,'LONG');good(result);assert result['peak_rss_kib']<=512*1024;receipt=good(s.commit('LONG'));s.base=receipt['generation'];assert len(rows(s.folder()/'facts.jsonl'))==97
    @case('resource','many_active_records_same_condition')
    def _(s):
        n=30000*resource_size;events=(dict(put('EVIDENCE','e'+str(i),ev(['x'],0,'S',1)),seq=i+1) for i in range(n));raw=b''.join(wire(e)+b'\n' for e in events);manifest,batch=s.batch([],['x'],raw);result=s.prepare(manifest,'DENSE');good(result);assert result['peak_rss_kib']<=512*1024;receipt=good(s.commit('DENSE'));s.base=receipt['generation'];assert len(rows(s.folder()/'facts.jsonl'))==n;assert s.value()['cost']==0
    @case('resource','compression_retains_source_count_vector')
    def _(s):
        events=[put('EVIDENCE','e'+str(i),ev(['x'],0,'S'+str(i%8),1+i%3)) for i in range(2048)];events.append(put('EVIDENCE','anchor',ev(['x'],1,protected=True)));events.append(put('QUOTA','S0',dict(max_drops=255)));s.publish(events,['x']);assert s.check(False)['status']=='UNSAT';assert len(json.loads((s.folder()/'model.json').read_bytes())['groups'])==2
    @case('resource','maximum_variable_domain_and_no_residual_workers')
    def _(s):
        vs=['v'+str(i) for i in range(128)];events=[put('EVIDENCE','a'+str(i),ev([v],i%2,protected=True)) for i,v in enumerate(vs)];manifest,batch=s.batch(events,vs);result=s.prepare(manifest,'VARS');good(result);assert result['peak_rss_kib']<=512*1024 and not result['residual_processes'];receipt=good(s.commit('VARS'));s.base=receipt['generation'];s.history=[batch];s.check(False,(0,None));proof_check(s)

    for variant in range(4):
        @case('legacy','legacy_export_after_new_store_'+str(variant))
        def _(s,variant=variant):
            s.publish([put('OBSERVATION','o',obs())],['x']);s.check()
            vs=['a','b','c','d'];relations=[dict(a='a',b='b',bit=variant%2),dict(a='b',b='c',bit=1)] if variant!=3 else []
            observations=[dict(obs('b'),id='o'),dict(obs('c',position=2,gt='.|.'),id='missing')]
            obj=dict(version=1,variables=vs[::-1] if variant==2 else vs,relations=relations,observations=observations);path=r.file(s.name+'/legacy.json',wire(obj));value=good(r.call(['legacy-export','--input',path]))
            point=dict(a=0,b=variant%2 if relations else 0,c=(variant%2)^1 if relations else 0,d=0)
            calls=[dict(o,gt=o['gt'][::-1] if point[o['block']] else o['gt']) for o in observations];calls.sort(key=lambda v:(v['chrom'],v['position'],v['sample'],v['id']));assert value==dict(assignment=point,calls=calls)
    assert len(scenarios)==50,{g:sum(x[0]==g for x in scenarios) for g in WEIGHTS}
    return scenarios

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--results',required=True);parser.add_argument('--only');parser.add_argument('--resource-size',type=int,default=1);args=parser.parse_args();r=Runner(args.project,args.results)
    for group,name,fn in suite(r,args.resource_size):
        if args.only and args.only not in (group,name):continue
        begin=time.monotonic();passed=True;error=None
        try:fn(Scenario(r,name))
        except Exception as e:passed=False;error=repr(e)
        finally:r.close()
        record=dict(group=group,name=name,passed=passed,evidence=error,seconds=round(time.monotonic()-begin,3));r.records.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    if args.only:
        (Path(args.results)/'partial.json').write_text(json.dumps(r.records,indent=2));return
    r.save(WEIGHTS)

if __name__=='__main__':main()
