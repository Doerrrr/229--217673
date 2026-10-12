# DDI curation repair task

This repository contains a bioinformatics coding task for Harbor 0.5.0. The agent repairs a broken drug-drug interaction (DDI) curation command and an immutable generation publisher. The six input CSV files remain unchanged. The task combines molecular identity, incremental replay and semantic differences with concurrent compare-and-swap publication, lock-free consistent reads, idempotent request identity and recovery after writer termination. Research interactions are not asserted to be clinical facts.

## Task layout

- `instruction.md`: agent-visible requirements.
- `environment/`: Docker build context, broken application, and input CSV files.
- `solution/solve.sh`: Oracle repair and full-data run.
- `tests/test.sh`: weighted verifier; writes `/logs/verifier/reward.txt`.
- `task.toml`: Harbor resource limits and task metadata.

## Validation

Validate the task with Harbor 0.5.0 in a Linux Docker environment and check both controls:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```

Expected rewards are Oracle `1.0` and NOP `0.0`. A local Windows check can exercise the Python curation and verifier logic, but the Harbor runs are required to validate the container, launcher, and mounted paths.

The verifier retains 14 curation checks, scaled to a total of 0.55, and adds five independent publication responsibilities totaling 0.45. It has no single-responsibility score cap. Candidate execution runs in unprivileged child processes; hidden expectations and reward writing remain in the trusted supervisor. Local control results and platform model scores are separate evidence.
