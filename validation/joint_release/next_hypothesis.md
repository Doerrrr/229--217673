# Next difficulty hypothesis: durable DDI release ledger

Status: design only, not a frozen task and not sent to the platform.

## Evidence motivating a change of task center

The joined curation/bridge/release task was valid (Oracle 1.000, NOP 0.000) but two independent first answers scored 0.940 and 0.928 in under 15 minutes. Both passed every bridge and release check. Adding the scores of several independently tractable modules did not produce the requested local <=0.700 result. More edge cases or a post-hoc weight adjustment would not address that mechanism.

## Business responsibility to test next

Use the same original DDI CSVs, but center the task on *exactly-once, crash-recoverable publication* of incremental evidence. The tool persists a batch ledger and a reader-visible release pointer. A batch has an immutable ID, byte digest, ordered operations, and a committed sequence. Retrying the same ID with the same bytes must be a no-op; the same ID with different bytes is a fatal conflict. A successful ingest is atomic across all three evidence tables and its batch receipt. Publication creates a complete immutable generation and changes `CURRENT` only after the generation and manifest are valid. Recovery after an interrupted ingest or publish must converge without applying a batch twice or advertising a partial generation.

The public contract should specify durable files, ordering, retry semantics, required outputs, and explicit fault-injection checkpoints. The challenge is not to guess an undocumented storage format; any internal schema is acceptable. A pinned reader resolves `CURRENT` once and returns a self-consistent generation while another process may publish a newer one. Source data remain unchanged; the published curation rules are inherited where relevant.

## Precommitted assessment hypothesis

The score would follow the new responsibility, not the old additive modules: curation correctness 0.20; batch identity and replay 0.25; transactional crash recovery 0.30; immutable generation/pinned-reader consistency 0.20; diagnostics and deterministic metadata 0.05. No all-or-nothing cap. A plain one-shot curation program can earn its 0.20 but cannot claim that it implements a durable release system.

Use independent in-memory replay for small ordered batches, subprocess crash injection at every public checkpoint, byte sentinels on old generations, duplicate/conflicting retry controls, and simultaneous reader/publisher barriers. Oracle and NOP must both complete normally. Verify failures by business-visible outputs rather than an implementation-specific SQLite schema. Avoid scheduling-sensitive race assertions by using explicit barrier files or documented fault hooks. Keep agent and verifier budgets sufficient for normal completion.

Only after a complete implementation and independent controls pass should the new task be frozen and given to two fresh candidate-only agents. The local gate remains two independent normally completed first answers, each <=0.700; a platform T1 result is separate. If either blind score remains above the gate, diagnose the successful approach before changing the task again.
