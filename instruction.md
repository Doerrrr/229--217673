# Repair a leakage-safe DDI training-data release

Repair `/usr/local/bin/ddi-release` and its implementation under `/opt/ddi-release`.
The draft conflates IDs and molecules, collapses directions, puts everything in
train, and omits candidate assignment. You may replace it. Python 3.11 and
RDKit **2025.3.6** are installed; no other dependency is needed.
The evaluator reruns the executable with other paths; do not hardcode outputs.

## Command, input parsing and errors

```bash
ddi-release --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv --interactions /data/newddi.csv --out-dir /output
```

All four arguments are required. The old change-feed/withdrawal interface is
removed. Do not modify the three supplied CSV inputs.

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
interaction header or invalid CLI usage are **fatal**: nonzero exit, short
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

## 4. Exact global assignment

Independently per fold, every target may select one eligible candidate; every
candidate molecule may be used **at most once** in the fold. Optimize in order:
1. Maximum number of matched targets.
2. Maximum sum of integer scores.
3. Smallest candidate ID sequence in target_index order under lexicographic
   comparison, with **UNMATCHED greater than every real ID**.

Use exact optimization, not independent greedy choices. Earlier matches may
need reassignment. Every unmatched target still gets an output row.

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
    "unmatched": count}).
  - files: each of the **three CSV filenames** maps to
    {"sha256": "<lowercase SHA-256 of exact bytes>"}.

All counts are integers. Enforce conservation:
interaction_rows = kept + sum(dropped);
kept = sum(fold positives) + cross_fold_withheld;
unique_molecules = sum(fold molecules).
Empty results have CSV headers and complete zero-count reports.

## Evaluation

Fixtures exercise scaffold equivalence, transitive similarity, aliases/order,
reverse-positive exclusion, capacity conflicts, global score and lexicographic
ties, empty input and fatal-input no-clobber; the full snapshot is also checked.
Weights: exact matching **0.35**, chemistry/folds **0.20**, candidate safety/score
**0.15**, positive partition **0.10**, curation **0.10**, determinism/no-clobber
**0.10**. No undocumented score cap or time-reduction trick. Do not modify tests.
