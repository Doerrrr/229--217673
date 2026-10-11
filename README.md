# Resource-constrained, leakage-safe DDI experiment release (v4)

A Harbor 0.5.0 bioinformatics repair task. The agent repairs `ddi-release`
to curate molecular identities/directed interactions, create immutable chemical
folds and jointly select safe unobserved assays under finite shared stock,
once-only setup charges, budgets, candidate-cluster caps and event quotas.

Unobserved pairs are **not confirmed biological negatives**. Resource amounts
are synthetic task policy, not experimental claims. The three original CSVs
and fixed GitHub Actions workflow are unchanged. V3 expectations are preserved
in `validation/v3_full_snapshot.json`; V4 retains molecular/positive CSV hashes.

## Layout

- `instruction.md`: complete public contract, strict plan schema and report fields.
- `environment/`: Python 3.11, RDKit 2025.3.6, OR-Tools 9.14.6206,
  SciPy 1.15.3; incomplete executable draft, raw CSVs and screen_plan.json.
- `solution/solve.sh`: install reference Python modules; reuse candidate launcher.
- `solution/screen_optimizer.py`: staged integer CP-SAT optimization and audit.
- `tests/release_model.py`: independent chemical graph traversal.
- `tests/screen_model.py`: separately constructed SciPy MILP and tiny enumeration.
- `tests/test_outputs.py`: 15 weighted behavioral checks, unchanged six weights.
- `tests/full_snapshot.json`: V4 counts and exact CSV hashes.
- `validation/`: package preflight, 500 exhaustive comparisons, negative controls,
  measured evidence and user-controlled platform handoff.
- `task.toml`: schema 1.3, agent 2400 s, verifier 600 s.

## Run and validate

Inside the task container:

```bash
ddi-release --drugs /data/drug_list.csv --events /data/DDI_event.csv \
  --interactions /data/newddi.csv --screen-plan /data/screen_plan.json \
  --out-dir /output
```

Portable author checks (not a substitute for container controls):

```bash
python validation/check_boundary.py --self-test
python validation/check_release_assets.py
uv run --python 3.11 --with rdkit==2025.3.6 --with ortools==9.14.6206 --with scipy==1.15.3 python validation/check_optimizer.py
uv run --python 3.11 --with rdkit==2025.3.6 --with ortools==9.14.6206 --with scipy==1.15.3 python validation/validate_release.py --mode oracle
uv run --python 3.11 --with rdkit==2025.3.6 --with ortools==9.14.6206 --with scipy==1.15.3 python validation/validate_release.py --mode nop
# Negative controls: ignore_plan, clip, split_stock, per_assay_setup,
# ignore_min, float_lex; legacy chemical/safety controls remain available.
```

The author preflight compares candidate Docker COPY sources with hidden
solution/tests by SHA-256 and bytes, rejecting complete duplicate files.
It does not add a scored agent condition. No reference launcher is copied
into the candidate image; the reference script reuses the supplied entry point.

Both exact optimizers fix count, score and cost optima before fixing each target's
lexicographic choice. Tests retain independent credit for chemical folding,
positive partition and curation. There is no new global score cap.

Use the unchanged Harbor **0.5.0** workflow for Linux Docker Oracle/NOP:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```

Oracle must be 1.000, NOP 0.000. A final CI receipt is separate from local results.
R1/R2 and actual T1 scores still require one user-controlled platform detection.
See `validation/verification.md` and `validation/platform_handoff.md`.
