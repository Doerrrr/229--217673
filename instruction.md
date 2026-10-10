# Repair the DDI curation pipeline

You are maintaining a drug-drug interaction (DDI) preprocessing job used before model training. The upstream export format has not changed, but the current containerized job no longer produces a trustworthy curated dataset.

Repair the implementation and launcher already present in the container. The completed command must be:

```bash
/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --out-dir /output
```

Do not modify the source files in `/data`.

## Input contracts

- `drug_list.csv` is UTF-8 CSV **without a header**. Each non-blank row has exactly two non-empty fields, `drug_id,SMILES`. A row with the wrong number of fields or an empty field is `malformed`; a structurally valid row whose SMILES RDKit cannot parse and sanitize is `invalid_smiles`.
- `DDI_event.csv` is UTF-8 CSV **without a header**. Each non-blank row has exactly two fields, `event_type,description`. A wrong field count is `malformed`; a type that is not one or more ASCII decimal digits (`0`–`9`) is `invalid_type`; a valid type with an empty description is `empty_description`. Convert valid types to non-negative base-10 integers, so `01` and `1` denote the same type.
- `newddi.csv` is UTF-8 CSV with the header `d1,type,d2`. Each non-blank data row must have exactly three fields, non-empty `d1` and `d2`, and a `type` consisting of one or more ASCII decimal digits. A row failing any of these structural checks is `malformed`, before any drug or event lookup. Convert valid types to non-negative base-10 integers; an integer absent from the event dictionary is `unknown_type`.
- Surrounding whitespace in fields is insignificant. Blank physical rows are ignored. Report line numbers refer to the 1-based last physical line occupied by the corresponding CSV record.
- DDI records are directed. `(A, 7, B)` and `(B, 7, A)` are different records.

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

## Report and reliability requirements

Write `/output/report.json` as deterministic UTF-8 JSON with a trailing newline. It must contain:

```json
{
  "input": {
    "drug_rows": 0,
    "event_rows": 0,
    "interaction_rows": 0
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
    "interactions_clean.csv": {"sha256": "..."}
  }
}
```

Each invalid row entry must contain the 1-based physical `line`, the available identifier (`drug_id` or `event_type`, using an empty string when unavailable), and a stable `reason` (`malformed`, `invalid_smiles`, `invalid_type`, or `empty_description`). Sort invalid row entries by line; sort all ID/type lists.

The SHA-256 values are lowercase hexadecimal digests of the exact bytes written to the two CSV files.

The command must be deterministic and safe to rerun. Validate all input contracts before replacing existing output files. On a missing input or fatal CSV syntax/header error (for example, an unterminated quoted field), print a concise message to stderr, exit non-zero, and leave any existing output files unchanged.
