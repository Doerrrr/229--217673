"""Deliberately incomplete implementations, solely for verifier validation."""
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'solution'))
import oracle_release as ref
from rdkit import Chem, DataStructs
from rdkit.Chem.Scaffolds import MurckoScaffold

mode=sys.argv.pop(1)
if mode == 'scaffold_only':
    original=ref.chemistry
    def scaffold_only(drugs):
        meta=original(drugs)
        groups=defaultdict(list)
        for row in drugs:
            key=MurckoScaffold.MurckoScaffoldSmiles(mol=Chem.MolFromSmiles(row[1]),includeChirality=True) or row[1]
            groups[key].append(row)
        for rows in groups.values():
            cluster=ref.sha256(min(row[1] for row in rows).encode())
            bucket=int(cluster,16)%20
            fold='train' if bucket<14 else 'validation' if bucket<17 else 'test'
            for row in rows:
                meta[row[0]]=(cluster,fold,meta[row[0]][2])
        return meta
    ref.chemistry=scaffold_only
elif mode in ('greedy','reuse'):
    def greedy(options):
        result=[]
        used=set()
        for edges in options:
            match=next((edge for edge in edges if mode == 'reuse' or edge[0] not in used),None)
            if match:
                used.add(match[0])
            result.append(match)
        return result
    ref.exact_matching=greedy
elif mode == 'forward_only':
    def directed_edges(targets,fold,metadata,interactions):
        known={(a,b) for a,_,b in interactions}
        options=[]
        for a,_,b in targets:
            eligible=[]
            for c,(cluster,assigned,fp) in metadata.items():
                if assigned!=fold or c in (a,b) or cluster==metadata[b][0] or (a,c) in known:
                    continue
                score=DataStructs.TanimotoSimilarity(fp,metadata[b][2])
                if score >= .15:
                    eligible.append((c,ref.math.floor(10000*score+.5)))
            options.append(sorted(eligible,key=lambda edge:(-edge[1],edge[0]))[:8])
        return options
    ref.candidate_edges=directed_edges
else:
    raise SystemExit('unknown negative-control mode')
raise SystemExit(ref.main())
