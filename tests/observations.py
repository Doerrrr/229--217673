"""Output-only finite release checker; no source parser or aggregation solver."""
from functools import lru_cache
import re

GT=re.compile(r'(?:\.|[0-9]+)(?:[|/](?:\.|[0-9]+))*\Z',re.ASCII)
TAGS={'GT','AD','PL','DP','GQ','PS'}


@lru_cache(maxsize=64)
def genotype_order(ploidy,allele_count):
    if type(ploidy) is not int or not 1<=ploidy<=4:
        raise ValueError('outside draft ploidy support')
    if type(allele_count) is not int or not 1<=allele_count<=17:
        raise ValueError('outside draft allele-count support')
    if ploidy==1:return tuple((a,) for a in range(allele_count))
    return tuple(prefix+(last,) for last in range(allele_count)
                 for prefix in genotype_order(ploidy-1,last+1))


def integer_or_missing(value):
    if value is None:return None
    if type(value) is not int:raise ValueError('integer or null required')
    return value


def genotype(value,alleles):
    if not isinstance(value,str) or not GT.fullmatch(value):raise ValueError('invalid genotype')
    pieces=re.split(r'[/|]',value);separators=tuple(re.findall(r'[/|]',value))
    if not 1<=len(pieces)<=4:raise ValueError('unsupported genotype ploidy')
    resolved=[]
    for piece in pieces:
        if piece=='.':resolved.append(None)
        else:
            n=int(piece)
            if n>=len(alleles):raise ValueError('allele index out of range')
            resolved.append(alleles[n])
    if '|' not in separators:resolved.sort(key=lambda a:(a is not None,a or ''))
    return tuple(resolved),separators


def vector(value,count):
    if value is None:return None
    if not isinstance(value,list) or len(value)!=count:raise ValueError('vector cardinality')
    data=tuple(integer_or_missing(v) for v in value)
    return None if all(v is None for v in data) else data


def observation(value,alleles):
    if not isinstance(value,dict):raise ValueError('observation must be an object')
    source,ordinal=value['source'],value['ordinal']
    if not isinstance(source,str) or not source or type(ordinal) is not int or ordinal<0:
        raise ValueError('invalid origin')
    tags=value['format'];fields=value['values']
    if not isinstance(tags,list) or not tags or any(not isinstance(t,str) or t not in TAGS for t in tags):
        raise ValueError('invalid FORMAT')
    if len(set(tags))!=len(tags) or not isinstance(fields,dict) or set(tags)!=set(fields):
        raise ValueError('FORMAT and values disagree')
    if 'GT' not in fields:raise ValueError('draft observations require GT')
    gt=genotype(fields['GT'],alleles)
    mapped=[]
    for tag in sorted(tags):
        data=fields[tag]
        if tag=='GT':data=gt
        elif tag=='AD':
            values=vector(data,len(alleles))
            data=None if values is None else tuple(sorted(zip(alleles,values)))
        elif tag=='PL':
            order=genotype_order(len(gt[0]),len(alleles));values=vector(data,len(order))
            data=None if values is None else tuple(sorted((tuple(sorted(alleles[i] for i in combination)),number)
                                                          for combination,number in zip(order,values)))
        else:data=integer_or_missing(data)
        mapped.append((tag,data))
    return source,ordinal,tuple(mapped)


def normalize_row(row):
    if not isinstance(row,dict):raise ValueError('release row must be an object')
    chrom,pos,ref=row['chrom'],row['position'],row['reference'];alt=row['alternate']
    if not isinstance(chrom,str) or not chrom or type(pos) is not int or pos<1 or not isinstance(ref,str) or not ref:
        raise ValueError('invalid coordinate')
    if not isinstance(alt,list) or any(not isinstance(a,str) or not a for a in alt):raise ValueError('invalid ALT')
    alleles=(ref,*alt)
    if len(set(alleles))!=len(alleles):raise ValueError('duplicate allele identity')
    contributors=row['contributors']
    if not isinstance(contributors,list) or not contributors:raise ValueError('missing source contributions')
    origins=[]
    for item in contributors:
        if not isinstance(item,dict) or not isinstance(item['source'],str) or not item['source']:
            raise ValueError('invalid contributor')
        if type(item['ordinal']) is not int or item['ordinal']<0:raise ValueError('invalid ordinal')
        origins.append((item['source'],item['ordinal']))
    if len(set(origins))!=len(origins):raise ValueError('duplicate source-record identity')
    samples=row['samples']
    if not isinstance(samples,list):raise ValueError('samples must be a list')
    normalized=[];names=set()
    for sample in samples:
        name=sample['name']
        if not isinstance(name,str) or not name or name in names:raise ValueError('invalid sample identity')
        names.add(name)
        winner=None if sample['winner'] is None else observation(sample['winner'],alleles)
        others=tuple(sorted(observation(other,alleles) for other in sample['others']))
        all_observed=([winner] if winner is not None else [])+list(others)
        observed_origins=[(o[0],o[1]) for o in all_observed]
        if len(set(observed_origins))!=len(observed_origins) or any(origin not in origins for origin in observed_origins):
            raise ValueError('observation origin not a distinct contributing record')
        normalized.append((name,winner,others))
    return (chrom,pos,ref,tuple(sorted(alt)),tuple(sorted(origins)),tuple(normalized))


def equivalent(actual,expected):
    wanted=[normalize_row(row) for row in expected]
    try:
        if not isinstance(actual,list):return False
        got=[normalize_row(row) for row in actual]
        keys=[row[:3] for row in got]
        if len(set(keys))!=len(keys):return False
        return got==wanted
    except (ValueError,KeyError,TypeError,IndexError):return False
