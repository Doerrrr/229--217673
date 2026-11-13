# EB032-MATH-K v03 release and rollback

Registered identity is mathematics/eb032-math-k-exact-certificate. Public title is EB032-MATH-K. Current version is v03. Publication requires Oracle 1.000 and NOP at most 0.100 with normal production runs. The authoritative payload is payload.json and current execution evidence is evidence/current. Historical platform R1 93.67 and R2 81.83 apply to the earlier reviewed package. The old local difficulty result 0.310714 also belongs to v01.

## Publishing

Freeze source before validation. Preserve exact inputs, raw test.sh stdout/stderr, measurements and result.json. The provenance source digest must agree with the frozen grader. Keep current mathematical-instance hash, dependency lock and Docker image digest in the release receipt. Verify the published Git archive bytes against the repair manifest before supplying the sync command.

The public image copies app, bin, packet and the dependency lock from packet. The general reference and private scoring files stay outside this image. Existing isolated reader and checker boundaries remain active.

## Applying

Use the pinned-commit backup installer provided with the release. It accepts the original known source and previously published repair bytes, verifies the unchanged mathematical case digest, backs up changed paths, applies known files, runs preflight and stages the applied paths. Review the staged summary and use the platform submission workflow.

## Rollback

The namespace-v2 recovery commit is ca3d88f8f60a2576f5d69c31e2202a4d2e076311. The superseded v02 commit is 0443d0d0cc1c65b6aecfb4e27dd5b40492a288c8. Per-application backup ZIPs are written beside the platform project. Inspect the actual platform application commit before creating a Git revert. Preserve source inputs and all prior receipts during rollback. Model evaluations need a fresh version binding after any scoring revision.
