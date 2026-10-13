# Durable DDI ledger: frozen local difficulty gate

This is the author/operator record, not a candidate-visible answer. The current goal remains unachieved until two normal independent first answers on the same complete frozen task each score at most 0.700. Passing author controls is not difficulty evidence.

## Frozen version

- Author commit: `54fd0ac0c66f30c04d3fca3beb798fc796cbc215`.
- Task digest: `90f897879d84686ed15da1aee548a676e44d74ca5d2c9acfbc7635724e8d2c4d`.
- Frozen folder: `E:/coding/passby/talentsAi/general_coding/deliverables/ddi_ledger_20261013/frozen_r2/`.
- Public ZIP SHA-256: `6aebfd52b35990d9cafea9abfa77c89cb21a6ade54194231dc40c1195c7ea337`.
- Operator ZIP SHA-256: `8cc0438f1d120e173af0bf45d6353960a8e909496d3934f59623fb8bcef3c109`.
- The earlier `frozen_r1` task has identical task bytes but lacks the author-side LF checkout attribute fix. It is retained, not overwritten. Only `frozen_r2` is used for blind candidates.

## Evidence before candidates

Harbor 0.5.0 `ledger-oracle-r2` completed normally with reward 1.000 and exception_info null; `ledger-nop-r2` completed normally with reward 0.000 and exception_info null. Their result JSON files are under `deliverables/ddi_ledger_20261013/harbor_r2/`.

The frozen operator evaluator separately completed Oracle 1.000 and NOP 0.000, exit 0 and no OOM. These records are `frozen_r2/score_oracle/result.json` and `score_nop/result.json`. This checks the exact answer installer, image identity, hidden-file hashes, 20-check list, weights, score recomputation, and verifier terminal state.

Preflight verifies schema 1.3, allow_internet true, original three CSV byte hashes, LF shell launchers, Python syntax, no complete hidden file copied to the candidate environment, and no reference imports in the verifier. It is not a substitute for runtime controls.

## Independent standard, not answer matching

The verifier checks public behavior against manually derived small CSV results, batch byte identities, visible receipts, process exits, snapshot invariants and exact cryptographic definitions. It does not import the reference ledger or demand a particular storage schema. Valid implementations may use SQLite, atomic JSON plus locks, or another design.

Every check is worth 0.05. The 20 checks sum to 1.000 without a score cap:

| Area | Checks | Weight |
| --- | --- | ---: |
| Chemical curation | alias/conflict, event/drop, directed order, original-data run | 0.20 |
| Batch ledger | ordered replay, duplicate retry, conflict/gap, strict JSON, two racing writers | 0.25 |
| Recovery | before/after batch commit, before/after advertisement, stale stage, immutable old generation | 0.30 |
| Generations/readers | exact hashes, repeat/overlapping publication, pinned reader, corrupt generation rejection | 0.20 |
| Fatal diagnostics | invalid input, invalid barriers, unavailable state, unchanged old bytes | 0.05 |

The base small fixture has 6 drug rows, 4 event rows and 9 interaction rows. Manual result: representatives A/CCO (aliases A;B) and C/CCN; BAD invalid-only; X conflicting; event 7 conflicting; directed positives A,5,C and C,5,A. Seven rejected raw interactions have one count each for missing drug, conflicting drug, invalid drug, conflicting type, raw self, alias self and duplicate. This small fixture is independent of the reference implementation.

## Blind procedure

1. Give each candidate only a fresh public folder and empty conversation history; no hidden tests, solution, author history or previous answers.
2. Use the same 3600-second coding budget. Exclude only recorded real environment-only waits. Do not repair host services as part of a blind answer.
3. Freeze one first answer ZIP and its metadata before any grading. Do not give scorer feedback or permit resubmission for that version.
4. Wait for both answers to freeze, then grade serially through the immutable private evaluator. Preserve all original ZIPs, SHA-256 values, actual displayed model identities, timestamps, logs and terminal states.
5. A score is eligible only after normal verifier completion with no OOM, installation fault, external interruption or infrastructure timeout. A near-zero score needs additional audit that a runnable candidate's real behavioral omissions caused it.
6. Accept the local gate only if **both** eligible scores are <=0.700. Keep high-score counterexamples; do not select low retries or edit the frozen standard afterward.

Isolation is procedural: separate public folders and explicit instructions on a shared host. It is not an OS-enforced filesystem sandbox. The exact backend deployment IDs may be unavailable; do not relabel these local agents as formal platform DeepSeek or GLM trials.

## Platform boundary

This ledger task has not been synced to the platform. The currently published joint-release task is a different version and must not be graded by this ledger standard. Platform R1/Oracle/T1/R2 acceptance requires its own report. A missing platform score is not a model low score.
