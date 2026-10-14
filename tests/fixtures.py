"""Finite source facts generated at author time; no repaired release implementation."""
from dataclasses import dataclass, replace
from itertools import combinations_with_replacement


@dataclass(frozen=True)
class Record:
    chrom: str
    pos: int
    ref: str
    alt: tuple
    tags: tuple
    samples: tuple  # (name, tuple of source-domain field values)


@dataclass(frozen=True)
class Batch:
    source: str
    names: tuple
    records: tuple
    contigs: tuple = ('chr7',)
    encoding: str = 'vcf'
    fault: str = ''


@dataclass(frozen=True)
class Case:
    name: str
    batches: tuple
    selected: tuple
    success: bool = True
    relative: bool = False


def order(ploidy, count):
    # Separate enumeration from the recursive output checker, tested against
    # manually labelled triploid/tetraploid cases in test_observations.py.
    return sorted(combinations_with_replacement(range(count), ploidy), key=lambda x: x[::-1])


def record(alt=('G',), p=2, seed=10, names=('S',), pos=31, chrom='chr7', missing=False,
           tags=('GT', 'AD', 'PL', 'DP', 'GQ', 'PS')):
    values=[]
    for index, name in enumerate(names):
        base=seed+index*100
        gt='/'.join(['.']*p) if missing else '|'.join(str(i % (1+len(alt))) for i in range(p))
        fields={'GT':gt, 'AD':[base+i for i in range(1+len(alt))],
                'PL':[base*10+i for i in range(len(order(p, 1+len(alt))))],
                'DP':base+1000, 'GQ':base % 90, 'PS':base+3000}
        values.append((name, tuple(fields[tag] for tag in tags)))
    return Record(chrom, pos, 'A', tuple(alt), tuple(tags), tuple(values))


def wire(value):
    if value is None: return '.'
    if isinstance(value, list): return ','.join('.' if v is None else str(v) for v in value)
    return str(value)


def vcf_bytes(batch):
    header=['##fileformat=VCFv4.3']
    header += ['##contig=<ID='+name+',length=2000000>' for name in batch.contigs]
    for tag, number, kind in [('GT','1','String'),('AD','R','Integer'),('PL','G','Integer'),
                              ('DP','1','Integer'),('GQ','1','Integer'),('PS','1','Integer')]:
        header.append(f'##FORMAT=<ID={tag},Number={number},Type={kind},Description="{tag}">')
    header.append('#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t'+'\t'.join(batch.names))
    lines=[]
    for row in batch.records:
        samples=dict(row.samples)
        lines.append('\t'.join([row.chrom,str(row.pos),'.',row.ref,','.join(row.alt) or '.',
                               '.','PASS','.',':'.join(row.tags),
                               *[':'.join(wire(v) for v in samples[name]) for name in batch.names]]))
    return ('\n'.join(header+lines)+'\n').encode()


def pair(name, a, b, names=('S',), encoding='vcf'):
    return Case(name,(Batch('first',tuple(n for n,_ in a.samples),(a,)),
                      Batch('second',tuple(n for n,_ in b.samples),(b,),encoding=encoding)),names)


projection=[]
for p in range(1,5):
    projection.append(pair('growth_'+str(p),record(('G',),p,10),record(('C',),p,20),encoding='bcf' if p % 2 else 'vcfgz'))
    projection.append(pair('permutation_'+str(p),record(('C','G'),p,30),record(('G','C'),p,40),encoding='bcf'))
projection.append(pair('missing_gt_has_evidence',record(('G',),4,50,missing=True),record(('C',),4,60)))
null_record=record(('G',),3,70)
null_record=replace(null_record,samples=(('S',('./.|.',[None,17],None,None,0,None)),))
projection.append(pair('partial_missing_values',null_record,record(('C',),3,80)))
projection.append(pair('field_order_is_local',record(('G',),2,90,tags=('GT','DP','AD','PS','PL','GQ')),
                       record(('C',),2,100,tags=('GT','PL','GQ','AD'))))
projection.append(pair('only_gt_and_depth',record(('G',),1,110,tags=('GT','DP')),
                       record(('C',),1,120,tags=('GT','AD','PL'))))

priority=[pair('source_priority',record(seed=130),record(seed=140)),
          pair('missing_winner_is_not_absence',record(seed=150,missing=True),record(seed=160)),
          pair('different_header_order',record(seed=170,names=('A','B')),record(seed=180,names=('B','A')),('B','A')),
          pair('samples_only_in_one_source',record(seed=190,names=('A',)),record(seed=200,names=('B',)),('B','A'))]
priority.append(Case('earliest_same_source_record',(Batch('first',('S',),(record(seed=210),record(seed=220))),
                                                    Batch('second',('S',),(record(seed=230),))),('S',)))
priority.append(Case('identical_duplicate_is_a_contribution',(Batch('first',('S',),(record(seed=240),record(seed=240))),),('S',)))
priority.append(Case('absent_sample_at_key',(Batch('first',('A',),(record(names=('A',),pos=31),)),
                                           Batch('second',('B',),(record(names=('B',),pos=32),))),('B','A')))
priority.append(Case('three_sources',(Batch('a',('S',),(record(seed=260),)),
                                    Batch('b',('S',),(record(seed=270),)),
                                    Batch('c',('S',),(record(seed=280),))),('S',)))

grouping=[Case('local_contig_ids',(Batch('first',('S',),(record(chrom='chrA'),record(chrom='chrB',seed=20)),('chrA','chrB')),
                                   Batch('second',('S',),(record(chrom='chrA',seed=30),record(chrom='chrB',seed=40)),('chrB','chrA'))),('S',)),
          Case('numeric_positions',(Batch('first',('S',),(record(pos=2),record(pos=100))),
                                    Batch('second',('S',),(record(pos=10),record(pos=100)))),('S',)),
          Case('ref_separates_same_position',(Batch('first',('S',),(record(),)),
                                              Batch('second',('S',),(replace(record(alt=('T',)),ref='C'),))),('S',)),
          Case('relative_manifest_paths',(Batch('first',('S',),(record(),)),),('S',),relative=True),
          Case('header_only_source',(Batch('first',('S',),()),Batch('second',('S',),(record(),))),('S',)),
          Case('utf8_chromosomes',(Batch('first',('S',),(record(chrom='chr10'),record(chrom='chr2')),
                                         ('chr2','chr10')),),('S',))]

completion=[Case('all_sources_empty',(Batch('first',('S',),()),),('S',)),
            Case('missing_source_file',(Batch('first',('S',),(),fault='missing'),),('S',),False),
            Case('unknown_selected_sample',(Batch('first',('S',),(record(),)),),('UNKNOWN',),False),
            Case('unreadable_header',(Batch('first',('S',),(),fault='header'),),('S',),False),
            Case('missing_sample_column',(Batch('first',('S',),(record(),),fault='columns'),),('S',),False)]

CASES={'projection':tuple(projection),'priority':tuple(priority),
       'grouping':tuple(grouping),'completion':tuple(completion)}


def source_facts(case):
    """Finite facts about generated sources, not release output or a solver."""
    loci={}
    for rank,batch in enumerate(case.batches):
        for ordinal,row in enumerate(batch.records):
            key=(row.chrom,row.pos,row.ref)
            entry=loci.setdefault(key,{'alts':set(),'origins':[], 'samples':{n:[] for n in case.selected}})
            entry['alts'].update(row.alt)
            entry['origins'].append((batch.source,ordinal))
            for name,values in row.samples:
                if name not in entry['samples']:continue
                entry['samples'][name].append({'source':batch.source,'ordinal':ordinal,'format':list(row.tags),
                                              'values':dict(zip(row.tags,values)), 'alleles':(row.ref,*row.alt)})
    return loci
