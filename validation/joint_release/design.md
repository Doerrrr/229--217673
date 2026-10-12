# DDI release audit: joined curation and network robustness

Status: authoring prototype. This branch is not the published platform task and has no T1 score.

## Hypothesis

Three independently frozen local coding tasks have now yielded normally completed full-score model answers: the native snapshot (one answer), the temporal bridge engine (two answers), and a certificate core (one local partial). The bridge task's correct-but-rebuild-every-query negative control scored 0.650, yet both blind answers implemented efficient exact methods and scored 1.000. Increasing the graph size or reducing its time limit would not address that finding. A legitimate next test is one DDI publication workflow whose deliverable requires accurate raw-data curation, temporal network analysis, and their release boundary together. This is a new task version; none of the earlier frozen scoring rules will be changed after seeing answers.

## Public task outline

Repair a containerized DDI evidence publisher with three initially damaged parts:

1. The `ddi-curate` program reads the three original CSVs and three ordered change CSVs. It emits `drugs_clean.csv`, `interactions_clean.csv`, `interaction_delta.csv`, and `report.json` under the published incremental-curation contract from the `f99fd22` baseline. It must preserve directed interactions and identify molecules by RDKit canonical isomeric SMILES.
2. The C++20 `bridge-index` engine supports keyed undirected multigraph updates and queries under the frozen temporal-bridge contract from `6bcf942`: exact connected components, per-key bridges, and two-edge blocks even with replacements, retractions, self-loops, and parallel evidence.
3. The `ddi-release-audit` launcher stages curator output, maps each distinct canonical SMILES to a vertex in lexical SMILES order, maps every final directed clean interaction row to its own undirected physical evidence key (its one-based CSV data-row index), then queries the bridge engine. It publishes an immutable generation and moves `CURRENT` only after all files and SHA-256 manifest entries are validated. A fatal input or graph failure must leave the prior `CURRENT` and generation bytes unchanged.

The graph is undirected only for robustness analysis; opposite directed DDI rows remain distinct physical evidence keys, hence they form parallel edges. This conversion is explicit in the task, not inferred from a hidden test. A corrected drug alias can change representative IDs without changing the molecule vertex identity. A deleted drug or event can remove final edges and change bridge status.

### New integration outputs

Inside `/output/generations/<generation_sha>/`, retain the four curator files and add:

- `molecule_audit.csv`: `canonical_smiles,cc_min_smiles,cc_size,block_min_smiles,block_size,cc_count,bridge_count,block_count`; one row per final canonical molecule in lexical SMILES order. Minima are lexical canonical SMILES, not raw IDs or vertex numbers.
- `bridge_evidence.csv`: `evidence_index,d1,type,d2`; only final clean interaction rows whose own physical key is a bridge, sorted by numeric evidence index. A reverse-direction or otherwise parallel edge prevents either individual key from being a bridge.
- `manifest.json`: exact-byte lowercase SHA-256 for the six CSVs and curator report, plus generation identity computed from those hashes. `CURRENT` is a single generation ID and LF. No partial generation may be advertised.

The first prototype may use a smaller, explicitly bounded integration workload. The final task must state any throughput bound and must verify the author oracle against it without a model-timeout shortcut.

## Independent scoring standard (draft)

Score is additive; there is no cap. Tests are fixed before the first new blind answer. Full curator functionality contributes 0.40; full temporal bridge functionality contributes 0.40; cross-module release semantics, provenance and failure safety contribute 0.20. Within those three groups, each public behavior gets independently documented checks, including all baseline rejection reasons, ordered changes, semantic delta, bridges/blocks, raw reclassification, alias-stable vertex mapping, directed-to-parallel conversion, generation hashes, and failure non-clobbering.

Expected curation results must be established by hand-sized fixtures and pinned full-data conservation counts, not only by running the reference program. Small graph expectations must come from individual-key deletion and BFS; large graph expectations from separate analytic formulas. Integration expectations must be computed by reading the curator's *candidate* clean files and independently checking their semantic content before calculating the graph standard; the grader must not silently accept a jointly wrong curator/graph pair. It must also compare independent end-to-end fixtures whose exact output is pinned before any blind answer.

Oracle must score 1.000 and NOP 0.000 under Harbor 0.5.0 in the final container. Deliberately incomplete implementations (curator-only, bridge-only, reversing directed pairs, collapsing parallel evidence, and moving CURRENT before validation) must fail their corresponding groups. Verifier errors, OOM, and timeouts are infrastructure results, not evidence of difficulty.

The local difficulty gate remains: two independent fresh first answers on one immutable candidate-only package, each normally completed within the documented agent budget and each reward <= 0.700. Do not select the lower of repeated answers, change weights after seeing an answer, or infer the formal TalentsAI T1 from local probes. If both pass, then consider replacing the personal/platform task after separate R1/Oracle/NOP checks; the user owns final submission.

## Work order

1. Create the candidate environment and separate hidden references by mechanically copying the two already validated task components. Check that neither solution nor hidden test files are in the environment or candidate ZIP.
2. Write the small end-to-end fixtures and exact expected outputs first; implement integration reference and broken starter against that public contract.
3. Compose the scorer and task runner, run independent negative controls, then serial Harbor Oracle/NOP. Freeze file hashes and a candidate-only package.
4. Run two genuinely isolated blind first answers and grade them once, serially. If either is >0.700, diagnose the specific complete behaviors and redesign a substantive business component; do not alter the frozen version.

The original three CSVs remain unchanged. The published personal `main` and platform repository are not modified while this prototype is being tested.
