"""Frozen-ready business driver: process observations, not reference outputs.

Resources are supplied separately after positive calibration. This module never
solves an arbitrary input, and never accepts an answer's self-test as evidence.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from fixtures import CASES, Batch, Case, record, vcf_bytes
from business_checks import CHECKS, accepts
from hand_fixture import fixture
from snapshot_checks import current, input_id, load_current, load_generation, preserved, prepared_snapshots
from test_snapshot_checks import materialize, second_fixture
from view_checks import both_views


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def prepare(native, case, label):
    root = native.root / label
    root.mkdir(); root.chmod(0o755)
    paths, sources = [], []
    for i, batch in enumerate(case.batches):
        path = root / f'source{i}.vcf'
        if batch.fault != 'missing':
            raw = vcf_bytes(batch)
            if batch.fault == 'header': raw = b'not a VCF header\n'
            elif batch.fault == 'tail': raw += b'not a record\n'
            elif batch.fault == 'columns':
                raw = b'\n'.join(line.rsplit(b'\t',1)[0] if not line.startswith(b'#')
                    else line for line in raw.splitlines())+b'\n'
            path.write_bytes(raw); path.chmod(0o444)
            if batch.encoding in ('bcf', 'vcfgz'):
                converted = path.with_suffix('.bcf' if batch.encoding=='bcf' else '.vcf.gz')
                p = subprocess.run([native.codec, 'view', '-Ob' if batch.encoding=='bcf' else '-Oz',
                    '-o', str(converted), str(path)], capture_output=True, timeout=60)
                if p.returncode: raise RuntimeError('author codec failed: '+p.stderr.decode(errors='replace'))
                converted.chmod(0o444); path = converted
            sources.append({'source':batch.source, 'sha256':digest(path)})
        paths.append(path.name if case.relative else str(path))
    manifest = root/'batches.tsv'
    manifest.write_text('source\tpath\n'+''.join(b.source+'\t'+p+'\n' for b,p in zip(case.batches,paths)))
    manifest.chmod(0o444)
    payload = {'sources':sources, 'samples':list(case.selected)}
    return root, manifest, payload


def writable(path):
    path.mkdir(exist_ok=True)
    for file in (path, *path.rglob('*')):
        os.chown(file, 10001, 10001)
        file.chmod(0o755 if file.is_dir() else 0o644)


def seed(root):
    store = root/'store'; store.mkdir()
    case, release, original = fixture()
    generation, _ = materialize(store, case, release, original)
    (store/'CURRENT').write_text(generation+'\n')
    writable(store)
    return store, generation, load_current(store)


def file_args(manifest, selected, store, expect, gate=None):
    args = ['--manifest', str(manifest), '--samples', ','.join(selected),
            '--out-dir', str(store), '--expect', expect]
    if gate: args += ['--gate', str(gate)]
    return args


def success(result): return result['returncode']==0 and result['stdout_bytes']==0 and not result['timed_out']


def check(case, action):
    try:
        details = action()
        return {'name':case, 'passed':True, **(details or {})}
    except (AssertionError, ValueError, KeyError, IndexError, TypeError, OSError) as error:
        return {'name':case, 'passed':False, 'reason':str(error)[:1500] or type(error).__name__}


def legacy(native):
    cases=[]
    for family in ('projection','priority','grouping','completion'):
        for case in CASES[family]:
            def action(case=case, family=family):
                _,manifest,_ = prepare(native,case,'legacy_'+case.name)
                result = native.invoke('legacy_'+case.name,
                    ['--manifest',manifest,'--samples',','.join(case.selected)])
                rows = [json.loads(line) for line in Path(result['stdout_path']).read_bytes().splitlines()]
                if family=='completion':
                    verdict=accepts(family,case,{**result,'stdout':Path(result['stdout_path']),'rows':rows})
                else:verdict=result['returncode']==0 and CHECKS[family](case,rows)
                assert verdict, 'legacy business obligation differs'
                return {'returncode':result['returncode'],'family':family}
            outcome=check(case.name,action);outcome['family']=family;cases.append(outcome)
    return cases


def dual(native):
    cases=[]
    for case in [*CASES['projection'], *CASES['priority'], *CASES['grouping'], CASES['completion'][0]]:
        def action(case=case):
            root,manifest,payload = prepare(native,case,'dual_'+case.name)
            store=root/'store';writable(store)
            result=native.invoke('dual_'+case.name,file_args(manifest,case.selected,store,'NONE'))
            assert success(result), f"returncode={result['returncode']} stdout={result['stdout_bytes']}"
            snapshot=load_current(store,payload)
            assert both_views(case,snapshot),'original or projected view differs from source facts'
            return {'generation':snapshot['generation']}
        cases.append(check(case.name,action))
    return cases


def hand_variant(index):
    if index==1:return second_fixture()[0]
    case=second_fixture()[0]
    row=case.batches[0].records[0]
    row=replace(row,samples=(('S',('0|1',[13,20],[101,102,103])),))
    batch=replace(case.batches[0],records=(row,*case.batches[0].records[1:]))
    return replace(case,batches=(batch,*case.batches[1:]))


def schedules(native,reader):
    atomic=[];conflict=[]
    def run(label,action):
        result=check(label,action)
        native.cleanup()
        return result

    def prepared():
        case=hand_variant(1);root,manifest,payload=prepare(native,case,'prepared')
        store,old,before=seed(root);gate=root/'gate';writable(gate)
        call=native.start('prepared',file_args(manifest,case.selected,store,old,gate))
        ready=call.ready(gate)
        assert ready.get('generation')==input_id(payload) and ready.get('stage')=='PREPARED'
        assert preserved(before,load_current(store)), 'CURRENT changed before commit'
        assert any(both_views(case,snapshot) for snapshot in
                   prepared_snapshots(store,input_id(payload),payload)), 'prepared views incomplete or incorrect'
        (gate/'go').write_text('continue')
        assert success(native.finish(call))
        assert current(store)==input_id(payload)
        assert both_views(case,load_current(store,payload)), 'committed views differ from source facts'
        assert preserved(before,load_generation(store,old)), 'previous generation changed'
    atomic.append(run('prepared_is_complete_but_not_committed',prepared))

    def pinned():
        case=hand_variant(1);root,manifest,payload=prepare(native,case,'pinned')
        store,old,before=seed(root);gate=root/'reader_gate';writable(gate)
        call=native.start('pinned_reader',[str(reader),'--store',store,'--view','release','--pin',gate],
                          binary=sys.executable)
        assert call.ready(gate)['generation']==old
        assert success(native.invoke('pinned_publish',file_args(manifest,case.selected,store,old)))
        assert current(store)==input_id(payload)
        (gate/'go').write_text('continue');result=native.finish(call)
        assert result['returncode']==0
        assert Path(result['stdout_path']).read_bytes()==before['bytes']['release.jsonl']
        assert preserved(before,load_generation(store,old))
    atomic.append(run('reader_pins_old_generation_across_commit',pinned))

    def reuse():
        case,_,_=fixture();root,manifest,payload=prepare(native,case,'reuse')
        store,old,before=seed(root)
        assert old==input_id(payload)
        assert success(native.invoke('reuse',file_args(manifest,case.selected,store,old)))
        assert preserved(before,load_current(store)), 'same identity changed committed bytes'
    atomic.append(run('existing_generation_reuse_preserves_bytes',reuse))

    def race():
        a=hand_variant(1);root,manifest_a,payload_a=prepare(native,a,'race_a')
        b=hand_variant(2);_,manifest_b,payload_b=prepare(native,b,'race_b')
        store,old,before=seed(root)
        ga=root/'a_gate';gb=root/'b_gate';writable(ga);writable(gb)
        first=native.start('race_a',file_args(manifest_a,a.selected,store,old,ga))
        second=native.start('race_b',file_args(manifest_b,b.selected,store,old,gb))
        assert first.ready(ga)['generation']==input_id(payload_a)
        assert second.ready(gb)['generation']==input_id(payload_b)
        assert preserved(before,load_current(store))
        (ga/'go').write_text('continue');assert success(native.finish(first))
        committed=load_current(store,payload_a)
        (gb/'go').write_text('continue');result=native.finish(second)
        assert (result['returncode'],result['stdout_bytes'])==(7,0) and result['stderr'].strip()
        assert preserved(committed,load_current(store)), 'stale contender overwrote winner'
        assert preserved(before,load_generation(store,old))
    conflict.append(run('two_preparations_only_one_cas_winner',race))

    def kill_retry():
        case=hand_variant(1);root,manifest,payload=prepare(native,case,'kill')
        store,old,before=seed(root);gate=root/'gate';writable(gate)
        call=native.start('kill_prepared',file_args(manifest,case.selected,store,old,gate))
        assert call.ready(gate)['generation']==input_id(payload)
        assert preserved(before,load_current(store))
        call.kill_candidate();result=native.finish(call,controlled_kill=True)
        assert result['returncode']==-9 and not result['timed_out']
        assert preserved(before,load_current(store))
        assert success(native.invoke('kill_retry',file_args(manifest,case.selected,store,old)))
        assert both_views(case,load_current(store,payload))
        assert preserved(before,load_generation(store,old))
    conflict.append(run('prepared_kill_preserves_old_and_retry_works',kill_retry))

    def stale():
        case=hand_variant(1);root,manifest,_=prepare(native,case,'stale')
        store,_,before=seed(root)
        result=native.invoke('stale',file_args(manifest,case.selected,store,'NONE'))
        assert (result['returncode'],result['stdout_bytes'])==(7,0) and result['stderr'].strip()
        assert preserved(before,load_current(store))
    conflict.append(run('stale_expect_rejects_without_old_change',stale))
    return atomic,conflict


def failures(native):
    cases=[]
    for case in CASES['completion'][1:]:
        def action(case=case):
            root,manifest,_=prepare(native,case,'failure_'+case.name)
            store,old,before=seed(root)
            wanted=3 if case.name in ('missing_source_file','unreadable_header') else 5 if case.name=='unknown_selected_sample' else 4
            result=native.invoke('failure_'+case.name,file_args(manifest,case.selected,store,old))
            assert (result['returncode'],result['stdout_bytes'])==(wanted,0) and result['stderr'].strip(), f"expected={wanted} got={result['returncode']}"
            assert preserved(before,load_current(store)), 'old release changed on input failure'
        cases.append(check(case.name,action))
    for label in ('bad_expect','missing_expect','bad_manifest','readonly_store','file_size_error'):
        def action(label=label):
            case=hand_variant(1)
            if label=='file_size_error':
                case=Case(label,(Batch('first',('S',),tuple(record(pos=p) for p in range(1,129))),),('S',))
            root,manifest,_=prepare(native,case,'failure_'+label)
            store,old,before=seed(root);args=file_args(manifest,case.selected,store,old)
            wanted=2;limit=-1
            if label=='bad_expect':args[-1]='BAD'
            elif label=='missing_expect':args=args[:-2]
            elif label=='bad_manifest':
                manifest.chmod(0o644);manifest.write_text('wrong\tpath\n');manifest.chmod(0o444)
            elif label=='readonly_store':
                # Entire existing output hierarchy is read-only for UID10001.
                for f in (store,*store.rglob('*')):f.chmod(0o555 if f.is_dir() else 0o444)
                wanted=6
            else:limit=16384;wanted=6
            result=native.invoke('failure_'+label,args,size_limit=limit)
            assert (result['returncode'],result['stdout_bytes'])==(wanted,0) and result['stderr'].strip(), f"expected={wanted} got={result['returncode']}"
            assert preserved(before,load_current(store)), 'old release changed on failure'
            if label=='readonly_store':writable(store)
            # The failed attempt must not corrupt the next ordinary publication.
            retry_case=hand_variant(1)
            _,retry_manifest,payload=prepare(native,retry_case,'retry_'+label)
            assert success(native.invoke('retry_'+label,file_args(retry_manifest,retry_case.selected,store,old)))
            assert both_views(retry_case,load_current(store,payload))
            assert preserved(before,load_generation(store,old))
        cases.append(check(label,action))
    return cases


def summarize(native,groups,start):
    earned=0
    for group in groups:
        cases=group['cases'];group['passed']=sum(c['passed'] for c in cases);group['total']=len(cases)
        if group['name']=='legacy':
            ratios=[]
            for family,w in [('projection',.14),('priority',.07),('grouping',.06),('completion',.03)]:
                subset=[c for c in cases if c['family']==family]
                ratios.append(w*sum(c['passed'] for c in subset)/len(subset))
            group['earned']=sum(ratios)
        else:group['earned']=group['weight']*group['passed']/len(cases)
        earned+=group['earned']
    return {'task_id':'DDI-019','version':'v02-DRAFT','groups':groups,
            'execution_status':'ANSWER_RUNTIME_FAILURE' if native.abnormal else 'NORMAL',
            'reward':None if native.abnormal else round(earned,6),
            'provisional_behavior_score':round(earned,6),'abnormal':native.abnormal,
            'calls':native.calls,'model_calls':0,'formal_platform_t1':False,
            'elapsed_seconds':round(time.monotonic()-start,3)}


def evaluate(native,reader,resource_checks):
    start=time.monotonic()
    groups=[{'name':'legacy','weight':.30,'cases':legacy(native)},
            {'name':'dual_views','weight':.20,'cases':dual(native)}]
    atomic,conflict=schedules(native,reader)
    groups += [{'name':'atomicity_and_pinned_readers','weight':.20,'cases':atomic},
               {'name':'conflicts_and_recovery','weight':.15,'cases':conflict},
               {'name':'failure_paths','weight':.10,'cases':failures(native)},
               {'name':'resources','weight':.05,'cases':resource_checks(native)}]
    return summarize(native,groups,start)
