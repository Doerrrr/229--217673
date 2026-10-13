# Rules-first symbolic-lineage checker: actual evidence

Status: full external-trial contract, runtime and independent grading pipeline
are prepared. Numbered packet freezing is the next release step. No external
answer has been scored; no general production Oracle solution is claimed.

The previous frozen ledger remains a counterexample, with two eligible first
answers scoring 1.000. The new task does not retroactively change that result.

## Independent checking

`certificate_check.py` verifies a supplied reduced ordered decision diagram,
its finite path-length layers, and the exact minimal-support characteristic
function. It derives rational probability, hypothetical source sensitivities,
support counts and rank selections. No general graph-to-diagram answer compiler
or reference implementation is used by the checker.

`hand_checks.py` has an intentionally limited <=8-source control constructor:
it enumerates source worlds, performs set-based directed BFS, and computes
minimal supports by literal subset removal. Its expected scalar metrics are
calculated independently of BDD arithmetic. This is a tiny quality oracle,
not a production answer for 96-source tasks.

The separate large control is a closed-form chain of parallel evidence sources.
For K=40, manual identities are 3^40 satisfying assignments, 2^40 minimal
supports, support size 40, probability (3/4)^40, and source sensitivity
(1/2)*(3/4)^39. Its valid certificate uses 1759 nodes and 77909 bytes;
it does not enumerate 2^80 worlds or 2^40 support sets.

## Executed controls

- Eight controls passed: independent/shared diamond, unequal-size minimal
  supports with cycles, conditions/endpoints, no sources, and serial K=1/4/40.
- Shared-source probability is checked against 3/8; replacing it with the
  independent-edge value 7/16 was actually rejected.
- Mutated initial layers and fabricated family counts were actually rejected.
- Quality evidence:
  `E:/coding/passby/talentsAi/general_coding/deliverables/ddi_symbolic_lineage_20261013/quality_r2/quality_result.json`.
- Measured whole control runtime: 0.163 seconds on the current host.

The first quality run failed because the K=1 control constructor requested
rank 1 twice. The published rank uniqueness rule was not loosened; the
constructor now removes duplicate requests. The first directory is retained.

## Full behavior mapping and tool controls (2026-10-13)

The full 20 checks are implemented with the precommitted 0.05 weights. Four
checks verify supplied directed/shared-evidence layers, nine verify minimal
families/counts/ranks, four verify exact conditional probability/sensitivity,
and three verify deterministic serialization, fatal preservation and CLI/new
directory behavior. The large-family check additionally exercises 96 sources.

`quality_full_r2/quality_result.json` records 17 hand-known semantic controls,
the 96-source boundary, 200 Boolean truth-table trials and 500 independent
small directed-graph BFS/subset-enumeration trials. All passed in 1.894 seconds.
These verify the checker; they do not score a model answer. No general
graph-to-production-answer compiler is part of the grader.

Proof, family and probability credit are independent. Wrong probability leaves
proof/family credit intact; a wrong minimal root (including orphaned old nodes)
does not erase a correct reachability proof or probability. Canonical
serialization is scored separately, and remains strict.

`quality_runtime_r1/quality_receipt.json` is the first actual Linux Docker
installation/grading control. A finite dispatcher of already hand-known
fixtures scored 1.000 (20/20); the original nonimplemented application scored
0.000; wrong-probability control scored 0.800; wrong-minimal-root control scored
0.450. All four containers exited normally without OOM. These are AUTHOR
QUALITY CONTROLS, not fresh model answers, not a general Oracle, and not
formal Harbor Oracle/NOP results. Normal grading took about 3.4 to 10.4 seconds.

The private verifier runs as root, but every answer command runs as UID/GID
10001 with no-new-privileges, no network and process-group timeout cleanup.
The executed confinement probe confirmed that the answer UID cannot read
`/tests/test_outputs.py` or `/logs/verifier/reward.txt`. Answer ZIP paths and
symlinks are screened before installation. Public packages exclude all tests,
quality controls, old answers, Git history and score records.

After this first successful control, eight additional public-contract malformed
input cases, an explicit output/log size allowance, and a digest-pinned Python
image were added before external freezing. The final frozen operator must be
retested; the earlier receipt is not evidence for those final changes.

## Remaining acceptance steps

1. Freeze committed source into readable DDI-008 v01 public/operator ZIPs.
2. Retest final frozen-container installation/grading and verify packet hashes.
3. Preserve the original three CSVs and fixed workflows; this task changes neither.
4. Give the same frozen public package to two independent external agents,
   record first answers and their real model/time evidence, and grade without
   feedback/retries. Accept the local goal only with two eligible scores <=0.700.

No new local answer agent may be started. The user selected external agents.
No platform sync or detection is authorized by this prototype quality result.

## Counterexample-driven decision rule

If either eligible first answer scores above 0.700, retain the high result and
inspect its actual code and per-check evidence before changing the task. Never
reweight a frozen rubric, select the lowest retry or call an environment failure
a low model score. A substantive new contract uses a new version (or task ID
if the center changes), while all old scores remain associated with the old SHA.

If both independent first answers complete normally within the declared coding
budget and each scores <=0.700, audit installation/freshness/runtime failures
and verify the same frozen rubric was used. Very low scores require extra
inspection of actual answer behavior. Only this evidence can satisfy the local
difficulty goal. Platform acceptance is a separate R1/Oracle/T1/R2 process and
is currently unverified; this external packet has no complete production Oracle.
