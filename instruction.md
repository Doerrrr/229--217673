# Repair the joint DDI evidence release audit

You are maintaining a drug-drug interaction (DDI) evidence publisher used before model training and robustness review. The upstream export now includes ordered changes. The container has three damaged parts: CSV curation, a native keyed-graph bridge engine, and a release publisher joining their outputs. Repair all three. This is a data-quality and network-analysis task, not a clinical recommendation.

The direct curator command must work as specified below:

```bash
/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --out-dir /output
```

Do not modify the source files in `/data`.

The final publisher command uses the same six inputs but is named
`/usr/local/bin/ddi-release-audit`. It writes immutable generations under
`/output/generations/` and updates `/output/CURRENT` only after all files are
validated. Its additional output contract and the separate native engine
contract follow the curation rules. You may edit only the installed application
sources and launchers under `/opt/ddi-curator`, `/opt/ddi-bridge/src`,
`/opt/ddi-release`, and `/usr/local/bin/ddi-curate` or
`/usr/local/bin/ddi-release-audit`; do not edit `/data`, the test harness, or
the task configuration. C++20, G++, Python 3.11, and RDKit are installed.

## Input contracts

- `drug_list.csv` is UTF-8 CSV **without a header**. Each non-blank row has exactly two non-empty fields, `drug_id,SMILES`. A row with the wrong number of fields or an empty field is `malformed`; a structurally valid row whose SMILES RDKit cannot parse and sanitize is `invalid_smiles`.
- `DDI_event.csv` is UTF-8 CSV **without a header**. Each non-blank row has exactly two fields, `event_type,description`. A wrong field count is `malformed`; a type that is not one or more ASCII decimal digits (`0`–`9`) is `invalid_type`; a valid type with an empty description is `empty_description`. Convert valid types to non-negative base-10 integers, so `01` and `1` denote the same type.
- `newddi.csv` is UTF-8 CSV with the header `d1,type,d2`. Each non-blank data row must have exactly three fields, non-empty `d1` and `d2`, and a `type` consisting of one or more ASCII decimal digits. A row failing any of these structural checks is `malformed`, before any drug or event lookup. Convert valid types to non-negative base-10 integers; an integer absent from the event dictionary is `unknown_type`.
- Surrounding whitespace in fields is insignificant. Blank physical rows are ignored. Report line numbers refer to the 1-based last physical line occupied by the corresponding CSV record.
- DDI records are directed. `(A, 7, B)` and `(B, 7, A)` are different records.

## Incremental publication

First curate the three original files as a **baseline**, using all rules below. Then replay the three change files against the raw snapshot and curate the resulting **final** snapshot with the same rules. Each change file is UTF-8 CSV with exactly the header shown below; blank physical rows are ignored. Within each file, `seq` is a positive ASCII decimal integer and must strictly increase (gaps are allowed). Replay each file in its own order; there is no cross-file ordering requirement. Trim surrounding whitespace from all fields. Wrong headers, field counts, operations, sequences, or keys/values described below are fatal input errors.

- `drug_changes.csv`: `seq,op,drug_id,SMILES`. `drug_id` must be non-empty. `UPSERT` requires a non-empty RDKit-parseable/sanitizable SMILES and replaces **all raw rows** for that exact ID with one new row. `DELETE` requires an empty SMILES field and removes all raw rows for that ID; a missing ID is a legal no-op.
- `event_changes.csv`: `seq,op,event_type,description`. The type must be ASCII decimal digits; compare types numerically, so `01` and `1` are the same key. `UPSERT` requires a non-empty description and replaces all raw rows for that type with one new row. `DELETE` requires an empty description and removes all raw rows for that type; an absent type is a legal no-op.
- `interaction_changes.csv`: `seq,op,d1,type,d2`. Both drug IDs must be non-empty and `type` must be ASCII decimal digits. `ADD` appends one directed raw row, including when an identical row already exists. `DELETE` removes **all raw rows** matching the directed `(d1, numeric type, d2)` key; an absent key is a legal no-op. Reverse-direction rows are unaffected. The referenced drugs or event type need not exist: ordinary final curation handles those cases.

Structural/sequence/change-value errors must be found before replacing any old output. Invalid molecules and other bad rows in the three **original** files remain non-fatal and are reported by the curation rules below. Physical line numbers in invalid-row evidence refer to surviving original-file records; valid UPSERT rows use their physical line in the corresponding change file if ever needed.

## Drug curation

Use RDKit to parse and sanitize each SMILES, then generate canonical isomeric SMILES (`canonical=True`, `isomericSmiles=True`).

- Malformed rows and invalid SMILES must be reported.
- If one drug ID has multiple valid rows with the same canonical SMILES, it is valid.
- If one drug ID has more than one distinct valid canonical SMILES, quarantine that ID as conflicting.
- An ID with no valid SMILES is invalid.
- Different valid IDs that resolve to the same canonical SMILES are aliases. Use the lexicographically smallest ID as the representative.

Write `/output/drugs_clean.csv` with UTF-8, LF line endings and this header:

```text
drug_id,canonical_smiles,aliases
```

Write one row per unique molecule, sorted by representative `drug_id`. `aliases` is the semicolon-separated, lexicographically sorted list of all valid IDs for that molecule, including the representative.

## Event curation

- Repeated rows with the same type and description are allowed.
- A type associated with more than one distinct non-empty description is conflicting and cannot be used.
- Malformed types, empty descriptions and malformed rows must be reported.

## Interaction curation

Process non-blank interaction rows using this first-match rejection order:

1. `malformed`
2. `missing_drug`
3. `conflicting_drug`
4. `invalid_drug`
5. `unknown_type`
6. `conflicting_type`
7. `self_interaction`
8. `alias_self_interaction`
9. `duplicate`

Map valid drug IDs to their canonical representatives. A duplicate is an already-kept, mapped, directed `(d1, type, d2)` triple. Do not collapse reverse-direction records.

Write `/output/interactions_clean.csv` with UTF-8, LF line endings and this header:

```text
d1,type,d2
```

Sort rows by `d1`, integer `type`, then `d2`.

Write `/output/interaction_delta.csv` with UTF-8, LF line endings and header `action,d1,type,d2`. Compare baseline and final **kept** interactions by directed identity `(canonical isomeric SMILES of d1, numeric type, canonical isomeric SMILES of d2)`. Emit one `REMOVE` row for each identity present only at baseline, using its baseline representative IDs; emit one `ADD` row for each identity present only at final, using its final representative IDs. Sort all `REMOVE` rows first, then `ADD` rows, each by `d1`, numeric `type`, `d2`. A change of representative ID caused only by a new alias must not create a false delta. The delta is a set difference, not a count of raw ADD/DELETE operations.

## Report and reliability requirements

Write `/output/report.json` as deterministic UTF-8 JSON with a trailing newline. It must contain:

```json
{
  "input": {
    "drug_rows": 0,
    "event_rows": 0,
    "interaction_rows": 0
  },
  "final_input": {
    "drug_rows": 0,
    "event_rows": 0,
    "interaction_rows": 0
  },
  "changes": {
    "drug_rows": 0,
    "event_rows": 0,
    "interaction_rows": 0,
    "delta_added": 0,
    "delta_removed": 0
  },
  "drugs": {
    "valid_ids": 0,
    "unique_molecules": 0,
    "invalid_rows": [],
    "invalid_only_ids": [],
    "conflicting_ids": []
  },
  "events": {
    "valid_types": 0,
    "invalid_rows": [],
    "conflicting_types": []
  },
  "interactions": {
    "kept": 0,
    "dropped": {
      "malformed": 0,
      "missing_drug": 0,
      "conflicting_drug": 0,
      "invalid_drug": 0,
      "unknown_type": 0,
      "conflicting_type": 0,
      "self_interaction": 0,
      "alias_self_interaction": 0,
      "duplicate": 0
    }
  },
  "files": {
    "drugs_clean.csv": {"sha256": "..."},
    "interactions_clean.csv": {"sha256": "..."},
    "interaction_delta.csv": {"sha256": "..."}
  }
}
```

Each invalid row entry must contain the 1-based physical `line`, the available identifier (`drug_id` or `event_type`, using an empty string when unavailable), and a stable `reason` (`malformed`, `invalid_smiles`, `invalid_type`, or `empty_description`). Sort invalid row entries by line; sort all ID/type lists.

`input` counts describe the original snapshot; `final_input` counts describe the raw snapshot after replay. All `drugs`, `events`, and `interactions` curation statistics describe the **final** snapshot. `changes` row counts exclude headers and blank physical rows; `delta_added` and `delta_removed` count semantic delta rows. The SHA-256 values are lowercase hexadecimal digests of the exact bytes written to the three CSV files.

The command must be deterministic and safe to rerun. Validate all six input files before replacing existing output files. On a missing input or fatal CSV syntax/header/change-contract error (for example, an unterminated quoted field or repeated `seq`), print a concise message to stderr, exit non-zero, and leave all four existing output files unchanged.

## Native keyed-graph bridge engine

Repair `/opt/ddi-bridge/src/bridge_index.cpp`; `/opt/ddi-bridge/build.sh` must
produce `/opt/ddi-bridge/bridge-index`. The engine reads one valid native graph
stream from stdin. Its first line is `n operation_count`, with vertices
`0..n-1`; following lines are:

- `+ key u v`: add or replace keyed undirected edge `key`.
- `- key`: retract it; an absent key is a no-op.
- `? a b key`: query the current graph and key.

Different keys with equal endpoints are parallel physical edges. Replacing a
key first removes its old edge. Self-loops never are bridges. A key is a bridge
iff deleting *that individual edge* increases the connected-component count.
Remove all bridge keys simultaneously to define two-edge-connected blocks.
Connected-component and block IDs are their minimum vertex; sizes count
vertices, not edges. Isolated vertices remain present.

For each query output one line of exactly 16 ASCII integers, separated by
spaces, in this order:

`query_index cc_count bridge_count block_count cc_min_a cc_size_a block_min_a
block_size_a cc_min_b cc_size_b block_min_b block_size_b same_cc same_block
key_active key_bridge`

`query_index` starts at zero. Flags are 0 or 1. An absent key has both key
flags zero. Valid native input may include parallel edges, replacements,
retractions, and self-loops. The public `/opt/ddi-bridge/client.py` also accepts
the raw DDI stream below, converts it to keyed graph operations, and invokes
the engine; it contains no bridge algorithm. The grader checks both forms.

Raw DDI stream: first line `n operation_count`; following lines are `D raw
state molecule`, `E type state`, `P key raw_d1 type raw_d2`, `R key`, or `Q a b
key`. State 0 means missing, drug state 1 valid, drug state 2 conflicting,
drug state 3 invalid-only; event state 1 valid and 2 conflicting. A valid drug
binding has molecule `0..n-1`; other states use placeholder molecule 0.
`D` and `E` replace a binding/state, `P` replaces an assertion by key, and `R`
retracts it. An assertion contributes one undirected physical edge only when
both drugs and the event are valid, raw endpoints differ, and canonical
molecule endpoints differ. Inactive assertions remain stored and may reactivate
after later corrections. Reverse raw direction remains distinct physical
evidence. `Q` queries the indicated molecules and evidence key. IDs and keys
are positive integers; event types are nonnegative integers.

The supported native workload has up to 60,000 vertices, 139,999 operations,
and 40,000 queries. Each of two independent 40,000-query families has a
45-second wall-time limit on the supplied two-CPU Linux environment. The
candidate native child has a 1,536 MiB virtual-address-space limit. Small
semantic runs have a 30-second bound and compilation a 150-second bound. Any
algorithm satisfying the public behavior and limits is valid.

## Immutable joined release

Run `/usr/local/bin/ddi-release-audit` with the same six named input options
and `--out-dir /output`. The publisher must first curate the final snapshot by
the rules above, then create a graph from its *final* clean CSVs:

1. Each distinct canonical isomeric SMILES in `drugs_clean.csv` is one vertex,
   numbered by lexical SMILES order. Representative ID changes caused by an
   alias must not change vertex identity.
2. Every data row of `interactions_clean.csv` is a separate undirected physical
   edge; its key is the one-based CSV data-row index. The DDI row remains
   directed as data, so `(A,type,B)` and `(B,type,A)` yield parallel graph
   edges. No record is collapsed merely because its reverse is present.
3. Graph connected components, individual-key bridges, and two-edge blocks
   have exactly the native definitions above.

Create one generation directory `/output/generations/<generation_id>/` with
the curator's four files plus these two UTF-8, LF-terminated CSVs:

- `molecule_audit.csv`: header
  `canonical_smiles,cc_min_smiles,cc_size,block_min_smiles,block_size,cc_count,bridge_count,block_count`;
  one row per molecule in lexical SMILES order. The minimum labels are canonical
  SMILES strings, not representative IDs. All counts and sizes are integers.
- `bridge_evidence.csv`: header `evidence_index,d1,type,d2`; one row for each
  final clean interaction whose own physical edge key is a bridge. Sort by
  numeric evidence index. Preserve the directed `d1,type,d2` of that row and
  print the event type as a normalized integer.

For these six content files (three curator CSVs, its `report.json`, and two
new CSVs), compute lowercase SHA-256 of exact bytes. Let `file_hashes` be a
JSON object mapping each filename to its digest. Compute `generation_id` as
SHA-256 of UTF-8 `json.dumps(file_hashes, sort_keys=True,
separators=(",", ":"))`. Write `manifest.json` as UTF-8 JSON with trailing LF:
`{"generation": generation_id, "files": file_hashes}`. JSON whitespace and
key order in the manifest may vary; its parsed content and trailing LF must
match. `/output/CURRENT` contains only `generation_id` followed by LF.

Stage and validate all files before moving `CURRENT`. Identical reruns reuse
the same generation without changing its bytes. If any input, curation, graph,
or manifest step fails, exit nonzero with a concise stderr message and leave
the previous `CURRENT` and all advertised generation files byte-for-byte
unchanged. An unadvertised staging directory is not a valid generation.

## Assessment

The six-input curator behaviors account for 0.40, native temporal bridge
behavior for 0.40, and joined release behavior for 0.20. Groups are additive
with no score cap. Tests use hand-sized curation fixtures, independent
individual-key deletion/BFS for small graphs, analytic large graph families,
cross-module fixtures, and actual output hashes. A failure to compile only
loses native behavior and any joined behavior that requires that engine; it
does not erase independent curator points. The agent has 3600 seconds; a
verifier infrastructure error, OOM, or interrupted trial is not a difficulty
result.
