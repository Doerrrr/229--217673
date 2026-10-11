# V4 verification evidence

Date: 2026-10-11. Local host: Windows, Python 3.11, RDKit 2025.3.6,
OR-Tools 9.14.6206, SciPy 1.15.3. Machine-readable results: local_results.json.
These are portable checks, not local Docker evidence. The fixed Harbor 0.5.0
CI must independently confirm the published commit in Linux Docker.

## Objective and independent truth

The Oracle constructs a CP-SAT edge/activation model. The verifier separately
constructs a sparse binary MILP with SciPy/HiGHS; it never imports the Oracle.
Both fix maximum count, maximum integer score and minimum actual cost before
fixing each target's lexicographic candidate rank. Only proven optimal/infeasible
statuses are accepted, not merely feasible incumbents.

Both optimizers agree with exhaustive enumeration on **500** fixed-seed small
resource instances, including empty edge sets, zero costs/stock, quotas,
overlapping roles and clusters. This is separate from agreement on full data.

An explicit hand witness has targets A/type0, F/type1, C/type1. Candidates D/E
share cluster X; F/G share Y. All stock is 1, setup 3, assay 1, budget 14,
cluster cap 1; both event types require >=1. D,UNMATCHED,F yields 2 experiments,
16000 score, 4 participants * 3 + 2 assays = **14**. Old matching D,G,F followed
by clipping can leave D,G with 15000 instead. Both independent models reproduce
the hand optimum; this proves why joint planning is required.

## Manually checked molecular examples

Selections below follow actual public target order, not input row order.

| Case | Chosen candidates | Count | Score | Cost |
| --- | --- | ---: | ---: | ---: |
| Shared roles, stock 1 | UNMATCHED,A,D,UNMATCHED | 2 | 12308 | 0 |
| Event quota/stock witness | I,E,F,UNMATCHED | 3 | 5417 | 0 |
| Once-only setup, budget exactly 15 | J,G,UNMATCHED,D | 3 | 14659 | 15 |
| Cost before lex, expensive E | J,G,UNMATCHED,UNMATCHED | 2 | 10770 | 0 |
| A/ZZ aliases share one unit | C,F,D,UNMATCHED | 3 | 15892 | 3 |
| Zero fees and zero budget | D,A,F,UNMATCHED | 3 | 17602 | 0 |

In the budget witness, D and G occur in both roles. There are only four prepared
molecules A,D,G,J, not six preparations: 4*3 + 3*1 = 15. Charging per role/assay
would lose a feasible optimum. In the cost witness, equal count and score prefer
candidate G over lexicographically smaller E because E incurs setup 9.
A and ZZ configure the same canonical structure; they cannot expand its stock.

Additional cases cover positive quotas with no candidates (INFEASIBLE),
stock 0, feasible empty plans, budget 0 with nonzero setup, and empty raw inputs.
For valid infeasibility, all target rows remain, with zero consumption/cost and
explicit unmet minima in event_usage. All base molecules/positives still publish.

The exact inclusive **0.15** fixture uses unchanged raw DB00014 as anchor,
DB00104 as positive_d2 and DB11660 as candidate: candidate score **1500**.
V3 chemistry fixtures still check scaffold equality, chiral/acyclic identities,
and the DB00666/DB06825/DB06788 transitive component.

## Controls actually executed

| Local implementation | Reward | Detected business error |
| --- | ---: | --- |
| Reference Oracle | 1.000 | All 15 checks pass |
| Unrepaired draft/NOP | 0.000 | No implemented release |
| Ignore plan / V3 matching | 0.580 | Budget/pair limit and exact selections |
| Old matching then clip | 0.750 | Suboptimal joint quantity/score |
| Separate anchor/candidate stock | 0.800 | Shared inventory witnesses |
| Setup charged for every assay | 0.850 | Budget boundary and exact optimum |
| Ignore event minimum | 0.780 | Infeasible status and quota feasibility |
| Floating lex perturbation | 0.850 | Late lexicographic choice and full rows |

Every resource mutant failed a corresponding business assertion, not a missing
dependency, timeout or runtime exception. These rewards are **not T1 forecasts**:
one isolated defect can still earn >0.700 under the unchanged partial-credit
weights. No weights were increased or score cap added to force lower scores.
Historical V3 chemical controls remain in Git and executable, but their older
receipts are not presented as fresh V4 runs.

## Runtime and reliability

Three consecutive fresh verifier processes (empty per-process fixture cache,
no forced OS cache flush) each obtained 1.000:
**232.765 / 218.844 / 221.219 seconds**, all below **450 seconds**.
Other author controls sometimes ran concurrently, so these are conservative
host observations, not guaranteed timing for all machines.
Agent stays **2400 s**; verifier is **600 s**. No time reduction.

Strict plan tests cover malformed/missing JSON, root/nested duplicate keys,
missing/unknown fields, incorrect versions, booleans/floats masquerading as
integers, illegal ranges, unknown/invalid/conflicting drug references,
conflicting alias overrides, unknown/conflicting/duplicate event quotas.
All fatal cases preserve sentinel bytes in all four previous outputs and
require nonempty stderr. Missing each of five CLI flags and no arguments
are included. Existing CSV BOM/leading blanks/quoted commas/escaped quotes,
multiline physical lines and directory creation checks remain.

## Full dataset

The original curation and chemical partition are unchanged:
1700 molecules, 86 valid events, 191570 directed positives, 1125 clusters.
Fold molecules: 1208/268/224; same-fold positives: 93650/4987/3720;
cross-fold withheld 89213. Thus 102357+89213=191570.

| Fold | Targets | Experiments | Score | Actual cost |
| --- | ---: | ---: | ---: | ---: |
| validation | 48 | 19 | 48920 | 94 |
| test | 48 | 17 | 45297 | 95 |

The independent MILP's **full lexicographic result** agrees with the CP-SAT
Oracle, not just the first three totals. Resource ledgers are recomputed from
actual selected pairs and checked against stock, budget, cluster caps and quotas.
CSV hashes are pinned in tests/full_snapshot.json:
molecules b7ff3f9e..., positives 8365bac8... unchanged from V3;
unobserved_pairs **97338759dc16f41cafed944c6ba7183ae944e4d89cf8e2148f36e1717888434a**.
V3 summary/hashes are preserved in validation/v3_full_snapshot.json.

## Packaging and scope

check_release_assets.py guards original raw hashes and the fixed personal
workflow; also checks stable molecular/positive hashes, syntax, independent
test imports, 15 checks and six unchanged weights .35/.20/.15/.10/.10/.10.
The platform mode guards raw assets but intentionally leaves its different
workflow to the Git before/after check in the handoff.

check_boundary.py and its self-test reject exact candidate/hidden duplicates.
The candidate image explicitly copies only app/release.py, excluding ignored
local legacy pyc caches. It includes six candidate files (one draft, one
launcher, four inputs). No hidden reference launcher is installed. Oracle
solve.sh installs two Python modules and reuses the existing candidate entry.

Original protected SHA-256:
- drug_list.csv: 9678f897dabe1641e3934a8cd79971c386e2bd17fdff9952af15db6a9a5d932f
- DDI_event.csv: f7bdb8290a8733a783f4a269f1f32ae2f302d41504098120b9dc61345ae19802
- newddi.csv: 3e5613f00e241ff79bafe83199347bad56e9d9e6beec0a1c60e73c72c2adcf68
- harbor-validation.yml: da628e5289907fc57baac03618158602ee8017e775b1f5cc1068c74b662b1156

No platform detection or final submission was triggered. R1/R2 and true T1
difficulty remain unverified for V4. The prior normal T1=0.900 counterexample
is recorded in experience_review.md. User controls the remaining platform runs.

Solver semantics: [CP-SAT status documentation](https://developers.google.com/optimization/cp/cp_solver)
and [SciPy 1.15.3 milp](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.milp.html).
Reproduce with README.md commands and use the locked platform_handoff.md.

## Verified Linux container receipt

Task commit **8023f518432b2f3534c2ac0f2a598650649265f3** passed the unchanged
Harbor 0.5.0 workflow: [run 38142054389](https://github.com/Doerrrr/229--217673/actions/runs/38142054389),
job 114477745362. Oracle trial, NOP trial, reward checks and diagnostics upload
all succeeded. Job logs explicitly record **oracle: reward=1.0** and
**nop: reward=0.0** at 2026-10-11T13:12:05Z. The workflow also rejects trial
exception_info. Machine-readable receipt: harbor_ci_receipt.json.

This confirms Linux Docker controls for that exact task commit, not a platform
T1 or R1/R2 result. The subsequent handoff/receipt-only commit leaves all candidate,
reference and scored test files unchanged; platform synchronization pins the
verified task SHA rather than an unverified moving branch.
