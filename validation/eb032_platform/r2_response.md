# EB032-MATH-K v05 reference stabilization

Question 242247 uses mathematics/eb032-math-k-exact-certificate. The reviewer independently reran v04 in two clean environments and reported rewards 0.8119 and 0.8333, with eb014, eb015, eb017 and eb018 returning INCUMBENT. These are reviewer-reported results. The earlier local v04 1.000 receipt remains historical and does not establish cross-hardware stability.

## Diagnosis

All six singular fixtures have one exact global minimizer, so the list of other equal minimizers is naturally empty. The v04 reference limited the first certificate attempt to 30 seconds and conditioned the next attempt on a nonempty tie list. A numerical or exact-recovery failure therefore ended the search even when substantial query time remained. The outer exception handler discarded recovery errors. A one-second author counterexample reproduced INCUMBENT on the four reported fixtures with zero ties. Existing numerical-library warnings do not identify the failed recovery stage.

## Stabilization

The reference now uses one absolute query deadline, reserves output time, and shares the available time across independent CLARABEL and SCS certificate attempts. The first attempt receives 65 percent of the remaining time, without the fixed 30-second ceiling. A failed attempt always permits the second attempt while time remains, including an empty or unsuccessful tie search. Solver time limits leave budget for exact rational recovery. Numerical rank estimates are refined first; every incompatible low-rank refinement has a bounded subdeadline. A subdeadline exhaustion permits another rank while the shared deadline remains.

Every accepted matrix still passes the exact Boolean polynomial identity, rational PSD and rational-output length checks. INCUMBENT emits structured stderr diagnostics containing query ID, method, attempt, budget, elapsed and remaining time, and exception or recovery-failure reason. Individual failed attempts are also diagnosed when a later attempt succeeds.

## Verification

Release requires two fresh isolated runs of the production tests/test.sh with 2-vCPU and 2048-MiB limits, normal exit, Oracle 1.000 and 82/82 checks in each run. Both runs retain the six actual singular JSONL outputs and independent exact-check results. The host CPU, image digest, dependency versions and source digest accompany the receipts. The reviewer host CPU is unknown.

Non-scoring CLI controls run every singular fixture at its normal budget, at a deliberately shortened one-second budget with natural zero ties, and with an explicitly identified first-attempt timeout injection plus forced empty ties. The short-budget controls must retain INCUMBENT counterexamples for eb014, eb015, eb017 and eb018 with useful diagnostics. The injected controls require all six second attempts to return CERTIFIED. Fault injection is separate from genuine elapsed-budget counterexamples.

The 18 mathematical case objects, scoring responsibilities, five weights, 300-second CLI limit, 14400-second agent limit and 18000-second verifier limit are preserved from v04. common.py only changes the result version tag to v05. Formal candidate-model T1 and R1/R2 require new platform receipts.
