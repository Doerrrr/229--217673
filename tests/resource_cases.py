"""Deterministic finite resource inputs; checks accept equivalent ALT order."""
import json
import re
from fixtures import Batch, Record, vcf_bytes, order

LIMIT_KIB=192*1024


def expected_fields(values,old,actual):
    fields=dict(values)
    p=len(re.split(r'[/|]',values['GT']))
    fields['GT']=re.sub(r'[0-9]+',lambda m:str(actual.index(old[int(m[0])])),values['GT'])
    lookup=dict(zip(old,values['AD']));fields['AD']=[lookup.get(a) for a in actual]
    lookup={tuple(sorted(old[i] for i in comb)):v for comb,v in zip(order(p,len(old)),values['PL'])}
    fields['PL']=[lookup.get(tuple(sorted(actual[i] for i in comb))) for comb in order(p,len(actual))]
    return fields


def validate_observation(observed,fields,origin):
    return (observed['source'],observed['ordinal'])==origin and set(observed['format'])==set(fields) and observed['values']==fields


def resource_checks(execute):
    output=[]
    for label,wide in (('long_source',False),('wide_locus',True)):
        directory=execute.root/label;directory.mkdir();directory.chmod(0o755)
        alts=('C','G','T','AA','AC','AG','AT','ACC','ACG','ACT','AGC','AGG','AGT','ATC','ATG','ATT') if wide else ('C','G','T','AA')
        values={'GT':'0|1|2|16' if wide else '0|1|2|4',
                'AD':list(range(1,18)) if wide else [1,128,40000,60000,2147483000],
                'PL':list(range(2147470000,2147474845)) if wide else list(range(100000,100070)),
                'DP':40000 if wide else 200000,'GQ':99,'PS':123456}
        names=tuple('S'+str(i).zfill(2) for i in range(64)) if wide else ('S',)
        record=Record('chr7',31,'A',alts,tuple(values),tuple((name,tuple(values.values())) for name in names))
        encoded=vcf_bytes(Batch('x',names,(record,)))
        header,body=encoded.rsplit(b'\n',2)[:2]
        # Header ends immediately before the final record; body has exactly the
        # nine fixed columns and generated observations, no hidden data file.
        rows=2 if wide else 400000;sources=16 if wide else 1
        paths=[]
        for i in range(sources):
            name='source'+str(i).zfill(2) if wide else 'primary'
            path=directory/(name+'.vcf')
            with path.open('xb') as file:
                file.write(header+b'\n')
                if wide:file.write((body+b'\n')*rows)
                else:
                    parts=body.split(b'\t');suffix=b'\t'.join(parts[2:])+b'\n'
                    for pos in range(rows,0,-1):file.write(b'chr7\t'+str(pos).encode()+b'\t'+suffix)
            path.chmod(0o444);paths.append((name,path))
        manifest=directory/'batches.tsv';manifest.write_text('source\tpath\n'+''.join(name+'\t'+str(path)+'\n' for name,path in paths));manifest.chmod(0o444)
        measured=execute.invoke(label,manifest,names,limit=180)
        semantics_ok=False
        if measured['returncode']==0 and not measured['timed_out']:
            try:
                old=('A',*alts);cache={};count=0
                with measured['stdout'].open('rb') as file:
                    for count,line in enumerate(file,1):
                        row=json.loads(line);actual=(row['reference'],*row['alternate'])
                        assert row['chrom']=='chr7' and row['position']==(31 if wide else count) and actual[0]=='A'
                        assert len(actual)==len(old) and set(actual)==set(old)
                        if actual not in cache:cache[actual]=expected_fields(values,old,actual)
                        fields=cache[actual]
                        origins=[(name,j) for name,_ in paths for j in range(rows)] if wide else [('primary',rows-count)]
                        assert sorted((v['source'],v['ordinal']) for v in row['contributors'])==sorted(origins)
                        assert [v['name'] for v in row['samples']]==list(names)
                        for sample in row['samples']:
                            assert validate_observation(sample['winner'],fields,origins[0])
                            others={(v['source'],v['ordinal']):v for v in sample['others']}
                            assert len(others)==len(sample['others']) and set(others)==set(origins[1:])
                            assert all(validate_observation(others[o],fields,o) for o in origins[1:])
                assert count==(1 if wide else rows)
                semantics_ok=True
            except (AssertionError,ValueError,KeyError,TypeError,IndexError):pass
        if measured['returncode']!=0:execute.abnormal.append({'case':label,'reason':'resource_valid_input_nonzero'})
        output.append({'name':label,'passed':semantics_ok and measured['peak_rss_kib']<=LIMIT_KIB,
                       'observations_correct':semantics_ok,'peak_rss_kib':measured['peak_rss_kib'],
                       'limit_kib':LIMIT_KIB,'returncode':measured['returncode'],'timed_out':measured['timed_out'],
                       'elapsed_seconds':measured['elapsed_seconds']})
    return output
