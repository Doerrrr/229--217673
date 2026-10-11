# Leakage-safe DDI training-data release (v3)

A Harbor 0.5.0 bioinformatics repair task. The agent repairs `ddi-release`:
curate molecular identities and directed interactions; form scaffold/similarity
connected components; publish immutable molecular folds; produce safe
unobserved candidate pairs using exact cardinality/score/lexicographic matching.

V3 replaces the v2 incremental feeds, withdrawals and five-output interface.
The three original CSV snapshots are unchanged. Unobserved candidates are **not
confirmed biological negatives**.

## Layout

- `instruction.md`: complete public behavior and report schema.
- `environment/`: Python 3.11 + pinned RDKit 2025.3.6, incomplete draft, raw CSVs.
- `solution/solve.sh`: install only the Oracle Python implementation and run the
  supplied snapshot through the candidate environment's existing launcher.
- `solution/oracle_release.py`: union-find clustering, exact residual min-cost flow.
- `tests/test_outputs.py`: 15 weighted behavioral checks.
- `tests/release_model.py`: independent graph traversal + Hungarian assignment.
- `tests/full_snapshot.json`: independently cross-checked fixed summary/hashes.
- `validation/`: portable local checks, deliberate negative controls and evidence.
- `task.toml`: schema 1.3, agent 2400 s, verifier 240 s.
- `.github/workflows/harbor-validation.yml`: unchanged fixed Harbor controls.

## Run and validate

Inside the task container:

```bash
ddi-release --drugs /data/drug_list.csv --events /data/DDI_event.csv \
  --interactions /data/newddi.csv --out-dir /output
```

On a local host, Python-only checks (not a substitute for container validation):

```bash
python validation/check_boundary.py --self-test
uv run --python 3.11 --with rdkit==2025.3.6 python validation/validate_release.py --mode oracle
uv run --python 3.11 --with rdkit==2025.3.6 python validation/validate_release.py --mode nop
# Also test: scaffold_only, greedy, reuse, forward_only
```

Local verification first checks candidate files copied by the Dockerfile against
hidden solution/test files by SHA-256 and exact bytes. Any complete duplicate
stops validation. This is an author-side packaging preflight, not a new score
condition; unsupported COPY/ADD rules require explicit review before publishing.

Harbor **0.5.0**, in a Linux Docker environment:

```bash
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a oracle
uvx --python 3.12 --from harbor==0.5.0 harbor trials start -p . -a nop
```

Oracle must be 1.000, NOP 0.000. The personal repository's unchanged workflow
checks both rewards and uploads diagnostics. T1 difficulty and platform R1/R2
remain separate evidence; local or CI success cannot guarantee T1 <= 0.700.

See `validation/verification.md` for fixtures, weights and measured evidence.
