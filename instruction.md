# Repair a resource-constrained, leakage-safe DDI experiment release

Repair `/usr/local/bin/ddi-release` and its implementation under `/opt/ddi-release`.
The draft conflates IDs and molecules, collapses directions, puts everything in
train, and omits experimental planning. You may replace it. Python 3.11,
RDKit **2025.3.6**, OR-Tools **9.14.6206** and SciPy **1.15.3** are installed.
These supply chemistry and exact optimization; no extra installation is needed.
The evaluator reruns the executable with other paths; do not hardcode outputs.

## Command, input parsing and errors

```bash
ddi-release --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv --interactions /data/newddi.csv \
  --screen-plan /data/screen_plan.json --out-dir /output
```

All five arguments are required. The old change-feed/withdrawal interface is
removed. Do not modify the three supplied CSV inputs or supplied plan.

Read UTF-8 CSV (initial BOM allowed), standard comma/quote escaping, including
quoted multiline fields. Trim every field. Ignore empty physical records and
single-field blank records, not multi-field empty records. Report a record's
**last physical line**, counting blank lines.
Drugs have **no header**, two fields `drug_id,SMILES`. Events have **no header**,
two fields `event_type,description`. Interactions' first nonblank record must
be exactly `d1,type,d2` after trimming. Empty drugs/events are valid; interactions
still require a header. Event types are nonempty **ASCII decimal digits**,
including zero and leading zeros; output normalized decimal integers.

Missing/unreadable inputs, invalid UTF-8, syntactically broken CSV, wrong/missing
interaction header, invalid plan or invalid CLI usage are **fatal**: nonzero exit, short
nonempty error description on stderr, and **all four existing outputs unchanged
byte-for-byte**. Validate all inputs before publication. Wrong data-record field
counts, invalid SMILES and invalid event values are row rejections, not fatal.
Successful runs exit zero; create output directory if needed. No crash-consistent
multi-file transaction is required for OS failure during publication.

## 1. Curate molecular identities and directed positives

Drugs: count every nonblank record. Wrong field count, empty ID or SMILES:
`malformed`; otherwise RDKit sanitized parsing failure: `invalid_smiles`.
Invalid-row evidence includes physical line, trimmed first field as drug_id
(or empty), and reason. Every nonempty ID, even from a bad row, is known.
Valid structures use RDKit canonical **isomeric** SMILES without salt stripping,
tautomerization, neutralization or other standardization.
An ID with multiple distinct valid canonical structures is conflicting and
quarantined. An ID with no valid structure is invalid-only. Bad rows do not
quarantine an ID that also has exactly one valid structure.
Group remaining IDs by exact canonical SMILES. Representative is the smallest
ID in ordinary case-sensitive string order. Aliases are unique sorted IDs
joined with `;`, including the representative; input IDs never contain `;`.

Events: wrong field count is `malformed`, nonnumeric type is `invalid_type`,
numeric type with blank description is `empty_description`. Evidence includes
physical line, reason, event_type (trimmed original first field for the first two
reasons, normalized decimal for the last). Compare trimmed nonempty descriptions.
Multiple descriptions for one numeric type quarantine that type. Known types
have at least one valid nonempty description; valid types exclude conflicts.

Interactions: retain direction, remap IDs to representatives, normalize type
and deduplicate directed triples. Reverse directions and different types are
distinct. Assign exactly the **first** applicable rejection reason:
1. `malformed`: field count not three, empty endpoint, or nonnumeric type.
2. `missing_drug`: endpoint absent from all known IDs.
3. `conflicting_drug`: endpoint is conflicting.
4. `invalid_drug`: endpoint is invalid-only.
5. `unknown_type`: type is not known.
6. `conflicting_type`: type is known but conflicting.
7. `self_interaction`: trimmed original endpoints equal.
8. `alias_self_interaction`: different IDs map to one representative.
9. `duplicate`: remapped directed triple already retained.

## 2. Chemical clusters and immutable folds

For each curated molecule compute RDKit Murcko scaffold SMILES **including
chirality**. Empty scaffold (acyclic molecule) falls back to canonical isomeric
SMILES. Compute **binary Morgan** fingerprint, radius 2, 2048 bits, chirality
included (`GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)`,
other defaults unchanged). All similarities use RDKit Tanimoto on these bits.

Join two molecules if their scaffold keys are equal **OR** similarity >= **0.80**.
Take connected components of the union graph, including full transitive closure.
Do not only group scaffolds or only compare representatives.

Cluster key is its smallest canonical SMILES. cluster_id is lowercase SHA-256
of its UTF-8 bytes. Interpret digest as a hexadecimal integer modulo 20:
**0–13 train**, **14–16 validation**, **17–19 test**. The entire cluster shares
one fold. Aliases/input order cannot change clustering or folding (adding a
smaller alias may change the displayed ID).

Publish only positives with same-fold endpoints; count the rest as
cross_fold_withheld. Known-positive exclusions below use **all curated positives**.

## 3. Targets and safe unobserved candidates

In validation and test separately select at most **48** same-fold positives:
sort anchors d1 by ID; for each anchor sort positives by numeric type then d2.
Take each anchor's first positive in anchor order, then each anchor's second,
etc. Stop at 48 or exhaustion, truncating the last round. target_index is
**1-based** in this selection order, restarting per fold.

For each target (d1,type,positive_d2), enumerate same-fold molecules and exclude:
- the anchor and original positive_d2;
- every molecule in positive_d2's cluster;
- any molecule with a known positive with the anchor in **any event type,
  either direction**.

Similarity compares candidate_d2 to **positive_d2**, not the anchor. Keep
similarity >= **0.15**. Score = `floor(10000 * similarity + 0.5)`.
Sort by **integer score** descending then candidate ID ascending; keep the
first **8**. Never expand beyond those eight to improve assignment.
These are **unobserved candidate pairs**, NOT confirmed biological negatives.

## 4. Strict experimental plan

Read the plan as UTF-8 JSON (without BOM), not CSV. All objects require exactly
the listed keys: missing/unknown keys and duplicate JSON object keys are fatal.
JSON numbers used below must be integers, not booleans, floats or strings.
IDs are exact strings referring to trimmed CSV IDs; do not trim plan IDs.
The complete schema is illustrated by the supplied plan:

```json
{
  "version": 1,
  "defaults": {"stock": 2, "setup_cost": 3},
  "drug_overrides": [],
  "folds": {
    "validation": {
      "budget": 96, "assay_cost": 1, "max_pairs": 20, "cluster_cap": 1,
      "event_quotas": [
        {"type": 5, "min": 1, "max": 6},
        {"type": 25, "min": 1, "max": 6},
        {"type": 14, "min": 1, "max": 6}
      ]
    },
    "test": {
      "budget": 96, "assay_cost": 1, "max_pairs": 20, "cluster_cap": 1,
      "event_quotas": [
        {"type": 75, "min": 1, "max": 6},
        {"type": 5, "min": 1, "max": 6},
        {"type": 8, "min": 1, "max": 6}
      ]
    }
  }
}
```

version must equal 1. drug_overrides and event_quotas are arrays, possibly empty.
Each override has exactly `drug_id,stock,setup_cost`. A drug ID may be any valid,
nonconflicting alias; all aliases of a molecule refer to the same inventory.
Repeated overrides for one molecule are allowed only if both values agree;
conflicts, unknown/invalid-only/conflicting IDs are fatal. Defaults apply to
every molecule without an override. Each quota has exactly `type,min,max`.
Its type must be a valid, nonconflicting event from the events CSV, at most once
per fold. Referencing a valid type with no selectable targets is legal.

Ranges (inclusive): stock 0–96; setup_cost and assay_cost 0–10000;
budget 0–1000000; max_pairs, cluster_cap, min and max 0–48, with min <= max.
The folds object must contain exactly validation and test, with every listed
field present in each. Invalid JSON syntax/encoding, NaN/Infinity and any schema
or reference error are fatal, even if the affected record would never be used.

## 5. Exact joint selection under resources

Independently per fold, every target may select one eligible candidate; every
candidate molecule may be used **at most once** in the fold. Apply these constraints
to the already selected targets and safe top-8 edges; do not add new candidates:

- Every chosen pair consumes one stock unit from its anchor and its candidate.
  Merge both roles by canonical molecular identity. positive_d2 consumes nothing.
  Inventory is reset per fold; aliases cannot provide additional units.
- Each actually used molecule incurs its setup_cost **once**, even if it occurs
  in several assays or both roles. Each chosen pair adds assay_cost. Total cost
  must be <= budget, and selected pair count must be <= max_pairs.
- For each chemical cluster, the number of its molecules used **as candidates**
  must be <= cluster_cap. Anchor usage does not count toward this cap.
- For each specified event, selected pair count must be in [min,max]; unspecified
  events have [0,48]. Quotas concern selected assays, not available positives.

Optimize feasible selections in this exact order:
1. Maximum number of matched targets.
2. Maximum sum of integer scores.
3. Minimum actual total cost, including once-only setup charges.
4. Smallest candidate ID sequence in target_index order under lexicographic
   comparison, with **UNMATCHED greater than every real ID**.

Only proved optima are acceptable; greedy selection, solving old unconstrained
matching then clipping, or collapsing lex order into imprecise floating weights
is not equivalent. Every unmatched target still gets an output row.
When no feasible selection exists, succeed with status **INFEASIBLE**, all targets
UNMATCHED and zero resource consumption/score/cost; do not relax minima. A feasible
empty selection is **OPTIMAL**, not INFEASIBLE. Curated molecules and positives are
published in either case. Resource limits are defined by this synthetic plan;
unobserved assays are not biologically verified negatives.

## Four output artifacts

CSV is UTF-8 without BOM, standard minimal quoting, LF record terminators,
one final LF, no index column. Numeric fields are ordinary decimal integers.
JSON whitespace/key order is unrestricted. Unrelated existing files need not
be removed. Repeated runs must be deterministic.

- `molecules.csv`: header `drug_id,canonical_smiles,aliases,cluster_id,fold`;
  one row per curated molecule, sorted by representative ID.
- `positives.csv`: header `fold,d1,type,d2`; sort by fold order
  train,validation,test then d1, numeric type, d2.
- `unobserved_pairs.csv`: header
  `fold,target_index,d1,type,positive_d2,candidate_d2,score,state`;
  validation before test, then target_index. MATCHED rows have candidate and
  score; UNMATCHED rows have empty candidate, score 0, state UNMATCHED.
- `report.json` required fields:
  - input: drug_rows,event_rows,interaction_rows (interaction header excluded).
  - drugs: valid_ids (nonconflicting IDs with valid structure), unique_molecules,
    invalid_rows (objects line,drug_id,reason sorted by physical line),
    invalid_only_ids,conflicting_ids (sorted ID lists).
  - events: valid_types,invalid_rows (objects line,event_type,reason sorted by
    physical line),conflicting_types (sorted integer list).
  - interactions: kept (all curated triples before partition), dropped
    (all nine reason keys above, including zero values).
  - release: clusters,cross_fold_withheld,folds (train/validation/test each
    maps to {"molecules": count, "positives": count}),matching
    (validation/test each maps to {"targets": count,"matched": count,
    "unmatched": count}), and plan (validation/test each maps to the resource
    object below).
  - files: each of the **three CSV filenames** maps to
    {"sha256": "<lowercase SHA-256 of exact bytes>"}.

Each release.plan fold object has exactly these required fields:
- status: OPTIMAL or INFEASIBLE.
- total_score: sum of selected integer similarity scores.
- total_cost: actual once-only setup plus per-assay cost.
- stock_usage: only actually used representatives, sorted by drug_id; objects
  `drug_id,used,capacity,setup_cost`, including zero-cost participants.
- cluster_usage: only clusters used as candidates, sorted by cluster_id;
  objects `cluster_id,used`.
- event_usage: all explicitly specified quotas, sorted by numeric type;
  objects `type,min,max,used`. Unspecified events are not listed. For INFEASIBLE,
  used is 0 even when min is positive; stock_usage and cluster_usage are empty.

All counts are integers. Enforce conservation:
interaction_rows = kept + sum(dropped);
kept = sum(fold positives) + cross_fold_withheld;
unique_molecules = sum(fold molecules).
Empty results have CSV headers and complete zero-count reports.

## Evaluation

Fixtures exercise scaffold equivalence, transitive similarity, aliases/order,
reverse-positive exclusion, capacity conflicts, global score and lexicographic
ties, shared stock, alias merging, setup activation, budget boundaries, cluster
caps, event coverage, feasible empty and infeasible plans, strict plan errors,
empty input and fatal-input no-clobber; the full snapshot is also checked.
Weights: exact matching **0.35**, chemistry/folds **0.20**, candidate safety/score
**0.15**, positive partition **0.10**, curation **0.10**, determinism/no-clobber
**0.10**. No undocumented score cap or time-reduction trick. Do not modify tests.
