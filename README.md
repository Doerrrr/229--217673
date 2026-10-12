# Versioned DDI evidence library task

This is a Harbor 0.5.0 bioinformatics coding task. The agent repairs a C++20
library behind an existing Python client. The library maintains directed DDI
evidence as drug and event interpretations change. It must preserve immutable
snapshots, support savepoints and transaction rebase, publish one winner for a
same-base concurrent commit, and keep sparse version updates within the public
resource budget. Research interactions in the supplied data are not clinical
recommendations.

## Task files

- `instruction.md` specifies the public C ABI behavior, ownership, concurrency,
  error handling, and bounded workload.
- `environment/` contains the damaged C++ source, public header, client,
  Docker build files, and three original research CSV files.
- `solution/solve.sh` installs the Oracle implementation.
- `tests/test.sh` runs 18 additive behavior groups and writes the Harbor reward.
- `task.toml` declares the schema and execution limits.

The 18 group weights sum to 1.000. There is no score cap. The verifier runs
candidate code in an unprivileged child process while holding expectations in
the supervisor. Any implementation satisfying the public behavior is accepted.

## Validation status

The frozen task files were tested with Harbor 0.5.0 in Linux Docker. Serial
Oracle and NOP trials finished normally with rewards 1.000 and 0.000. A fresh
local blind answer also earned 1.000, so this task is **not** locally verified
to meet the desired T1 difficulty threshold. A TalentsAI platform run is a
separate experiment and must be interpreted from its own result.

Run the controls in a Linux Docker environment:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```

`validation/sync_native_release.sh` is the reviewed, pinned-commit handoff
for the platform Git workspace. It only transfers task paths; it checks the
platform workflow and original CSV bytes before committing.
