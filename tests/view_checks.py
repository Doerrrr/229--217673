"""Independent source-fact checks for both dictionaries; no release writer."""
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]/'cohort_unordered'
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
from business_checks import semantics, projection, priority, grouping
from fixtures import vcf_bytes
from snapshot_checks import sha

def expected_input(case):
    # Unit fixtures are uncompressed text. Runtime compressed files must hash
    # their actual bytes, not a decompressed or rewritten equivalent.
    return {'sources':[{'source':b.source,'sha256':sha(vcf_bytes(b))} for b in case.batches],
            'samples':list(case.selected)}

def original_view(case,rows):
    if not isinstance(rows,list):return False
    expected=[]
    for batch in case.batches:
        for ordinal,record in enumerate(batch.records):
            expected.append((batch.source,ordinal,record))
    if len(rows)!=len(expected):return False
    try:
        for got,(source,ordinal,record) in zip(rows,expected):
            if not isinstance(got,dict):return False
            if type(got['ordinal']) is not int or got['ordinal']!=ordinal or got['source']!=source:return False
            if (got['chrom'],got['position'],got['reference'])!=(record.chrom,record.pos,record.ref):return False
            if type(got['position']) is not int:return False
            if got['alternate']!=list(record.alt):return False
            if set(got['format'])!=set(record.tags) or len(got['format'])!=len(record.tags):return False
            values=dict(record.samples)
            names=[name for name in case.selected if name in values]
            if [sample['name'] for sample in got['samples']]!=names:return False
            for sample in got['samples']:
                actual={'source':source,'ordinal':ordinal,'format':got['format'],'values':sample['values']}
                wanted={'source':source,'ordinal':ordinal,'format':list(record.tags),
                        'values':dict(zip(record.tags,values[sample['name']]))}
                if semantics(actual,(got['reference'],*got['alternate']))!=semantics(wanted,(record.ref,*record.alt)):
                    return False
        return True
    except (KeyError,ValueError,IndexError,TypeError):return False

def both_views(case,snapshot):
    release=snapshot['rows']['release.jsonl'];original=snapshot['rows']['original.jsonl']
    try:
        return (projection(case,release) and priority(case,release) and grouping(case,release)
                and original_view(case,original))
    except (KeyError,ValueError,IndexError,TypeError):return False
