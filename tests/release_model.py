"""Independent verifier model: graph traversal and rectangular assignment.

This does not import or execute the reference solution. The matching algorithm
is Hungarian assignment, independently checked against exhaustive enumeration.
"""
import csv
import hashlib
import io
import math
from collections import defaultdict
from pathlib import Path

from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Scaffolds import MurckoScaffold

RDLogger.DisableLog('rdApp.*')
FOLDS = ('train', 'validation', 'test')
HEADERS = {
    'molecules.csv': ['drug_id', 'canonical_smiles', 'aliases', 'cluster_id', 'fold'],
    'positives.csv': ['fold', 'd1', 'type', 'd2'],
    'unobserved_pairs.csv': ['fold', 'target_index', 'd1', 'type', 'positive_d2', 'candidate_d2', 'score', 'state'],
}
REASONS = ('malformed', 'missing_drug', 'conflicting_drug', 'invalid_drug',
           'unknown_type', 'conflicting_type', 'self_interaction', 'alias_self_interaction', 'duplicate')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(header, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def records(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, strict=True)
        for row in reader:
            row = [cell.strip() for cell in row]
            if row and not (len(row) == 1 and not row[0]):
                yield reader.line_num, row


def number(value):
    return int(value) if value and all('0' <= c <= '9' for c in value) else None


def curate(root):
    drug_records = list(records(root / 'drug_list.csv'))
    event_records = list(records(root / 'DDI_event.csv'))
    interaction_records = list(records(root / 'newddi.csv'))
    assert interaction_records and interaction_records[0][1] == ['d1', 'type', 'd2']
    structures = defaultdict(set)
    known_ids = set()
    drug_bad = []
    for line, row in drug_records:
        key = row[0] if row else ''
        if key:
            known_ids.add(key)
        mol = Chem.MolFromSmiles(row[1]) if len(row) == 2 and key and row[1] else None
        if mol is None:
            reason = 'invalid_smiles' if len(row) == 2 and key and row[1] else 'malformed'
            drug_bad.append(dict(line=line, drug_id=key, reason=reason))
        else:
            structures[key].add(Chem.MolToSmiles(mol, isomericSmiles=True))
    conflicts = {key for key, values in structures.items() if len(values) > 1}
    invalid = known_ids - structures.keys()
    by_smiles = defaultdict(list)
    for key, values in structures.items():
        if key not in conflicts:
            by_smiles[next(iter(values))].append(key)
    molecules = []
    aliases = {}
    for smiles, keys in by_smiles.items():
        keys.sort()
        molecules.append((keys[0], smiles, ';'.join(keys)))
        aliases.update((key, keys[0]) for key in keys)
    molecules.sort()
    descriptions = defaultdict(set)
    event_bad = []
    for line, row in event_records:
        raw = row[0] if row else ''
        value = number(raw)
        reason = 'malformed' if len(row) != 2 else 'invalid_type' if value is None else 'empty_description' if not row[1] else None
        if reason:
            event_bad.append(dict(line=line, event_type=str(value) if reason == 'empty_description' else raw, reason=reason))
        else:
            descriptions[value].add(row[1])
    type_conflicts = {key for key, values in descriptions.items() if len(values) > 1}
    dropped = dict.fromkeys(REASONS, 0)
    positives = set()
    for _, row in interaction_records[1:]:
        if len(row) != 3 or not row[0] or not row[2] or number(row[1]) is None:
            dropped['malformed'] += 1
            continue
        a, typ, b = row[0], number(row[1]), row[2]
        if a not in known_ids or b not in known_ids:
            reason = 'missing_drug'
        elif a in conflicts or b in conflicts:
            reason = 'conflicting_drug'
        elif a in invalid or b in invalid:
            reason = 'invalid_drug'
        elif typ not in descriptions:
            reason = 'unknown_type'
        elif typ in type_conflicts:
            reason = 'conflicting_type'
        elif a == b:
            reason = 'self_interaction'
        elif aliases[a] == aliases[b]:
            reason = 'alias_self_interaction'
        elif (aliases[a], typ, aliases[b]) in positives:
            reason = 'duplicate'
        else:
            positives.add((aliases[a], typ, aliases[b]))
            continue
        dropped[reason] += 1
    report = {
        'input': dict(drug_rows=len(drug_records), event_rows=len(event_records), interaction_rows=len(interaction_records)-1),
        'drugs': dict(valid_ids=len(aliases), unique_molecules=len(molecules), invalid_rows=drug_bad,
                      invalid_only_ids=sorted(invalid), conflicting_ids=sorted(conflicts)),
        'events': dict(valid_types=len(descriptions)-len(type_conflicts), invalid_rows=event_bad, conflicting_types=sorted(type_conflicts)),
        'interactions': dict(kept=len(positives), dropped=dropped),
    }
    return molecules, sorted(positives), report


def clusters(molecules):
    mols = [Chem.MolFromSmiles(row[1]) for row in molecules]
    # Legacy bit-vector API provides an independent route to the same bits.
    fps = [AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048, useChirality=True) for mol in mols]
    keys = [Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(mol), isomericSmiles=True) or row[1]
            for mol, row in zip(mols, molecules)]
    adjacency = [set() for _ in molecules]
    groups = defaultdict(list)
    for i, key in enumerate(keys):
        groups[key].append(i)
    for members in groups.values():
        if members:
            for i in members[1:]:
                adjacency[members[0]].add(i)
                adjacency[i].add(members[0])
    for i, fp in enumerate(fps):
        for j, similarity in enumerate(DataStructs.BulkTanimotoSimilarity(fp, fps[:i])):
            if similarity >= .8:
                adjacency[i].add(j)
                adjacency[j].add(i)
    todo = set(range(len(molecules)))
    meta = {}
    while todo:
        component = []
        stack = [todo.pop()]
        while stack:
            current = stack.pop()
            component.append(current)
            fresh = adjacency[current] & todo
            todo.difference_update(fresh)
            stack.extend(fresh)
        key = min(molecules[i][1] for i in component)
        cluster = digest(key.encode())
        bucket = int(cluster, 16) % 20
        fold = FOLDS[0 if bucket <= 13 else 1 if bucket <= 16 else 2]
        for i in component:
            meta[molecules[i][0]] = (cluster, fold, fps[i])
    return meta


def assignment(options):
    """Rectangular Hungarian algorithm, unlike the Oracle residual flow."""
    n = len(options)
    if not n:
        return []
    candidates = sorted({key for edges in options for key, _ in edges})
    rank = {key: i for i, key in enumerate(candidates)}
    base = len(candidates)+1
    scale = base ** n
    penalty = (10000*n+1)*scale
    infinity = (n+2)*penalty
    costs = []
    for i, edges in enumerate(options):
        row = [infinity]*len(candidates) + [penalty+len(candidates)*base**(n-i-1)]*n
        for key, score in edges:
            row[rank[key]] = -score*scale+rank[key]*base**(n-i-1)
        costs.append(row)
    m = len(costs[0])
    u, v, p, way = [0]*(n+1), [0]*(m+1), [0]*(m+1), [0]*(m+1)
    for i in range(1, n+1):
        p[0] = i
        j0 = 0
        minimum = [infinity]*(m+1)
        used = [False]*(m+1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = infinity
            j1 = 0
            for j in range(1, m+1):
                if not used[j]:
                    cur = costs[i0-1][j-1]-u[i0]-v[j]
                    if cur < minimum[j]:
                        minimum[j], way[j] = cur, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m+1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    selected = [None]*n
    for j in range(1, len(candidates)+1):
        if p[j]:
            i = p[j]-1
            key = candidates[j-1]
            selected[i] = (key, dict(options[i])[key])
    return selected


def expected(root):
    molecules, interactions, report = curate(root)
    meta = clusters(molecules)
    molecular_rows = [(*row, *meta[row[0]][:2]) for row in molecules]
    positives = {fold: [] for fold in FOLDS}
    cross = 0
    for row in interactions:
        if meta[row[0]][1] == meta[row[2]][1]:
            positives[meta[row[0]][1]].append(row)
        else:
            cross += 1
    positive_rows = [(fold, *row) for fold in FOLDS for row in positives[fold]]
    known = defaultdict(set)
    for a, _, b in interactions:
        known[a].add(b)
        known[b].add(a)
    pair_rows, targets_by_fold, edges_by_fold, matching = [], {}, {}, {}
    for fold in FOLDS[1:]:
        anchors = defaultdict(list)
        for row in positives[fold]:
            anchors[row[0]].append(row)
        targets = [anchors[a][i] for i in range(max([len(v) for v in anchors.values()] or [0]))
                   for a in sorted(anchors) if len(anchors[a]) > i][:48]
        options = []
        for a, _, b in targets:
            available = []
            for c, (cluster, assigned_fold, fp) in meta.items():
                if assigned_fold != fold or c in (a,b) or cluster == meta[b][0] or c in known[a]:
                    continue
                similarity = DataStructs.TanimotoSimilarity(fp, meta[b][2])
                if similarity >= .15:
                    available.append((c, math.floor(10000*similarity+.5)))
            options.append(sorted(available, key=lambda item: (-item[1], item[0]))[:8])
        matches = assignment(options)
        for index, (target, match) in enumerate(zip(targets, matches), 1):
            pair_rows.append((fold, index, *target, *(match or ('',0)), 'MATCHED' if match else 'UNMATCHED'))
        count = sum(match is not None for match in matches)
        matching[fold] = dict(targets=len(targets), matched=count, unmatched=len(targets)-count)
        targets_by_fold[fold], edges_by_fold[fold] = targets, options
    report['release'] = dict(
        clusters=len({v[0] for v in meta.values()}), cross_fold_withheld=cross,
        folds={fold: dict(molecules=sum(v[1] == fold for v in meta.values()), positives=len(positives[fold])) for fold in FOLDS},
        matching=matching,
    )
    tables = dict(zip(HEADERS, (molecular_rows, positive_rows, pair_rows)))
    report['files'] = {name: {'sha256': digest(csv_bytes(HEADERS[name], rows))} for name, rows in tables.items()}
    return tables, report, targets_by_fold, edges_by_fold
