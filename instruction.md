# Repair the DDI curation pipeline

You are maintaining a drug-drug interaction (DDI) preprocessing job used before model training. The upstream export now includes ordered change files. The current containerized job neither replays them nor produces a trustworthy curated dataset.

Repair the implementation and launcher already present in the container. The completed command must be:

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
