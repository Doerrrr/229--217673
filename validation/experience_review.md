# EXP-DDI-PUBLICATION-20261012

Status: verified local counterexample; formal platform difficulty unknown.

Trigger: v4 platform `680418a` scored 0.900 after several solver-oriented revisions, while the best historical incremental version scored 0.770 / 0.580. User authorized retaining v4, restoring that version, developing a new draft and a blind candidate-only subagent.

Attempt: retain DDI cleaning/replay/semantic delta; add immutable-generation publication with CAS, no-lock reads, sealed-orphan retry, ancestor identity and process-failure boundaries. Declare all requirements and weights before blind scoring. Use barriers/callbacks and unprivileged worker execution with trusted parent expectations, drawing on the supplied concurrent-log and SQLite-recovery case reports.

Measured evidence: the fixed Harbor 0.5.0 workflow on personal `b5718e9` produced Oracle=1.0 and NOP=0.0 (run 38188634197). The unchanged verifier on an independent audit branch measured the completed blind answer at 0.9615 (run 38188878602). Both trial processes completed normally. Five publication groups necessarily passed by the additive-score bound; exact failed legacy check is unknown because the fixed artifact step uploaded no `.trials` files.

Consequence: correct reference/worker isolation and sophisticated recovery cases do not establish difficulty. This example is a success counterexample, not a basis to misgrade the answer. Publication byte handling is largely separable from chemical replay; another independent feature could again leave most credit easy to obtain. That structural explanation is an author inference, not evidence of DeepSeek internal reasoning.

Action: save current code and receipts in the personal repository; hold platform synchronization and detection. No weight manipulation, hidden requirement or runtime failure is used to claim improvement. The candidate source hashes are frozen in results.json. A later substantive redesign or target-model evidence is needed before another platform run.

Limits: one blind answer, not the two platform models; no OS-enforced filesystem sandbox around the coding agent; no independent mutant/control campaign completed for this draft; no formal R1/T1/R2 for it. WSL was left untouched at the user's request. These records are project-local; the shared experience library is not rewritten through an unsafe Windows shortcut.
