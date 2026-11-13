# EB032-MATH-K v03 platform record

Registered task is mathematics/eb032-math-k-exact-certificate, question 242247. Version v03 preserves the frozen mathematical cases and the v02 scoring denominator. The current general reference must score exactly 1.000 under production test.sh before publication. NOP must complete normally at or below 0.100.

## Supplied historical platform report

The user-supplied first-revision report identifies platform source 394a6c9dde4ca4bf64a6cc3f7595c8b054b2a226. R1 scored 96, NOP 0.000, Oracle 1.000 and candidate 1 0.681 with normal completion. Candidate 2 reached runner_timeout after approximately four hours and produced no valid reward. T1 failed and R2 was unexecuted. Archive integrity fields describe stored artifacts. Candidate command contents were unavailable in the supplied index.

The previously published v02 general reference scored 0.55 locally and did not satisfy the Oracle gate. Its Git commit and ZIP remain recoverable history. Current v03 receipts and source binding appear in local_validation.json and evidence/current.

## Publication and evaluation

The GitHub author repository publishes the complete task, including private scoring and author sources. The candidate Docker image contains app, bin and packet plus locked dependencies. Public author-source availability is recorded separately from local execution and formal platform acceptance.

Use the pinned backup installer and verify_release.py to apply known release bytes. Review the compact staged summary and submit through the platform workflow. This release makes no automatic model calls or platform submissions. Both v03 candidate evaluations, R1 and R2 require new platform receipts.
