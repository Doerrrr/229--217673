# Rules-first symbolic-lineage checker: actual evidence

Status: prototype quality checks passed; full candidate package and scoring
fixtures have not been frozen. No external answer has been scored.

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

## Required before external handoff

1. Finish the full 20-check mapping and independent large-family fixtures.
2. Test checker Boolean primitives against direct truth tables, and fuzz small
   directed graphs with conditions and 0/1 probabilities.
3. Separate proof, minimal-family and probability credit: one wrong optional
   metric must not silently become a score cap on unrelated correct behavior.
4. Create the runtime, public instructions, answer packer, operator evaluator
   and immutable manifests. Public material must not contain checker controls,
   expected output, solution or model-score history.
5. Verify fresh-container installation and normal grading. Preserve the original
   three CSVs and fixed workflows; this draft does not alter either.
6. Give the same frozen public package to two independent external agents,
   record first answers and their real model/time evidence, and grade without
   feedback/retries. Accept the local goal only with two eligible scores <=0.700.

No new local answer agent may be started. The user selected external agents.
No platform sync or detection is authorized by this prototype quality result.
