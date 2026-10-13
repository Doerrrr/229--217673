# Joint DDI release: frozen local blind result

Date: 2026-10-13 UTC. This is a local experiment, not TalentsAI T1.

The frozen task digest was `eafe4c434c2902a8fb45c6e164ae11b836d0387e0bf2751240bff11e6788c053` (author commit `6b3f557371d4ce100ba2ae9d0890386fa930fb4c`). The root-level submission branch `submission/ddi-joint-release-20261013` points to `c468db8de9e6a6c4f5ea04cda7d40e05ba6a14a2`, whose task tree equals the frozen source tree. The public candidate package SHA-256 is `b514254959a8f5a0292ab457e1383f50d0dc62a65224ced6c283c8f7f68fad49`.

Control runs against the same private evaluator completed normally: Oracle 1.000 and NOP 0.000, both verifier exit 0 and no OOM.

Two independent candidates received separate copies of only the public package and were instructed not to inspect the private evaluator or prior answers. Their notes self-report following that boundary; the shared host filesystem did not technically prevent access, so this is a procedural rather than a sandbox-enforced isolation claim. Both frozen first answers completed before either was scored. Exact backend model ID was not exposed; the second candidate self-reported GPT-6 family. These are not the platform's DeepSeek/GLM agents.

| Candidate | Answer SHA-256 | Coding time | Local reward | Missed checks |
| --- | --- | ---: | ---: | --- |
| 1 | `8816e38136d1c36339de28021869b48347eebb61a79bf2e55765d6d46be92b8b` | about 8 min | 0.940 | `curator/failure_no_clobber`, `curator/bad_changes_no_clobber` |
| 2 | `771fb42760cd8d84df9b51b45edaec2872584bac48d1a12996eeb00f683f157b` | about 14 min | 0.928 | `curator/basic_parsing`, `curator/failure_no_clobber`, `curator/bad_changes_no_clobber` |

Both scoring containers exited 0 without OOM and completed all 24 checks. The two answer ZIPs have different hashes. The local target was two independent normal scores at or below 0.700, so this version **does not meet the target**. The high scores are evidence against the hypothesis that joining these three already-solvable modules suffices. Do not infer the formal platform T1 from these local results, and do not adjust frozen weights after seeing answers.

Evidence: `deliverables/ddi_joint_20261013/frozen_r1/checksums.json`, `score_oracle/result.json`, `score_nop/result.json`, `score_blind_first/result.json`, `score_blind_second/result.json`, and each candidate's `answer_notes.md` under `blind_exams/joint_20261013/`.
