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

## Actual Linux evidence and decision

Personal commit `b5718e94a65a195a1806f31377bc7850d9905866` passed the immutable fixed workflow, run `38188634197`: Harbor Oracle completed reward=1.0, NOP completed reward=0.0. This validates the complete reference under the Linux Docker verifier, not only the portable substitute.

The completed blind answer was installed only as the solution on audit branch `audit-blind-ddi-20261012`, commit `4b193427b5b4aedddafcb91ed3a3d6c707c4208e`. Candidate environment, instruction, verifier, task configuration and GitHub workflow were unchanged from `b5718e9`. Fixed workflow run `38188878602` measured blind reward=0.9615 and NOP=0.0; both trials completed. The audit job is red only because its unchanged final step requires a golden Oracle score of 1.0, whereas this branch intentionally contains a blind answer. This is not a runtime error and is not formal platform T1.

With additive weights, any failed publication responsibility would deduct at least 0.07. The observed deduction is 0.0385, so all five publication responsibilities passed. Per-case artifacts are unavailable because the fixed upload action excludes the hidden `.trials` directory; the exact failed legacy group is not claimed. The blind agent had a candidate-only context and explicit access restrictions, not an OS-enforced agent filesystem sandbox. Its answer was not tuned on hidden scores and no rerun of the same blind solution is planned.

This is a counterexample to the proposed publication difficulty hypothesis under this local agent. It does not predict DeepSeek/GLM scores, but it gives no reason to spend a finite platform run on this draft. Hold synchronization; do not change weights or invent new failure conditions to lower the already-observed score. A subsequent design should reconsider how DDI data evolution and release state share one correctness boundary, rather than attach another independent API. That redesign is not implemented in this revision.
