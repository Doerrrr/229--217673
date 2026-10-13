# DDI durable evidence ledger: author standard (draft)

This document is an internal design standard, not a candidate-visible task yet. The original three DDI CSVs remain unchanged. This version is a different task center; it must not be scored by changing the frozen joint-task weights.

## Responsibility

Build a command-line service that imports DDI evidence batches exactly once, curates the committed state, and advertises only complete immutable releases. Processes may terminate at documented checkpoints. Another process may read an older pinned release while a new release is published. No network service, administrator permission, or external broker is required.

## Proposed public CLI

```text
ddi-ledger bootstrap --state-dir STATE --drugs DRUG_CSV --events EVENT_CSV --interactions INTERACTION_CSV
ddi-ledger apply     --state-dir STATE --batch BATCH_JSON [--crash after_prepare|after_commit]
ddi-ledger publish   --state-dir STATE [--crash after_generation|after_current]
ddi-ledger recover   --state-dir STATE
ddi-ledger read      --state-dir STATE --generation CURRENT|GENERATION_ID [--ready PATH --continue PATH]
```

`--crash` is a documented deterministic process-failure hook: the command exits 75 at the named checkpoint without graceful cleanup. It is not a way to relax normal behavior. A `read` with both barrier paths resolves the generation once, creates READY, waits until CONTINUE exists, then reads only that pinned generation. A timeout or missing barrier is a nonzero error with stderr.

`STATE` is local and persistent. The implementation may choose its own database schema and temporary-file names, but must expose `STATE/CURRENT` (generation ID plus LF) and `STATE/releases/GENERATION_ID/` containing the exact published files. All files for a generation are immutable once `CURRENT` has advertised it. A generation may be reused on identical reruns. A partial or unadvertised staging directory is never a valid generation.

## Inputs and batch identity

The base CSV contracts and RDKit chemical canonicalization are inherited from the validated DDI curation task; the new candidate instruction must restate them fully rather than refer to hidden history. `bootstrap` takes byte SHA-256 of each base file. Repeating bootstrap with identical bytes is a no-op; different bytes against existing STATE is fatal and leaves state unchanged.

A batch is UTF-8 JSON with no duplicate keys and exactly:

```json
{"batch_id":"batch-001","number":1,"operations":[
  {"feed":"drug","op":"UPSERT","drug_id":"DBX","SMILES":"CCO"},
  {"feed":"event","op":"DELETE","event_type":"74"},
  {"feed":"interaction","op":"ADD","d1":"DBX","type":"5","d2":"DBY"}
]}
```

`batch_id` matches `[A-Za-z0-9_-]{1,32}`. `number` is a positive JSON integer, not boolean, and must equal the last committed number plus one for a new batch. Operations run in array order. Drug/event UPSERT replaces all raw rows with that key; DELETE removes all matching raw rows. Interaction ADD appends one directed raw row; DELETE removes all matching directed raw rows. Missing-key DELETE is a valid no-op. Keys are trimmed; event types are canonical nonnegative ASCII decimal integers. Unknown/missing fields, invalid operations, malformed JSON, duplicate keys, and malformed batch identity are fatal before any committed state changes. A batch's identity is the SHA-256 of its *raw input bytes*: replaying an already committed `batch_id` with identical bytes is a no-op, even if its `number` is no longer the next number. The same ID with different bytes is a fatal conflict. A previously committed number cannot be reused by another ID.

The batch receipt and all three raw evidence tables become visible in one transaction. With two processes racing for the same next number, exactly one may commit. A failed or killed command must not expose a receipt without its rows or rows without its receipt.

## Releases and recovery

`publish` reads a single committed snapshot. It curates drugs, events, and directed interactions under the public DDI rules, writes `drugs_clean.csv`, `interactions_clean.csv`, `report.json`, and `manifest.json` to a complete generation, then atomically changes `CURRENT`. `report.json` gives the committed batch number, input and rejection counts, canonical molecule count, directed interaction count, and each CSV SHA-256. `manifest.json` gives generation ID, three base byte hashes, ordered batch receipts (`batch_id`, `number`, raw byte SHA-256), and every published file's SHA-256. Exact canonical JSON and generation-ID formulas remain to be fixed *before* candidate-visible release or blind testing; no score can be assigned against a moving formula.

`apply` never changes `CURRENT`. `recover` is idempotent: it ignores incomplete staging, uses only fully committed batches, and advertises the latest committed snapshot as a complete generation. After `after_prepare`, the batch is absent; after `after_commit`, the batch is present exactly once. After `after_generation`, a complete but unadvertised generation may be reused; after `after_current`, the new `CURRENT` must already be readable. An old advertised generation remains byte-for-byte unchanged through all later operations. Fatal input errors do not alter `CURRENT`, previously advertised files, or committed receipts.

`read` resolves `CURRENT` once (or accepts an explicit generation ID), validates the pinned manifest and file hashes, and writes one JSON summary to stdout. The barrier option permits deterministic interleaving with a publisher without timing guesses. Readers may return the old complete generation or the new complete generation depending on when they resolve, but never a mixture. A missing, incomplete, or corrupt requested generation is a nonzero error.

## Precommitted evaluation map

| Business area | Weight | Independent evidence |
| --- | ---: | --- |
| Chemical identity and directed curation | 0.20 | Hand-sized CSVs plus original-data smoke; independent molecule/rule checks |
| Batch identity, strict replay, serializable races | 0.25 | In-memory replay model, duplicate/conflicting retry, two-writer barrier |
| Crash checkpoints and idempotent recovery | 0.30 | Subprocess exits 75 at every checkpoint; state and immutable-file sentinels |
| Complete generations and pinned readers | 0.20 | Manifest hashes, deterministic reruns, reader/publisher barrier |
| Diagnostics and fatal non-clobber | 0.05 | Nonempty stderr, unchanged receipt/CURRENT/advertised bytes |

No cap or timeout-based reward. Oracle=1.000 and NOP=0.000 must complete normally in Harbor 0.5.0 before any local blind. Score each exposed contract on different small inputs; do not import the reference implementation into the verifier. A candidate with one-shot curation alone should earn only its relevant curation points because it has not implemented durable publication. Both normal first blind answers must score <=0.700 on one unchanged frozen task to meet the local goal.

## Operational constraints and source basis

Specify *process crash*, not machine power-loss recovery; do not claim durability beyond the tested failure model. Keep state on one local filesystem. SQLite WAL is an implementation option, not a required solution. Its documented snapshot isolation and reader/writer concurrency support the proposed reference design; Python `os.replace` provides an atomic rename on POSIX when successful. Reference: https://sqlite.org/isolation.html , https://sqlite.org/wal.html , https://docs.python.org/3/library/os.html .
