# Repair a durable DDI evidence release ledger

A local bioinformatics group curates drug–drug interaction (DDI) evidence from three CSV feeds. Its current ledger can lose a batch receipt, apply a retry twice, or advertise an incomplete release when a process exits mid-operation. Repair `ddi-ledger` in `/opt/ddi-ledger/` so imports are exactly once and readers see only complete immutable releases. This is a local filesystem task; no server, network, privileged command, or external broker is needed.

The public helper `/opt/ddi-ledger/curation.py` provides RDKit parsing and curation functions. You may use or replace it. The damaged `/opt/ddi-ledger/ledger.py` is the program to repair. Your implementation may use SQLite, files, locks, or another local design; the exposed behavior below is authoritative, not an internal schema.

## Commands and paths

```text
ddi-ledger bootstrap --state-dir STATE --drugs DRUG_CSV --events EVENT_CSV --interactions INTERACTION_CSV
ddi-ledger apply     --state-dir STATE --batch BATCH_JSON [--crash after_prepare|after_commit]
ddi-ledger publish   --state-dir STATE [--crash after_generation|after_current] [--ready PATH --continue PATH]
ddi-ledger recover   --state-dir STATE
ddi-ledger read      --state-dir STATE --generation CURRENT|GENERATION_ID [--ready PATH --continue PATH]
```

All successful commands except `read` may be silent. `read` prints exactly one compact JSON object plus LF to stdout. On any ordinary error, exit nonzero with a concise nonempty stderr message. `--crash` instead simulates abrupt process termination: exit status **75** without graceful cleanup at the specified checkpoint. The state directory is persistent across invocations. Do not assume commands run in one process. Only `bootstrap` may create a new state directory.

The three supplied full-size inputs are `/data/drug_list.csv`, `/data/DDI_event.csv`, and `/data/newddi.csv`. They must not be edited. Tests also use small replacement CSVs. CSV is UTF-8 (an initial BOM is accepted), parsed with strict quoting; trim fields and ignore records with no non-whitespace field, including empty physical rows. The drug file has no header and each row is `drug_id,SMILES`. The event file has no header and each row is `event_type,description`. The interaction file starts with the exact header `d1,type,d2`. A missing file, invalid UTF-8, bad CSV quoting, or wrong interaction header is fatal; a syntactically valid but biologically invalid *data row* is handled by the curation rules below.

`bootstrap` stores the exact byte SHA-256 of each base file under feed keys `drugs`, `events`, `interactions`. Calling it again with exactly the same three byte sequences is a no-op. Calling it on an initialized state with any different base bytes is a fatal conflict and changes neither committed batches nor advertised releases. A state with no completed bootstrap is not usable by other commands.

## Curation of the committed raw snapshot

Use RDKit to parse and sanitize each nonempty drug SMILES and emit canonical isomeric SMILES with `canonical=True, isomericSmiles=True`. Count malformed rows and invalid molecules. An ID having multiple distinct *valid* canonical structures is conflicting and quarantined; repeated rows with the same structure are allowed. An ID with no valid structure is invalid. Different valid IDs with the same canonical SMILES are aliases; their representative is the lexicographically smallest ID. `drugs_clean.csv` has header `drug_id,canonical_smiles,aliases`, one row per molecule sorted by representative ID, with sorted aliases joined by semicolons.

Event types are nonnegative ASCII decimal integers; `00` and `0` identify the same type. A type with multiple distinct nonempty descriptions is conflicting. A row with an invalid type, empty description, or wrong field count is invalid. The published report records the number of invalid event rows, valid nonconflicting types, and sorted conflicting numeric types.

For each directed raw interaction, apply the first matching rejection reason in this order: `malformed`, `missing_drug`, `conflicting_drug`, `invalid_drug`, `unknown_type`, `conflicting_type`, `self_interaction`, `alias_self_interaction`, `duplicate`. `malformed` includes wrong field count, missing endpoint, and invalid decimal type. Map valid IDs to representative IDs. A duplicate is a previously kept mapped directed `(d1, numeric type, d2)` triple. Do not collapse reverse-direction rows. `interactions_clean.csv` has header `d1,type,d2`, sorted by `d1`, numeric type, then `d2`.

## Batch input and exactly-once replay

A batch is strict UTF-8 JSON with exactly `batch_id`, `number`, and `operations`. Duplicate JSON object keys, NaN/Infinity, unknown or missing fields, and wrong types are fatal. `batch_id` matches `[A-Za-z0-9_-]{1,32}`. `number` is a positive JSON integer, not a boolean. `operations` is an array (possibly empty), applied in array order. Every operation is one of:

```json
{"feed":"drug","op":"UPSERT","drug_id":"DBX","SMILES":"CCO"}
{"feed":"drug","op":"DELETE","drug_id":"DBX"}
{"feed":"event","op":"UPSERT","event_type":"5","description":"effect"}
{"feed":"event","op":"DELETE","event_type":"05"}
{"feed":"interaction","op":"ADD","d1":"DBX","type":"5","d2":"DBY"}
{"feed":"interaction","op":"DELETE","d1":"DBX","type":"05","d2":"DBY"}
```

Trim string values before applying. Drug IDs and interaction endpoints must be nonempty after trimming. Event and interaction types must be nonempty ASCII decimal strings and are compared numerically. SMILES and event descriptions are strings; a biologically invalid SMILES or empty description is accepted as a raw row and subsequently reported by curation. Drug/event UPSERT removes *all* raw rows with the same key, then appends one new row. Their DELETE removes all matching rows; an absent key is a valid no-op. Interaction ADD appends one directed raw row. Interaction DELETE removes all raw rows matching the directed endpoints and numeric type; the reverse direction is unaffected. An absent directed triple is a valid no-op.

Every new batch must have `number` exactly one greater than the highest committed number, starting at 1. Its `batch_id` and SHA-256 of the **raw JSON file bytes** are committed with its operations. Retrying a committed ID with byte-identical content is a no-op, even after newer batches commit. Retrying the same ID with different bytes is fatal. A different ID cannot reuse a committed number. A batch receipt and the complete effect of its operations become visible atomically; two processes racing to commit the same next number cannot both succeed. `apply` does not change `CURRENT`.

For a new valid batch, `apply --crash after_prepare` exits 75 after all format, identity and sequence validation but before any batch commit. `apply --crash after_commit` exits 75 after the complete batch commit but before reporting success. After the former, the batch is absent; after the latter, a byte-identical retry is a no-op. An already committed byte-identical retry returns success without repeating crash hooks. A malformed or conflicting batch must not alter receipts, committed data, `CURRENT`, or previously advertised files, even when a crash option is present.

## Immutable publication and recovery

`publish` builds from one committed snapshot, not a mixture of two batch numbers. It writes a complete generation under `STATE/releases/GENERATION_ID/` and only then atomically replaces `STATE/CURRENT` with the generation ID followed by LF. Repeating `publish` on an unchanged committed state reuses that exact generation without changing its bytes. Previously advertised generations remain byte-for-byte immutable. Concurrent `publish` and `apply` commands must never make `CURRENT` regress to an older committed batch after a newer one was advertised.

With both `--ready READY --continue CONTINUE`, `publish` selects its committed snapshot, writes `ready\n` to READY, and waits up to 30 seconds for CONTINUE before completing publication. Supplying only one path is an error. A publisher may hold a serialization lock while waiting; concurrent writers need not finish before the barrier is released. This operational barrier makes an older publisher reproducibly overlap later writers and publishers. It does not permit an older snapshot to overwrite a newer advertised snapshot.

`recover` is idempotent. It ignores incomplete staging and publishes the latest *committed* state as a complete generation; it never applies uncommitted operations. A `publish --crash after_generation` exits 75 after all generation files exist but before changing `CURRENT`. A `publish --crash after_current` exits 75 after replacing `CURRENT`. In both cases, `recover` converges on the latest committed generation without corrupting an older advertised one.

Each generation has exactly four required files: `drugs_clean.csv`, `interactions_clean.csv`, `report.json`, and `manifest.json`. CSVs use UTF-8 and LF. Every JSON output is UTF-8 with sorted object keys, compact separators (`,` and `:`), no ASCII escaping, and one trailing LF. SHA-256 strings are lowercase hexadecimal.

`report.json` has exactly these top-level keys:

- `state_id`: string defined below.
- `batch_number`: highest committed number, or 0 for the base snapshot.
- `raw_rows`: object with integer `drugs`, `events`, `interactions` counts; input headers and blank rows are excluded.
- `drugs`: `valid_ids`, `unique_molecules`, `invalid_rows` (integer count), sorted `invalid_only_ids`, sorted `conflicting_ids`.
- `events`: `valid_types`, `invalid_rows` (integer count), sorted numeric `conflicting_types`.
- `interactions`: `kept` and `dropped`; the latter has exactly the nine rejection-reason integer counts listed above.
- `files`: flat SHA-256 strings for `drugs_clean.csv` and `interactions_clean.csv`.

Let `base` map `drugs`, `events`, `interactions` to their original byte hashes. Let `batches` be the committed receipts in numeric order, each object having exactly `batch_id`, `number`, `sha256` (raw batch bytes). Define canonical JSON bytes as described above. Then:

```text
state_id = SHA256(canonical_json({"base":base,"batches":batches}))
file_hashes = {name: SHA256(exact file bytes) for name in
               ["drugs_clean.csv","interactions_clean.csv","report.json"]}
generation_id = SHA256(canonical_json({"state_id":state_id,"files":file_hashes}))
```

`manifest.json` has exactly `generation_id`, `state_id`, `base`, `batches`, and `files` (the latter is `file_hashes`). This avoids a self-referential manifest hash. `CURRENT` is not a JSON file.

## Pinned reader

`read --generation CURRENT` resolves `CURRENT` exactly once; an explicit generation ID is a 64-character lowercase hex string. It validates the pinned manifest, both CSV hashes, report hash, state and generation IDs, then prints a canonical JSON object with exactly `generation_id`, `state_id`, `batch_number`, and `files`. Missing, partial, or corrupt generations fail nonzero; a reader must not silently switch to a newer generation.

If `--ready READY --continue CONTINUE` are both present, `read` resolves the generation, writes `ready\n` to READY, waits up to 30 seconds for CONTINUE to exist, then validates and returns the *already pinned* generation. This is a reproducible operational barrier for readers overlapping publication. Supplying only one barrier path is an error. Tests never require guesses about process scheduling.

## Assessment and limits

Chemical identity and curation account for 0.20, strict batch identity/replay and racing writers 0.25, crash recovery 0.30, complete generations and pinned readers 0.20, and diagnostics/non-clobber 0.05. Groups are additive with no score cap. Tests use small independent replay models, process-failure checkpoints, byte sentinels, and the supplied full-size data. The agent has 3600 seconds and the verifier 900 seconds. A container error, OOM, or interrupted trial is not a difficulty score. This contract concerns **process exits**, not machine power failure.
