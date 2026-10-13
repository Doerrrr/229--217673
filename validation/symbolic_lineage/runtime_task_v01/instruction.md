# DDI-008: shared-evidence lineage release

Repair ddi-lineage to analyze directed observation paths with shared evidence sources.
A source can activate multiple observations, so observations need not be independent.
Publish compact logical support certificates and exact research-data reliability metrics.
This is not a clinical-risk predictor: a graph path is not a proven biological DDI,
and the given activation weights are not adverse-event probabilities.

## Input and command

`ddi-lineage --input /data/evidence_graph.json --out-dir /output`

Repair the Python 3.11 entry point; the runtime provides its standard library.
No backend service or administrator privileges are needed. Input JSON has
exactly `version`, `nodes`, `sources`, `edges`, and `queries`; version is integer
1, not boolean. Reject malformed UTF-8/JSON, duplicate JSON keys, unknown or
missing fields, wrong scalar types and invalid references. IDs are ASCII
`[A-Za-z0-9_-]{1,32}` and unique within their respective collections.

- `nodes`: 1..160 distinct drug IDs.
- `sources`: 0..96 entries, each exactly `source_id,numerator,denominator`.
  Probabilities are independent BETWEEN source IDs; the same ID used on several
  edges is one shared Bernoulli variable, not independent edge trials.
  Numerator is an integer 0..denominator; denominator is integer 1..1000000.
- `edges`: 0..600 entries, each exactly `edge_id,d1,d2,type,source_id`.
  Endpoints and source must exist. `type` is an integer 0..2^63-1, not boolean.
  Parallel observations, reverse observations and self loops are legal.
- `queries`: 1..12 entries, each exactly
  `query_id,start,end,event_types,condition,ranks`. Endpoints must exist.
  `event_types` is a duplicate-free list of integers 0..2^63-1; empty means
  all event types, otherwise only listed types are included. `condition` is a
  list of entries exactly `source_id,value`, one per fixed source; value must be
  a JSON boolean. `ranks` is a duplicate-free list of 0..32 canonical unsigned
  decimal strings (at most 128 digits each), including `0` but not `00`.
  Ranks may exceed the family size.

Collection input order has no semantic effect. Source variables and node
columns use ASCII ascending ID order. Queries are output by ascending query ID.
An assignment activates an edge iff its source is true and its event type is
selected. A zero-edge path makes start==end reachable. Paths remain directed.

## Logical and probabilistic outputs

For a query, fix conditioned sources first. Let F be the Boolean function
"end is reachable from start" on the remaining free source variables. An
inclusion-minimal support is a set S of FREE sources for which F(S) is true
and F(S minus {s}) is false for every s in S. Inclusion-minimal does not mean
minimum cardinality. Unselected free variables are false when evaluating S.

Write `proof.json` and `report.json`, each canonical UTF-8 JSON: sorted object
keys, compact separators, no ASCII escaping, and exactly one trailing LF.
Validate inputs fully before replacing either old output. Create absent
output directories. Fatal errors are nonzero with nonempty stderr and preserve
the old output bytes. Required CLI arguments must not silently default.

`report.json` has exactly `version,proof_sha256,results`. The hash is SHA-256
of the exact proof bytes. Each query result has exactly:

- `query_id`;
- `support_count`: canonical decimal STRING counting ALL satisfying assignments
  to free sources, including irrelevant free sources;
- `minimal_support_count`: canonical decimal STRING;
- `min_size,max_size`: minimum/maximum minimal-support cardinalities, or null
  for an empty family;
- `ranked_supports`: entries `rank,sources`, in requested rank order. Sort each
  support's IDs; order supports lexicographically as ID lists, with a shorter
  prefix before its extension. Out-of-range ranks have sources=null.
- `critical_sources`: free sources present in EVERY minimal support; [] for
  an empty family. Conditioned-true sources are not free and do not appear.
- `probability_state`: `DEFINED` or `UNDEFINED`;
- `probability`: exact reduced fraction `numerator,denominator`, both decimal
  strings, or null when the condition has probability zero;
- `sensitivities`: a mapping for every FREE source, to the exact reduced fraction
  P(F|s=true)-P(F|s=false), keeping the query's other conditions. Do not divide
  by p(s) or 1-p(s): sources with probability 0 or 1 still have well-defined
  hypothetical sensitivity. If the original condition has probability zero,
  every sensitivity is null. Counts/support sets remain logical and defined.

## Certificate, not golden-answer comparison

`proof.json` has exactly `version,variables,nodes,queries`. `variables` is the
sorted source-ID list. `nodes` represents one shared reduced ordered BDD with
implicit terminals 0=false and 1=true, and at most 100000 nonterminal nodes.
Each nonterminal has exactly `id,var,low,high`; all are integers, not booleans.
IDs are contiguous from 2. Variable index increases strictly along edges;
children have lower node IDs; low!=high; triples (var,low,high) are unique.
Number nodes bottom-up by decreasing var, then increasing (low,high). Do not
use complemented-edge encodings. Include only nodes reachable from certificate
roots. Internal algorithms and their own IDs are otherwise unconstrained.

Each proof query has exactly `query_id,layers,root,minimal_root`. There are N
layers (k=0..N-1) with N columns in sorted node-ID order. The verifier checks:

    R_0(v) = true iff v == start
    R_k(v) = R_(k-1)(v) OR
             OR_(u -> v included) [R_(k-1)(u) AND activation(source)]

Activation is true/false for a conditioned source, otherwise its BDD variable.
The final target column equals `root`. The N-1 bound suffices even with cycles:
every reachable target has a simple path. This finite recurrence excludes
unsupported self-justifying cycles. The verifier checks every local identity;
it does not enumerate 2^96 worlds or import a candidate/reference solver.

`minimal_root` must represent exactly the characteristic function of minimal
support sets on the full source-bit vector. All conditioned source bits are
false in this encoding, even if their condition value was true. On free bits:

    M = F AND AND_s [NOT s OR NOT (F restricted to s=false)]

Also AND with NOT s for each conditioned source. The verifier checks this
identity, then derives counts, rank selections, criticality, probabilities and
sensitivities directly from the supplied verified diagram. It accepts any
algorithm that produces a valid canonical certificate.

The supported release fixtures have certificates within the stated node bound.
No test may select a graph whose required certificate exceeds that bound, or
an adversarial variable order that makes the promised limit unattainable.


## Runtime and deliverable

The environment provides Python 3.11 standard library, 2 CPUs and 4 GiB RAM.
Edit only environment/app/*.py (nested Python helpers are allowed). Do not change
the Dockerfile, launcher, task inputs or contract. No additional packages are required.
You may choose any internal algorithm that satisfies the public certificate rules.
A fresh output directory must work. Each valid command is allowed 120 seconds;
an invalid-input/CLI command is allowed 10 seconds for diagnosis.
Each output file and captured log may use at most 32 MiB; this exceeds the
maximum expected certificate size under the published bounds.
The overall coding budget is 3600 seconds, excluding separately recorded environment
setup failures. Do not modify host Docker/WSL services.

Read start_here.md, complete answer_notes.md, then run
`python pack_answer.py --out answer.zip`. Return the first frozen source ZIP and
actual model/version, elapsed time, tests run and omissions. Outputs alone are not
a code answer. Do not access unrelated projects, hidden evaluators or prior answers.

## Behavior checks

Twenty independently scored checks each carry 0.05, with no score cap.
Proof, support-family and probability checks verify their corresponding behavior
independently; an incorrect unrelated report metric does not erase proof credit.
Structural validity of the relevant supplied BDD is still required.

- independent_paths (proof): 0.05
- shared_source_paths (proof): 0.05
- grounded_cycles (proof): 0.05
- direction_and_event_filter (proof): 0.05
- compressed_80_source_family (family): 0.05
- shared_guard_large_family (family): 0.05
- conditioned_large_family (family): 0.05
- multi_query_large_family (family): 0.05
- rational_large_family (family): 0.05
- inclusion_not_minimum_size (family): 0.05
- lexicographic_ranks (family): 0.05
- irrelevant_source_dimensions (family): 0.05
- empty_and_unreachable_supports (family): 0.05
- exact_rational_probability (probability): 0.05
- conditional_shared_probability (probability): 0.05
- zero_probability_condition (probability): 0.05
- endpoint_hypothetical_sensitivity (probability): 0.05
- canonical_permutation_determinism (determinism): 0.05
- fatal_input_nonclobber (fatal): 0.05
- cli_and_new_output_directory (cli): 0.05
