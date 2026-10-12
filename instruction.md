# Repair the DDI curation and release pipeline

You are maintaining a drug-drug interaction (DDI) preprocessing job used before model training. The upstream export now includes ordered change files. The current containerized job neither replays them nor produces a trustworthy curated dataset.

Repair the implementation and launcher already present in the container, including `/opt/ddi-curator/publication.py`. Training workers need a complete, immutable generation while concurrent curation jobs publish new data. The completed legacy command must be:

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
- Surrounding whitespace in fields is insignificant. Blank physical rows and CSV records whose fields are all empty after trimming are ignored. Report line numbers refer to the 1-based last physical line occupied by the corresponding CSV record.
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

The command must be deterministic and safe to rerun. Validate all six input files before replacing existing output files. On a missing input or fatal CSV syntax/header/change-contract error (for example, an unterminated quoted field or repeated `seq`), print a nonempty error description to stderr, exit non-zero, and leave all four existing output files unchanged.

## Immutable generation publication

The legacy mode above remains supported. Two additional **optional but paired** arguments select publication mode:

```bash
ddi-curate --drugs /data/drug_list.csv --events /data/DDI_event.csv \
  --interactions /data/newddi.csv --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --out-dir /output/releases-store --release-id batch_a --expected-parent NONE
```

Here `--out-dir` is a store root, not a flat output directory. `NONE` means there is no committed generation. Otherwise the expected parent is a release ID. IDs match the ASCII regex `[a-z][a-z0-9_-]{0,39}`. Reject a missing half of the pair or an invalid ID before modifying the store. Fully validate and curate all six inputs before asking the publisher to change store state. Publication payloads are the **same four byte sequences** that the legacy invocation would write for those inputs; do not add publication metadata to `report.json`.

Provide these public Python functions in `publication.py`; callers import them by putting `/opt/ddi-curator` on `sys.path`:

```python
publish(root, release_id, expected_parent, artifacts, hook=None) -> str
read_current(root) -> dict | None
```

`root` accepts a nonempty string or `pathlib.Path` (including a not-yet-existing multilevel directory). In the Python API, `expected_parent` is `None` or a valid ID, **not** the CLI sentinel. `artifacts` is a dictionary with exactly the four filenames listed above and values of type `bytes`. Validate these types/keys/IDs and that `hook` is None or callable before creating files. Do not modify the caller's dictionary. Fatal API errors raise an exception; no particular exception class or wording is required. The CLI must exit nonzero with a nonempty error description. Use Linux local-filesystem semantics; network filesystems, power loss, and malicious external writers are outside scope.

### Store layout and integrity

- `CURRENT` contains exactly the current ID plus ASCII LF, or is absent before the first commit.
- `releases/<id>/` contains the four payloads and `manifest.json`. Once sealed, this directory and its bytes must never change, even if it is not yet committed.
- A manifest is UTF-8 JSON containing exactly `version` (integer 1, not Boolean), `release_id`, `parent` (ID or null), and `sha256` (exactly the four filenames mapped to lowercase SHA-256 digests of their bytes). JSON whitespace/key order is not prescribed.
- A release is **committed** iff it is CURRENT or lies on its manifest-parent chain. Each reachable manifest must have the correct directory ID, legal fields, matching payload hashes and an existing parent, with no cycle. Reject a corrupt current chain without changing committed files or CURRENT. Do not confuse an unreferenced sealed directory with a committed release.
- Reserve `.writer.lock`, `.staging/`, and names beginning `.current-` at the store root for publisher bookkeeping. Keep a stable writer-lock file: never unlink or replace it. Do not delete unrelated root files. After a successful publish (including an idempotent retry), `.staging/` has no children and no `.current-` temporary files remain. After an exception or killed writer, these private remnants may exist; the next successful call must remove them. Old sealed generations, including unreferenced ones, are retained.

`read_current` reads CURRENT **once** and returns None if absent, without creating a store. Otherwise it returns exactly `{"release_id": id, "parent": parent_or_none, "artifacts": {filename: bytes, ...}}`. It validates that captured generation's manifest and hashes; it need not walk ancestors. It must not block on the writer lock. If CURRENT advances while a reader is fetching files, the reader still returns the complete captured generation, never a mixture. Captured generations remain readable after later publications.

### Compare-and-swap, retries, and failure boundary

Serialize writers across threads and independent processes, including different root paths resolving to the same directory. Read and validate the actual current chain **after** acquiring writer exclusivity. For a new release, require current ID == expected_parent; two writers competing for the same parent must have exactly one successful commit. A loser must not change CURRENT or any committed bytes. Ordinary readers must remain able to fetch the old generation while a writer is staging or waiting to commit.

The request identity is `(release_id, parent, exact four artifact bytes)`:

1. If that exact release is already committed, return its ID successfully even if CURRENT has advanced to a descendant. **Never move CURRENT backwards.** Do not invoke hooks for this no-work retry.
2. Reusing any sealed ID with different parent or content is an error, whether or not it is committed.
3. If an identical sealed directory is uncommitted (a writer died after sealing), it may be reused only when the expected-parent compare-and-swap still holds. If another release has won, reject the stale request; do not attach the orphan to a different parent.

Stage a complete generation and seal it before atomically switching the single CURRENT pointer. Persist files and relevant directories with `fsync` before reporting success. This requirement concerns independent-process termination, not recovery from arbitrary power loss. A failure before pointer replacement leaves the old CURRENT and all committed bytes unchanged. A failure after pointer replacement leaves the new release committed, even if the caller saw an exception. In both cases locks must be released and later calls must work.

### Public failure-injection callback

When provided, invoke `hook(event, detail)` synchronously at these boundaries while holding writer exclusivity:

- `after_stage_file`, `{"release_id": id, "name": filename}`: after each staged artifact is written/closed, before sealing. Invoke once per artifact, in filename-lexicographic order. This event does not run when reusing an already-sealed orphan.
- `after_seal`, `{"release_id": id}`: after the complete generation directory is sealed and before pointer replacement (also when reusing an orphan).
- `after_switch`, `{"release_id": id}`: after CURRENT has switched and been persisted, before returning.

Propagate callback exceptions without masking them or rolling back a committed pointer. The callback may pause or terminate the process; do not convert a callback failure into success. No callbacks are invoked on an already-committed retry. Tests coordinate processes using these public events rather than relying on timing sleeps.

### Completion and assessment

Repair the deployed command and module, run checks, and finish; extra stress suites are not a prerequisite. Assessment gives 0.55 to the existing curation/replay/delta obligations and 0.45 to five publication responsibilities: CLI payload/snapshots (0.10), writer compare-and-swap (0.10), request identity/idempotence (0.08), exception/crash recovery (0.10), and API/integrity/path boundaries (0.07). These are additive checks with no score cap for a single failed responsibility. A command that cannot produce the legacy artifacts receives zero. No clinical validity of the source interactions is asserted.
