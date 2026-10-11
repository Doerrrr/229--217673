# V3 verification evidence

Local verification date: 2026-10-11. Python 3.11, RDKit 2025.3.6.
Machine-readable evidence: `local_results.json`. Local verifier runtime was
about 22 seconds, so the verifier budget remains 240 seconds; agent remains
2400 seconds. No time-limit reduction was used.

## Controls and scope

| Implementation | Local reward | Meaning |
| --- | ---: | --- |
| Oracle | 1.000 | All 15 public-contract checks pass |
| Initial draft / NOP | 0.000 | Unrepaired task receives no credit |
| Scaffold-only clusters | 0.340 | Similarity union/transitive closure is detected |
| Greedy matching | 0.650 | Loses cardinality, score or lex optimum |
| Candidate reuse | 0.580 | Violates global capacity |
| Forward-only positive exclusion | 0.600 | Leaks reverse/other-type known positives |

These controls demonstrate test sensitivity, **not expected model T1 scores**.
The latest platform counterexample is documented in `experience_review.md`.
This file records local results only; the fixed GitHub workflow supplies
separate Linux Docker/Harbor evidence. Platform R1/T1/R2 remain unexecuted for V3.

## Independent checks

Reference chemistry uses union-find, generator Morgan fingerprints and min-cost
residual flow. The verifier uses graph traversal, the legacy binary Morgan API,
and rectangular Hungarian assignment; it never imports the reference solution.
Both optimizers were independently compared to exhaustive enumeration on **500**
fixed-seed tiny graphs. Verifier startup also runs 120 independent tiny checks.

Three small molecular examples have explicit independently enumerable options:

| Case | Chosen candidates in target order | Matched | Score |
| --- | --- | ---: | ---: |
| Cardinality trap | I, E, F, UNMATCHED | 3 | 5417 |
| Score trap | J, G, UNMATCHED, E | 3 | 16155 |
| Lexicographic tie | C, A, F, D | 4 | 22046 |

The cardinality greedy result matches only 2 targets. The score greedy result
has total 14659. The lex greedy result D,A,F,C has the same total but is worse
lexicographically. The fixture's round-robin target order is also checked.

Transitive chemical fixture uses immutable records DB00666, DB06825, DB06788:
three distinct scaffold keys, neighbor similarities approximately 0.918699
and 0.805970, outer similarity 0.760563. All three must share a component.
Additional fixtures cover benzene/phenol scaffold equivalence, acyclic fallback,
stereoisomers, salts, canonical aliases, invalid/conflicting IDs, directed
duplicates, numeric event normalization, multiline physical lines, reversed
inputs, smaller representative aliases and reverse known positives.

Ten fatal-input/CLI cases use four pre-existing sentinel files, including
missing file, wrong/missing header, broken quoted CSV in each input, invalid
UTF-8 in each input and unknown CLI option. All four bytestrings must survive.

## Weight allocation

| Delivery value | Weight | Checks |
| --- | ---: | --- |
| Exact matching | 0.35 | cardinality .10, score .10, lex .10, full .05 |
| Chemistry/folds | 0.20 | transitive .08, scaffold/chirality .05, full .07 |
| Safe candidates/scores | 0.15 | reverse .08, top-8/score/capacity .07 |
| Positive partition | 0.10 | full .06, tiny/empty .04 |
| Base curation | 0.10 | precedence .07, CSV/numeric .03 |
| Determinism/no-clobber | 0.10 | rerun/aliases .05, fatal .05 |

No global score cap. Chemistry checks do not require a correct matching CSV;
positive partition checks do not compare the matching report; curation checks
do not require correct chemical folds. Manifest checks use the relevant
artifact, and determinism checks actual file hashes, not an optimal assignment.
This preserves independent credit for correct subsystems.

## Full snapshot and conservation

All 1700 drug IDs have distinct canonical molecular identities; all 86 events
are valid. All 191570 directed interactions survive curation, with zero
rejections. Independent model and Oracle agree on all rows and CSV hashes.

- Clusters: **1125**.
- Molecules train/validation/test: **1208 / 268 / 224**, sum 1700.
- Same-fold positives: **93650 / 4987 / 3720**, sum 102357.
- Cross-fold withheld: **89213**; 102357 + 89213 = 191570.
- Validation: 48 targets, **40 matched**, 8 unmatched.
- Test: 48 targets, **38 matched**, 10 unmatched.

Exact expected hashes are pinned in `tests/full_snapshot.json`.

## Preservation and release boundary

Original input SHA-256, unchanged from personal baseline `54bf8c7`:

- drug_list.csv: 9678f897dabe1641e3934a8cd79971c386e2bd17fdff9952af15db6a9a5d932f
- DDI_event.csv: f7bdb8290a8733a783f4a269f1f32ae2f302d41504098120b9dc61345ae19802
- newddi.csv: 3e5613f00e241ff79bafe83199347bad56e9d9e6beec0a1c60e73c72c2adcf68
- harbor-validation.yml: da628e5289907fc57baac03618158602ee8017e775b1f5cc1068c74b662b1156

Old feed files and launchers are removed only from the new task interface;
their prior versions remain recoverable in Git history. No platform detection
or final submission was triggered by local verification.

## Reproduce

```bash
uv run --python 3.11 --with rdkit==2025.3.6 python validation/check_optimizer.py
uv run --python 3.11 --with rdkit==2025.3.6 python validation/validate_release.py --mode oracle
uv run --python 3.11 --with rdkit==2025.3.6 python validation/validate_release.py --mode nop
# Repeat with --mode scaffold_only, greedy, reuse, forward_only.
```

Use the unchanged Harbor 0.5.0 workflow for final container controls, then
`platform_handoff.md` for user-controlled synchronization and one detection.

