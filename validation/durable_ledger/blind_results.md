# Frozen durable-ledger first-answer results

The local difficulty goal was **not met**. Both independent first answers passed
all 20 precommitted checks and scored 1.000. No weight, contract, input or verifier
was changed after either answer was received. These are local evidence, not
TalentsAI DeepSeek/GLM T1 trials.

| Field | First | Second |
| --- | --- | --- |
| Start UTC | 2026-10-13 01:25:24 | 2026-10-13 01:25:32 |
| Freeze UTC | 2026-10-13 01:36:41 | 2026-10-13 01:41:24 |
| Coding seconds | 677 | 952 |
| Excluded environment waits | 0 | 0 |
| Exact deployment/version | unavailable | unavailable |
| Normal verifier completion | yes | yes |
| Container exit / OOM | 0 / false | 0 / false |
| Reward | 1.000 | 1.000 |
| Passed checks | 20 / 20 | 20 / 20 |

- Frozen author commit: `54fd0ac0c66f30c04d3fca3beb798fc796cbc215`.
- Task digest: `90f897879d84686ed15da1aee548a676e44d74ca5d2c9acfbc7635724e8d2c4d`.
- First answer SHA-256: `2bb17be2ef7f4fe2a9b7767f473e2b84ad3c335d444c9280b736071486ae7ca2`.
- Second answer SHA-256: `b0edcb5200d74271b19df6b0fb1b22334049756ab12163411f134055b095eeab`.
- Evidence root: `E:/coding/passby/talentsAi/general_coding/deliverables/ddi_ledger_20261013/frozen_r2/`.
- Raw results: `score_blind_first/result.json`, `score_blind_second/result.json`.
- Check details: the corresponding `verifier/details.json` files.

Both candidates used a writer lock and atomic whole-state JSON replacement;
immutable release directories and a pinned-reader protocol resolved the public
failure/concurrency requirements. This is a valid implementation route, not a
cheat. The results refute the current claim that transaction/checkpoint features
alone create enough difficulty. Five deliberately incomplete author controls
each scored 0.950; rejecting those controls was not evidence of low model scores.

Both answers froze before any grading. The examiner then graded them serially.
No answer was repaired with scorer feedback. Isolation was procedural on a
shared host, not an OS-enforced filesystem boundary.

## User-directed change in execution

On 2026-10-13 the user requested that the historical incremental baseline be
pushed for a remote Oracle diagnostic, without continuing local tests of that
old task. The personal release branch points to the exact historical commit
`f99fd220e3d5a6665547a1419e8a975c37e45c17`; no platform push/acceptance is claimed.
The already-started local Oracle had finished before cancellation; NOP was not
started. This result is separate from the ledger blind scores.

The user then chose external-agent answers for subsequent blind tests to avoid
further local model-quota use. Do not spawn another local blind agent. Prepare
public task material and an operator-only frozen verifier, and record the actual
external model label and first-answer timing. Preserve all high-score evidence;
do not choose low retries or redefine the score after answers arrive.
