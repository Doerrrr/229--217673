# DDI evidence lineage: rules-first standard

Status: new design and verifier development, not a released platform task.
The frozen ledger scores remain 1.000 / 1.000. This version has no blind score.
No local answer agent may be started: the user selected external-agent answers.

## Why this is a different task center

The ledger can be solved with a writer lock and an atomic snapshot file. Those
are valid solutions, so prohibiting them after seeing answers would be unfair.
The next center is exact symbolic analysis of shared evidence: one evidence
source can activate many directed DDI observations, so paths are correlated.
The command must describe all inclusion-minimal support sets compactly, count
them, retrieve ranked sets, and calculate exact conditional reliability and
source sensitivity. It must supply a checkable certificate, not an answer that
matches an author's chosen implementation.

The probability model is an explicitly defined research-data scenario. A path
in the evidence graph is NOT a proven biological DDI, and its source-activation
probability is NOT a clinical adverse-event probability. Do not claim either.

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

## Precommitment for the full external trial

Freeze the complete contract, runtime, operator verifier, fixtures and weights
BEFORE giving the public package to an external agent. Proposed 20 checks, .05
each, with no score cap: four directed/shared-evidence proof checks; five large
compressed-family checks; four minimal-family/rank checks; four exact
conditional-probability/sensitivity checks; three determinism/diagnostic checks.
Final fixtures and mappings must exist and pass checker quality controls before
freezing; this table is NOT a score for a partial prototype.

For each first external answer record actual displayed model/version, start and
freeze times, source ZIP hash and environment failures separately. The coding
budget remains 3600 seconds. Do not return scorer feedback before freezing the
two first answers. Use only the frozen verifier; retain high results. Local
acceptance still requires two eligible independent first answers each <=0.700;
the official platform has its own R1/Oracle/T1/R2 result.

## Independent quality controls and source basis

Hand-check independent paths (ab OR cd gives probability 7/16 at p=1/2), shared
paths (a AND (b OR c) gives 3/8, not 7/16), grounded and ungrounded cycles,
irrelevant variables, empty supports, impossible conditions, and 0/1 source
probabilities. For K serial stages, each with parallel sources a_i,b_i,
F=AND_i(a_i OR b_i): support_count=3^K, minimal_support_count=2^K,
all minimal sets have size K, probability=(3/4)^K, and each sensitivity is
(1/2)*(3/4)^(K-1). At K=40, neither worlds nor minimal sets may be enumerated.
These identities are derived independently, not copied from an author's run.

Reject deliberately wrong certificates/reports for ungrounded cycles, treating
shared sources as independent edges, minimum-size-only families, scalar floats,
conditioning zero-probability events, and enumeration-only stress solutions.
Do not claim these negative controls predict any model's score.

Author-only research basis: Bryant's fixed-order reduced decision diagrams
(https://www.cs.cmu.edu/~bryant/pubdir/ieeetc86.pdf) and exact probabilistic
inference via weighted decision diagrams (https://arxiv.org/abs/1610.05551).
These support the representation idea, not a claim that this new task will
lower T1 or that source reliability equals biological risk.
