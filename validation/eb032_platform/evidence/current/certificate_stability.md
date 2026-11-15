# EB032-MATH-K v05 certificate stability evidence

Two fresh isolated production runs use the same frozen source and the declared 2-vCPU, 2048-MiB limits. The available host CPU is AMD Ryzen 7 5800H. Reviewer host CPU details were not supplied.

| Run | Reward | Checks | Seconds |
| --- | --- | --- | --- |
| 1 | 1.000 | 82/82 | 326.832 |
| 2 | 1.000 | 82/82 | 322.793 |

## Individual singular certificates

| Query | First run | Seconds | Second run | Seconds |
| --- | --- | --- | --- | --- |
| eb013 | CERTIFIED | 3.2443 | CERTIFIED | 3.1167 |
| eb014 | CERTIFIED | 15.3725 | CERTIFIED | 14.8320 |
| eb015 | CERTIFIED | 21.5084 | CERTIFIED | 20.8016 |
| eb016 | CERTIFIED | 1.7459 | CERTIFIED | 1.6722 |
| eb017 | CERTIFIED | 12.3215 | CERTIFIED | 11.7598 |
| eb018 | CERTIFIED | 20.0903 | CERTIFIED | 19.4551 |

Every recorded certificate passes the exact polynomial identity and rational PSD checker. Both raw output sets are retained under the production run directories.

## Actual shortened-budget CLI controls

| Query | Configured budget | Other exact minimizers | State | CLI elapsed seconds | Diagnostic |
| --- | --- | --- | --- | --- | --- |
| eb013 | 1 s | 0 | INCUMBENT | 1.2286 | certificate_incomplete |
| eb014 | 1 s | 0 | INCUMBENT | 1.2517 | certificate_incomplete |
| eb015 | 1 s | 0 | INCUMBENT | 1.2153 | certificate_incomplete |
| eb016 | 1 s | 0 | INCUMBENT | 1.2276 | certificate_incomplete |
| eb017 | 1 s | 0 | INCUMBENT | 1.2271 | certificate_incomplete |
| eb018 | 1 s | 0 | INCUMBENT | 1.2308 | certificate_incomplete |
| eb013 | 5 s | 0 | CERTIFIED | 3.1274 | certificate completed |
| eb014 | 5 s | 0 | INCUMBENT | 6.0329 | certificate_incomplete |
| eb015 | 5 s | 0 | INCUMBENT | 5.2265 | certificate_incomplete |
| eb016 | 5 s | 0 | CERTIFIED | 1.6710 | certificate completed |
| eb017 | 5 s | 0 | INCUMBENT | 6.2376 | certificate_incomplete |
| eb018 | 5 s | 0 | INCUMBENT | 5.0399 | certificate_incomplete |

The configured budget covers recovery scheduling. CLI elapsed measurements also include process startup and numerical-library initialization. Every five-second control completes within 30 seconds. These controls use no injected solver failure.

## Explicit first-attempt fault injection

A separate author-only wrapper throws TimeoutError on the first certificate call and forces the tie list to empty. All six singular fixtures require the actual second SCS call to return CERTIFIED and pass exact verification. The wrapper and markers are retained in the author regression source and stderr logs.

The v04 one-second counterexamples are retained separately. The reviewer-reported v04 rewards 0.8119 and 0.8333 are user-provided evidence. Both v05 production rewards above were measured locally. Formal platform T1/R1/R2 remain pending.
