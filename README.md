# DDI curation repair task

This repository contains a bioinformatics coding task for Harbor 0.5.0. The agent repairs a broken drug-drug interaction (DDI) curation command. The supplied inputs are drug structures, event descriptions, and directed interactions from an existing research workspace. The task requires RDKit-based molecular identity, conflict quarantine, directed deduplication, deterministic output, and a failure-safe report.

## Task layout

- `instruction.md`: agent-visible requirements.
- `environment/`: Docker build context, broken application, and input CSV files.
- `solution/solve.sh`: Oracle repair and full-data run.
- `tests/test.sh`: weighted verifier; writes `/logs/verifier/reward.txt`.
- `task.toml`: Harbor resource limits and task metadata.

## Validation

The GitHub Actions workflow runs Harbor 0.5.0 in a Linux Docker environment and checks both controls:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```

Expected rewards are Oracle `1.0` and NOP `0.0`. A local Windows check can exercise the Python curation and verifier logic, but the Harbor runs are required to validate the container, launcher, and mounted paths.
