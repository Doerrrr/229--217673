"""Independent business families: fields, roles and grouping do not double-penalize."""
from observations import observation
from fixtures import source_facts


def semantics(value,alleles):
    source,ordinal,fields=observation(value,alleles)
    pruned=[]
    for tag,data in fields:
        if tag in ('AD','PL') and data is not None:
            data=tuple((key,value) for key,value in data if value is not None)
        pruned.append((tag,data))
    return source,ordinal,tuple(pruned)


def indexed(rows):
    if not isinstance(rows,list):raise ValueError('rows must be list')
    result={}
    for row in rows:
        key=(row['chrom'],row['position'],row['reference'])
        if key in result:raise ValueError('duplicate locus')
        result[key]=row
    return result


def projection(case,rows):
    wanted=source_facts(case);actual=indexed(rows)
    if set(actual)!=set(wanted):return False
    for key,facts in wanted.items():
        row=actual[key];alleles=(row['reference'],*row['alternate'])
        if len(alleles)!=len(set(alleles)) or set(row['alternate'])!=facts['alts']:return False
        samples={s['name']:s for s in row['samples']}
        for name,fact_values in facts['samples'].items():
            sample=samples[name]
            values=([sample['winner']] if sample['winner'] is not None else [])+sample['others']
            expected={ (v['source'],v['ordinal']):semantics(v,v['alleles']) for v in fact_values }
            got={}
            for value in values:
                origin=(value['source'],value['ordinal'])
                if origin in got:return False
                got[origin]=semantics(value,alleles)
            if got!=expected:return False
    return True


def priority(case,rows):
    wanted=source_facts(case);actual=indexed(rows)
    if set(actual)!=set(wanted):return False
    for key,facts in wanted.items():
        samples=actual[key]['samples']
        if [s['name'] for s in samples]!=list(case.selected):return False
        for sample in samples:
            observed=facts['samples'][sample['name']]
            origins=[(v['source'],v['ordinal']) for v in observed]
            winner=sample['winner']
            if not origins:
                if winner is not None or sample['others']!=[]:return False
                continue
            if winner is None or (winner['source'],winner['ordinal'])!=origins[0]:return False
            others=[(v['source'],v['ordinal']) for v in sample['others']]
            if sorted(others)!=sorted(origins[1:]):return False
    return True


def grouping(case,rows):
    wanted=source_facts(case)
    keys=[(r['chrom'],r['position'],r['reference']) for r in rows]
    if keys!=sorted(wanted):return False
    for row,key in zip(rows,keys):
        facts=wanted[key]
        if len(set(row['alternate']))!=len(row['alternate']) or set(row['alternate'])!=facts['alts']:return False
        got=[(v['source'],v['ordinal']) for v in row['contributors']]
        if sorted(got)!=sorted(facts['origins']):return False
    return True


CHECKS={'projection':projection,'priority':priority,'grouping':grouping}


def accepts(group,case,result):
    if result['returncode']!=0:
        return (group=='completion' and not case.success and result['returncode']>0
                and bool(result['stderr'].strip()) and result['stdout'].stat().st_size==0)
    if not case.success:return False
    try:
        if group=='completion':return grouping(case,result['rows']) and priority(case,result['rows'])
        return CHECKS[group](case,result['rows'])
    except (ValueError,KeyError,TypeError,IndexError):return False
