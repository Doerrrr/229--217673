# DDI-018 — Cross-batch observation release (platform v03-safety)

A Harbor 0.5.0 bioinformatics maintenance task. Repair the native C application
that aggregates VCF, BGZF VCF and BCF observations from multiple batches while
preserving sample identity, allele/genotype meaning, priority and provenance.
The supported workload includes one-to-four-ploid observations, repeated records
and bounded-memory streaming. The public protocol accepts equivalent ALT order;
there is no hidden byte-layout requirement.

## Files

- `instruction.md`: online task and delivery instructions.
- `environment/packet/`: public laboratory policy, consumer and sample inputs.
- `environment/src/`, `environment/Makefile`: initial native application.
- `environment/upstream/`: pinned build dependency.
- `solution/solve.sh`, `solution/src/`: hidden Oracle implementation.
- `tests/`: unchanged 33 business checks from DDI-018 v01, plus Harbor adapter.
- `validation/cohort_platform/`: provenance, preflight and platform handoff.
- `task.toml`: schema 1.3, internet enabled for the platform model route.

## Version boundary

Platform v02 adapts online delivery and changes the initial migration draft to
meet NOP admission. Business obligations and the five weights remain unchanged:
projection 0.45, priority 0.25, grouping 0.15, resources 0.10, completion 0.05.
The user-approved third external answer supplies the reference implementation,
with an author fix that releases large per-source decoding buffers.

Platform v03-safety changes only the verifier identity boundary: `rss_runner.c`
accepts UID/GID 10001 exclusively and uses literal identifiers in setgid/setuid,
which are statically within 0..65535. The five semantic scoring modules, public
contract, source/Oracle implementation and weights remain unchanged. Historical
v02 local validation remains recorded; v03 must obtain its own fixed CI receipt.

Original v01 answers scored 0.500, 0.400 and 0.950. They are historical external
evidence, **not** independent v02 answers or formal platform T1 scores. They and
their original frozen packages have been preserved outside this repository.

The three original research CSV files are preserved for historical continuity,
but are not copied into this task's image or used by its public input protocol.
The GitHub Actions workflow is unchanged. Final TalentsAI detection and submission
remain user-controlled; local or GitHub validation does not prove R1/T1/R2 pass.

## Container validation

Use the fixed workflow on `main`, or run Harbor 0.5.0 with:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle --trial-name oracle --trials-dir .trials/oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop --trial-name nop --trials-dir .trials/nop
```

Expected normal rewards: Oracle 1.000, NOP 0.000. A runtime exception or absent
reward is a validation failure, not evidence that a model failed the task.
