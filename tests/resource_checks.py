"""Bounded-memory verifier for finite resource shapes, not a publication oracle."""
import hashlib
import json
from pathlib import Path
import re

from resource_cases import expected_fields
from snapshot_checks import bounded_shape, current, decode, input_id

LIMIT_KIB=196608
ALTS=('C','G','T','AA','AC','AG','AT','ACC','ACG','ACT','AGC','AGG','AGT','ATC','ATG','ATT')

def spec(kind):
    assert kind in ('long400','long800','wide')
    wide=kind=='wide';n=2 if wide else 400000 if kind=='long400' else 800000
    return {'kind':kind,'wide':wide,'n':n,'alts':ALTS if wide else ALTS[:4],
        'names':tuple(f'S{i:02d}' for i in range(64)) if wide else ('S',),
        'sources':tuple(f'source{i:02d}' for i in range(16)) if wide else ('primary',),
        'values':{'GT':'0|1|2|16' if wide else '0|1|2|4',
                  'AD':list(range(1,18)) if wide else [1,128,40000,60000,2147483000],
                  'PL':list(range(2147470000,2147474845)) if wide else list(range(100000,100070)),
                  'DP':40000 if wide else 200000,'GQ':99,'PS':123456}}

def source_input(root,s):
    sources=[]
    for i,name in enumerate(s['sources']):
        h=hashlib.sha256()
        with (root/f'source{i:02d}.vcf').open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        sources.append({'source':name,'sha256':h.hexdigest()})
    return {'sources':sources,'samples':list(s['names'])}

def fields_equal(actual,wanted):
    assert isinstance(actual,dict) and set(actual)==set(wanted)
    for key,want in wanted.items():
        got=actual[key]
        if key=='GT':
            assert isinstance(got,str)
            assert re.sub(r'\d+',lambda m:str(int(m[0])),got)==want
        elif isinstance(want,list):
            assert isinstance(got,list) and all(type(v) is int for v in got)
            assert got==want
        else:assert type(got) is int and got==want

def valid_observation(value,origin,fields):
    assert type(value['ordinal']) is int
    assert (value['source'],value['ordinal'])==origin
    assert len(value['format'])==len(fields) and set(value['format'])==set(fields)
    fields_equal(value['values'],fields)

def inspect_files(root,s):
    """Keep one JSON line at a time; never retain both large views together."""
    hashes={};counts={};sizes={};cache={}
    old=('A',*s['alts']);n=s['n'];wide=s['wide']
    for filename in ('release.jsonl','original.jsonl'):
        path=root/filename
        assert path.is_file() and not path.is_symlink()
        h=hashlib.sha256();count=0
        with path.open('rb') as f:
            for count,raw in enumerate(f,1):
                h.update(raw);row=json.loads(raw)
                assert row['chrom']=='chr7' and row['reference']=='A' and type(row['position']) is int
                if filename=='release.jsonl':
                    assert row['position']==(31 if wide else count)
                    actual=('A',*row['alternate'])
                    assert len(actual)==len(old) and set(actual)==set(old)
                    if actual not in cache:cache[actual]=expected_fields(s['values'],old,actual)
                    fields=cache[actual]
                    origins=[(name,j) for name in s['sources'] for j in range(n)] if wide else [('primary',n-count)]
                    assert len(row['contributors'])==len(origins)
                    assert sorted((v['source'],v['ordinal']) for v in row['contributors'])==sorted(origins)
                    assert [v['name'] for v in row['samples']]==list(s['names'])
                    for sample in row['samples']:
                        valid_observation(sample['winner'],origins[0],fields)
                        others={(v['source'],v['ordinal']):v for v in sample['others']}
                        assert len(others)==len(sample['others']) and set(others)==set(origins[1:])
                        for origin in origins[1:]:valid_observation(others[origin],origin,fields)
                else:
                    rank,ordinal=divmod(count-1,n)
                    assert rank<len(s['sources']) and type(row['ordinal']) is int
                    assert (row['source'],row['ordinal'])==(s['sources'][rank],ordinal)
                    assert row['position']==(31 if wide else n-ordinal)
                    assert row['alternate']==list(s['alts'])
                    assert set(row['format'])==set(s['values']) and len(row['format'])==len(s['values'])
                    assert [v['name'] for v in row['samples']]==list(s['names'])
                    for sample in row['samples']:fields_equal(sample['values'],s['values'])
        wanted_count=(1 if wide else n) if filename=='release.jsonl' else len(s['sources'])*n
        assert count==wanted_count
        hashes[filename]=h.hexdigest();counts[filename]=count;sizes[filename]=path.stat().st_size
    return {'hashes':hashes,'rows':counts,'bytes':sizes}

def validate_generation(store,payload,s):
    generation=current(store);assert generation==input_id(payload)
    root=store/'generations'/generation
    assert root.is_dir() and not root.is_symlink()
    mpath=root/'manifest.json';assert mpath.is_file() and not mpath.is_symlink()
    meta=decode(mpath.read_bytes())
    assert meta['input']==payload and meta['generation']==generation
    assert set(meta['files'])=={'release.jsonl','original.jsonl'}
    data=inspect_files(root,s)
    for name in data['hashes']:
        assert meta['files'][name]['sha256']==data['hashes'][name]
        assert type(meta['files'][name]['rows']) is int and meta['files'][name]['rows']==data['rows'][name]
    return data

def measured_resource_cases(native,writer):
    """Author finite writer only generates public inputs, then discards outputs."""
    from evaluate_dual import writable,file_args
    cases=[];measurements={}
    for kind in ('long400','long800','wide'):
        s=spec(kind);root=native.root/('resource_'+kind);root.mkdir();root.chmod(0o755)
        # Only owned finite generated views are removed before candidate entry.
        import subprocess
        p=subprocess.run([str(writer),kind,str(root)],capture_output=True,timeout=180)
        assert p.returncode==0,'author finite fixture creation failed'
        for filename in ('release.jsonl','original.jsonl'):(root/filename).unlink()
        payload=source_input(root,s)
        manifest=root/'batches.tsv'
        manifest.write_text('source\tpath\n'+''.join(name+'\t'+str(root/f'source{i:02d}.vcf')+'\n' for i,name in enumerate(s['sources'])))
        manifest.chmod(0o444)
        for file in root.glob('*.vcf'):file.chmod(0o444)
        store=root/'store';writable(store)
        result=native.invoke('resource_'+kind,file_args(manifest,s['names'],store,'NONE'),seconds=180)
        passed=False;reason=''
        if result['returncode']==0 and result['stdout_bytes']==0 and not result['timed_out']:
            try:validate_generation(store,payload,s);passed=True
            except (AssertionError,ValueError,KeyError,TypeError,IndexError,OSError) as e:reason=str(e) or type(e).__name__
        else:reason=f"returncode={result['returncode']}"
        measurements[kind]=result
        cases.append({'name':kind,'passed':passed and result['peak_rss_kib']<=LIMIT_KIB,
                      'semantics_correct':passed,'reason':reason,**result})
    a,b=measurements['long400'],measurements['long800']
    cases.append({'name':'bounded_growth','passed':cases[0]['semantics_correct'] and cases[1]['semantics_correct']
                  and bounded_shape(a['peak_rss_kib'],b['peak_rss_kib']),
                  'first_rss_kib':a['peak_rss_kib'],'second_rss_kib':b['peak_rss_kib']})
    return cases
