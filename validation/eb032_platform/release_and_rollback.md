# EB032-MATH-K v04 release and rollback

Registered task is mathematics/eb032-math-k-exact-certificate. Current version is v04. Publication requires complete normal production controls with Oracle 1.000 and NOP at most 0.100. payload.json binds the source and evidence/current records actual executions. Candidate-model qualification remains pending formal evaluation.

## Applying

Use the pinned-commit installer supplied with this release. It verifies a known prior case hash, backs up affected task paths beside the platform project, applies known release bytes, runs preflight and stages the affected paths. verify_release.py checks the installed manifest hashes, versioned results and Oracle/NOP acceptance.

## Recovery

The prior v03 release is 1a0656adf933a754c14290c2ecd7a0e2515c8820. It has a valid general Oracle and a formal T1 score of 0.750. Per-application backup ZIPs preserve prior file bytes. Inspect the actual platform application commit before creating a Git revert. All previous receipts and task versions remain recoverable in Git and local archives.
