"""Deliberately incomplete implementations, solely for verifier validation."""
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'solution'))
import oracle_release as ref
from screen_optimizer import audit
from incorrect_optimizer import solve_plan as faulty_solver
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
elif mode in ('greedy','reuse','ignore_plan','clip','split_stock','per_assay_setup','ignore_min','float_lex'):
    def incomplete(targets,options,metadata,resources,policy):
        if mode in ('split_stock','per_assay_setup','ignore_min','float_lex'):
            return faulty_solver(targets,options,metadata,resources,policy,variant=mode)
        if mode in ('ignore_plan','clip'):
            values=ref.exact_matching(options)
            if mode == 'ignore_plan':
                return values,'OPTIMAL'
            result=[None]*len(values)
            for i,value in enumerate(values):
                tentative=result[:]; tentative[i]=value
                report=audit(targets,tentative,metadata,resources,policy,'OPTIMAL')
                if (report['total_cost'] <= policy['budget'] and sum(v is not None for v in tentative) <= policy['max_pairs']
                    and all(r['used']<=r['capacity'] for r in report['stock_usage'])
                    and all(r['used']<=policy['cluster_cap'] for r in report['cluster_usage'])
                    and all(r['used']<=r['max'] for r in report['event_usage'])):
                    result=tentative
            return result,'OPTIMAL'
        result=[]
        used=set()
        for edges in options:
            match=next((edge for edge in edges if mode == 'reuse' or edge[0] not in used),None)
            if match:
                used.add(match[0])
            result.append(match)
        return result,'OPTIMAL'
    ref.solve_plan=incomplete
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
