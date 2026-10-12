# Repair the versioned DDI evidence library

The chemical curation service has a working Python client and a defective C++
library. Structure corrections must update the directed evidence graph without
changing the snapshots still being read by downstream analyses. Repair the
native component, including its transaction and memory-ownership behavior.
No interaction in this dataset is a confirmed clinical recommendation.

## Deliverable and environment

Implement the C ABI in `/opt/ddi-snapshot/include/ddi_snapshot.h`. Edit
`/opt/ddi-snapshot/src/ddi_snapshot.cpp` and optionally add C++ source/header
helpers **under that src directory**. Run `/opt/ddi-snapshot/build.sh`; this
builds `/opt/ddi-snapshot/libddi.so` using G++ C++20, `-O2`, `-fPIC`, `-shared`,
and `-pthread`. The library must export the declared unmangled functions.
Use the installed C++ standard library; no new packages are needed. Do not
modify the header, build script, Python client, raw data, or runtime configuration.
Python/RDKit 2025.3.6 and G++ are already installed. The native library must work
with the existing `ctypes` client; spawning another interpreter or reading
external answer files is not a replacement for implementing this library.

The public `client.py` accepts a JSON object with `operations`, runs those C ABI
calls, and prints the returned values. It contains no expected answers. Example:

```bash
printf '%s\n' '{"operations":[["engine","e"],["begin","t","e"],["bind","t",1,1,10],["bind","t",2,1,20],["event","t",0,1],["put","t",11,1,0,2],["commit","t"],["current","s","e"],["snapshot","s"]]}' | python /opt/ddi-snapshot/client.py
```

The snapshot above has revision 1, one edge `(10,0,20)` with support 1,
and counts `[0,0,0,0,0,0,0,1]`. Keep your own tests outside the src directory.
The hidden verifier is not an input you need to find.

## Identities and cleaning rules

Raw drug IDs, canonical molecule keys, and raw evidence keys are positive
`uint64_t` values; event types are `uint32_t`, including 0. Canonical molecule
keys come from an upstream RDKit `MolFromSmiles` and canonical isomeric
`MolToSmiles` mapping. The three original CSVs in `/data` are supplied for
end-to-end checks; numeric C ABI fixtures also exercise aliases and conflicts.
Do not parse SMILES inside this native layer. Different raw IDs may refer to
the same canonical molecule key, and a binding may change in a later version.

`ddi_bind(tx,raw,state,molecule)` replaces the entire current interpretation of
one raw drug ID. State MISSING(0) removes it; VALID(1) requires a positive molecule
key; CONFLICTING(2) and INVALID_ONLY(3) require molecule 0. Every non-VALID state
requires molecule 0. `ddi_event` similarly replaces an event state, accepting
only MISSING, VALID, or CONFLICTING. Missing removes the event.

`ddi_put(tx,key,raw_d1,type,raw_d2)` replaces the raw assertion with that evidence
key. Reusing a key must remove its old drug/event dependencies and contribution.
`ddi_remove` removes that key. Removing absent bindings, events, or evidence is a
successful no-op. Different evidence keys with identical endpoint/type content
are distinct current assertions, **not** duplicate keys to discard.

Each current raw assertion receives exactly one reason, in this priority order:

1. Either endpoint binding absent: MISSING_DRUG (index 0).
2. Either endpoint CONFLICTING: CONFLICTING_DRUG (1).
3. Either endpoint INVALID_ONLY: INVALID_DRUG (2).
4. Event type absent: UNKNOWN_EVENT (3).
5. Event type CONFLICTING: CONFLICTING_EVENT (4).
6. Raw endpoint IDs equal: SELF (5).
7. Canonical endpoint molecule keys equal: ALIAS_SELF (6).
8. Otherwise ACCEPTED (7).

Accepted assertions aggregate into the **directed** canonical tuple
`(molecule_d1,type,molecule_d2)`. Edge support equals the number of distinct
currently accepted evidence keys for that tuple. Opposite directions are
different tuples. Counts include every raw key exactly once, even when multiple
accepted keys contribute to the same edge. Binding/event updates must reclassify
already present assertions; a previously rejected assertion may become accepted.

## Transactions and versions

A new engine has committed revision 0 and empty state. `ddi_begin` captures the
current committed state and revision. Only that transaction's working state is
changed by mutations. Other open transactions and existing snapshots must not
change. An operation that returns INVALID must not change state or replay history.

Savepoint tokens are positive and never reused in that transaction. A savepoint
captures its full working state **and the operation history position**.
Rollback restores the selected point, discards later history and later points,
and keeps the selected point usable. Release removes the selected point and
later points but leaves working state and operation history unchanged. An absent
token is INVALID and has no side effects.

Commit succeeds only if the engine's committed revision still equals the
transaction's captured base revision. Exactly one same-base competing writer can
win. Success publishes its complete working state, increments revision by one
(even for a no-op), writes the revision output, and closes the transaction.
A losing commit returns CONFLICT, does not publish, does not change its output,
and leaves its working state and history open for further editing or rebase.

Rebase captures the latest committed state/revision and replays the transaction's
**surviving ordered mutation history** on it. History discarded by rollback is
not replayed. Rebase invalidates all old savepoint tokens. It does not commit.
Subsequent rollback/savepoint and repeated rebase must remain coherent.
Preview captures the current working state, with the captured base revision;
it does not change after rollback, mutation, rebase, or commit of that transaction.

After success, mutations/savepoint/rollback/release/rebase/commit/preview return
CLOSED. `ddi_tx_free` is still required. Freeing an engine closes its live
transactions; operations on them return CLOSED, but transactions can still be
freed. Existing snapshot and diff handles remain usable independently of engine
and transaction lifetime. No call uses a freed engine/transaction pointer.

## ABI and ownership

The exact statuses/layouts are in the header: OK=0, INVALID=1, CONFLICT=2,
CLOSED=3, FAILED=4. Edge records are 32 bytes and diff records 40 bytes on this
64-bit Linux runtime. `reserved` is always zero. Edges sort numerically by
`(d1,type,d2)`, not lexically or insertion order. Empty views return NULL and 0.

`ddi_edges` borrows an immutable contiguous array **owned by that snapshot**.
Repeated successful reads return the same address and bytes until that snapshot
is freed. Later operations on any other handle must not mutate or invalidate it.
`ddi_counts` returns the eight counters above; `ddi_support` returns support for
a positive canonical endpoint tuple, or 0 if absent. Neither changes the snapshot.

`ddi_compare(before,after)` works for arbitrary snapshots, including previews
and different engines. It returns sorted net support changes only: a row has
`before` and `after` support; either may be 0; equal values are omitted. It does
not report transient history or return two rows for one tuple. A diff owns its
data independently of both source snapshots. Repeated `ddi_changes` reads have
the same immutable address until `ddi_diff_free`, even after freeing both inputs.

All status-returning functions reject NULL required handles/out-parameters with
INVALID. Missing scalar keys, invalid enum/state-molecule combinations, and
invalid savepoint tokens are INVALID. Every non-OK return leaves caller-owned
out-parameters untouched (including pointer/count pairs). `ddi_revision(NULL)`
returns 0; every `*_free(NULL)` is a no-op. Invalid arguments are checked before
closed-state checks where both apply; savepoint-token membership is checked only
after confirming that the transaction is open. FAILED denotes unexpected internal failure;
no C++ exception may escape the C ABI. Allocation failures are not injected by
the verifier, but they must not be reported as successful publication.

Handles returned by successful constructors must be freed exactly once. The
verifier will not pass invented non-null addresses, use freed handles, or race
destruction with operations on that same handle. Distinct transactions can be
used concurrently; multiple readers of one immutable snapshot/diff can run
concurrently. A single mutable transaction is used by only one thread at a time.
Different engines must not accidentally share state. Use real native thread
synchronization; `ctypes` C calls are not serialized by Python's GIL.

## Bounded workload and reliability

The supported sparse workload contains up to 200,000 raw assertions and 2,000
raw drug IDs, 1,000 committed revisions changing two evidence keys each, and
34 retained snapshots. Initial loading plus sparse changes and occasional reads
must complete within **120 seconds** with the process's peak RSS at most
**1,536 MiB** on the supplied two-CPU Linux environment. Old snapshots are read
throughout and after engine closure. Reads may materialize an edge array; no
specific data structure is required. Full copying/rebuilding at every sparse
update is not a safe assumption at this volume. Ordinary small semantic checks
have a generous 30-second subprocess bound, independent of the 40-minute coding
budget. Stress processes are isolated so their failure does not erase scores for
completed semantic checks. A runtime/environment failure is not a difficulty win.

Native code must not leak snapshots, transactions, or diffs after their matching
free operations, access released memory, or corrupt borrowed arrays. Your own
AddressSanitizer/UndefinedBehaviorSanitizer checks are encouraged; correctness is
judged through the public contract, not by source resemblance to a reference.

Finish by rebuilding the library. All checks are behavior-based and accept any
C++ implementation satisfying these requirements.

Assessment is additive, with no score cap. The independent behavior groups are:
ABI/invalid inputs .05; directed edges .06; alias support .06; drug cascade .07;
event cascade .05; replacement dependencies .05; preview isolation .08; nested
savepoints .07; rollback/rebase history .08; conflicts/revisions .05; net diffs
.06; snapshot lifetime .06; diff lifetime .04; concurrent CAS .05; concurrent
readers .04; composed mutation histories .05; supplied chemical data .04; sparse
versions .04. An implementation is not required to resemble any reference code.
