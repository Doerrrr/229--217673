# EB032-MATH-K v02 quality revision

The registered task is mathematics/eb032-math-k-exact-certificate. Public ID is EB032-MATH-K. The original 18 mathematical cases and five group weights are preserved. Production scoring now has 72 checks and 53 CLI calls. Historical v01 model results require fresh platform evaluation for v02.

## Review changes

- solution/ now runs a general CP-SAT assignment search and numerical SDP discovery followed by exact rational identity and PSD validation. It reads no answer catalogue. A numerical status alone never produces CERTIFIED.
- The search may return INCUMBENT. The present reference solves all original assignments and the quadratic certificates. Fourth-degree and ill-conditioned certificates remain incomplete. Its measured partial score is reported honestly.
- Production multi-query checks use four different problems. Additional checks exercise 16 queries, 32 variables, 65 basis entries, 64-character IDs, and 80-character rational syntax.
- Three production output-write failures exercise a directory target, a read-only parent with old output, and a file used as a parent. Return status, stdout/stderr and preservation are checked.
- Author parser regressions additionally cover 32768 terms, 32769 rejection, and neighboring ID, coefficient and basis bounds. A 32768-term formatting fixture is outside the guaranteed finite-basis certificate family, so it is used as an author parser fixture.
- The complete observed dependency set is pinned in environment/packet/requirements.lock. Docker installs with --no-deps and runs pip check.
- Current results and source hashes are refreshed. Prior receipts remain in older Git commits and local preservation archives. Current formal platform R1/R2/T1 remain pending user resubmission.

## Resource rationale

Agent time remains five hours. Each CLI invocation retains the public 300-second protection. The verifier has an independent 18000-second total cap. Calls near every individual cap can exhaust the total budget. A total-time failure is an abnormal run with no valid difficulty reward. Actual control time and peak RSS are retained in receipts.

## Validation boundary

Local containers use CPU, memory, UID separation, no-new-privileges and network isolation. The platform mount and permission configuration must be verified through platform receipts. Local controls do not establish platform acceptance.
