# Incremental DDI generation publication — author record

## Version and hypothesis

The user-confirmed platform HEAD is `680418aad96437c252f234db9a429296f4ec4807` (v4). Its normal T1 score was 0.900; the second candidate was skipped. The personal repository still has `ce821a5`. The local rollback `8a6ce92` restores the exact tracked tree of `f99fd22`, whose historical platform counterpart `6a7c4a6` scored 0.770 / 0.580. Neither the rollback nor the current draft has been published. Historical model trajectories and per-check scores are unavailable.

The v3/v4 optimization additions did not lower the observed score. This revision tests a different hypothesis: preserving semantic DDI output across simultaneous publication, exceptions, sealed-but-uncommitted generations and retries requires coupled state handling, rather than another independent solver feature. This is not an observed weakness of the platform model and is not a promised score reduction.

## Requirements and independently observable consequences

- Curation/replay/delta: existing 14 checks and original full-data hashes stay intact.
- CLI delivery and snapshots: published artifacts equal flat-mode bytes; a paused writer leaves old readers usable; manifests independently verify payloads.
- CAS: two jobs for one parent produce exactly one committed successor; the stable writer lock survives attempts.
- Request identity: retrying an ancestor succeeds without rollback, changed content/parent is rejected, and a sealed orphan is not mistaken for committed history.
- Recovery: public callback exceptions and actual process termination before/after the pointer boundary preserve the specified generation; fresh processes retry and advance successfully.
- Boundaries: valid Path/string roots, invalid arguments before side effects, committed-chain corruption and cleanup of reserved leftovers without deleting unrelated files.

The 0.55 / 0.45 business allocation is declared before blind scoring. Publication categories have distinct obligations and no score caps. Incorrect runtime setup is not evidence of task difficulty. Generous agent limit is 2400 seconds; verifier budget is 360 seconds, subject to measured Linux runtime.

## Source-bounded experience used

User-supplied `EXPERIENCE.md` (concurrent log handler) and `General-Coding第二期-215620-题面设计与检测复盘.md` support trying coupled recovery, process barriers, independent trusted expectations, correct alternatives and targeted mutants. Their old scores do not predict this task's scores. Public Python 3.11 `fcntl` and `os.replace` documentation informs the reference's Unix lock/rename implementation, but implementations satisfying the public behavior may differ.

Official references: https://docs.python.org/3.11/library/fcntl.html and https://docs.python.org/3.11/library/os.html#os.replace . The batch/store incident and callback interface are task construction, not a claim about a real production incident.

## Validation and release gate

1. Static/package checks, original three CSV bytes and fixed workflow unchanged; environment must not duplicate hidden solution/test files.
2. Portable reference curation regression (not concurrent/Linux evidence).
3. Real Linux publication probes, correct implementation and targeted incorrect controls; record actual per-category results.
4. User-authorized isolated blind solution sees only instruction and explicit environment files. A lost/interrupted run is not assigned a low score.
5. Fixed Harbor 0.5.0 Oracle=1 and NOP=0 on the same final commit.
6. Only then hand off the pinned SHA for platform synchronization. The user owns triggering finite platform detection and final submission.

As of construction, the local Docker engine is unavailable and Ubuntu did not return a shell in a bounded 15-second probe. No WSL/service restart was attempted. The initial blind run was interrupted, then resumed in the same candidate-only directory. It subsequently delivered a completed solution with Windows checks; it has not been hidden-scored and is not assigned a low score. No platform detection has been triggered.

On 2026-10-12 the user confirmed the platform is still `680418a`, asked to skip local WSL while they repair it, and explicitly approved pushing the personal repository to run the fixed GitHub CI. Portable reference curation passed 14/14 including full-data hashes. Three sequential exception/retry/ancestor cases passed with lock/directory-fsync emulation; this is not Unix validation. Package preflight passed with four protected assets unchanged and zero candidate-hidden exact duplicates.
