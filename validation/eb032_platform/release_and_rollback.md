# EB032-MATH-K v05 release and rollback

Question 242247 uses mathematics/eb032-math-k-exact-certificate. This revision retains v04 mathematical data and scoring and changes reference recovery, diagnostics and non-scoring author controls. Both isolated production Oracles must score exactly 1.000 before publication.

Apply the pinned release with the backup installer, inspect its compact staged summary and run verify_release.py. It verifies release file hashes, the result version, both production Oracles and all six singular certificates. Backup ZIPs are retained next to the target platform project. Known old task files are accepted and conflicting edits require review.

v04 source 44b02e8103bca7fc29ca6fbea9a4f0f901017707 and all earlier evidence remain recoverable in Git and archives. v04 has independently reported Oracle instability. Use the actual application commit and backup manifest when planning a rollback. Formal v05 platform qualification requires new receipts.
