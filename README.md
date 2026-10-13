# DDI-008: symbolic shared-evidence lineage

This Harbor 0.5.0 bioinformatics task asks the agent to repair `ddi-lineage`.
It analyzes directed research-observation paths whose edges can share evidence
sources. The release must contain canonical compressed certificates of logical
reachability and inclusion-minimal supports, exact counts/ranks, and exact
conditional rational probabilities and sensitivities.

This is a research-data model, not a clinical-risk predictor. Source activation
weights are task parameters, not adverse-event probabilities.

## Task layout

- `instruction.md`: the unchanged DDI-008 v01 public contract.
- `environment/`: Python 3.11 stdlib, damaged entry point, launcher and JSON inputs.
- `solution/solve.sh`: installs the hidden reference, then runs the public launcher.
- `solution/oracle_lineage.py`: the user-authorized external answer, unchanged.
- `tests/`: the unchanged independent certificate checker and 20 additive checks.
- `task.toml`: schema 1.3, networking enabled and original v01 runtime limits.

All 20 checks have weight 0.05. There is no score cap. The verifier runs candidate
commands as UID/GID 10001, while keeping tests and reward files inaccessible.
It checks supplied mathematical identities, not equality with reference outputs.
The Docker build never copies `solution/` or `tests/` into the candidate image.

Three legacy research CSVs are preserved unchanged; the current command reads
only the selected JSON input. The previous native C++ task's obsolete root
sources/tests were removed from this branch and remain recoverable in Git history.
The fixed GitHub Actions workflow was not edited.

## Evidence and limits

The supplied external answer scored 1.000 (20/20) under the original frozen local
verifier. This does not meet the desired <=0.700 local difficulty threshold and
is not a formal platform T1 score. Its notes report 62m49s, but the user clarified
that actual work took longer; exact elapsed time and budget compliance are not
established. The answer is now the hidden reference with explicit user consent.

Reference provenance and adapter boundary checks are in
`validation/symbolic_platform/`. Platform R1/Oracle/T1/R2 are not claimed passed
before an actual platform report. Use only the pinned, validated handoff commit.

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```
