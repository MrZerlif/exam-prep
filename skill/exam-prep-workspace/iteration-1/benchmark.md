# Skill Benchmark: exam-prep

**Model**: claude-sonnet-5
**Date**: 2026-09-15T00:43:06Z
**Evals**: 1, 2, 3, 4, 5 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 76% ± 19% | +0.24 |
| Time | 278.9s ± 148.2s | 128.3s ± 45.6s | +150.5s |
| Tokens | 104565 ± 26313 | 74721 ± 10110 | +29844 |

## Notes

- eval-3-resume-after-break: with_skill and without_skill BOTH scored 5/5 (100%) - a tie. The without_skill baseline independently discovered and correctly used the .exam-prep/ state files despite having no documented protocol for the format, producing behaviorally indistinguishable output from with_skill on every assertion in this case. This is the single largest 'small delta' finding in the whole audit and the most important one to not paper over.
- 21 of the 28 total assertions across all 5 evals (75%) passed in BOTH configurations - flagged non-discriminating by the grading agent, the eval author, or both. The skill's measured behavioral edge in this sample is concentrated in just 7 of 28 checks.
- The 7 assertions that actually discriminated with_skill from without_skill: reads-local-state, ticket-track-brief-structure-step, ticket-3-is-real-content (eval-1); reads-local-state, grounded-in-syllabus-target (eval-2); reaches-minted-structured-tickets (eval-4); durable-trace-left (eval-5). Nothing discriminated in eval-3.
- Two without_skill runs (eval-1, eval-2) explicitly declined to open the .exam-prep/ folder they discovered, citing no documented format for it, then guessed instead - that is what drove their lower pass rate, not an inherent inability to read the files. The other three without_skill runs (eval-3, eval-4, eval-5) DID open and use the same kind of state on their own initiative and scored much closer to with_skill as a result. The skill's real value in this sample looks more like 'reliably reads and uses local state every time' than 'a capability the baseline categorically lacks'.
- eval-4 (materials to minted tickets) is the clear cost outlier: with_skill used 141554 tokens / 477s / 53 tool calls vs without_skill's 77201 tokens / 186s / 12 tool calls - roughly 1.8x tokens, 2.6x time, 4.4x tool calls, for exactly one extra passing assertion (reaches-minted-structured-tickets) relative to without_skill's 4/5.
- eval-5 (mock exam and review) with_skill hit 4 real CLI errors, including a Windows-console Unicode crash printing the character '∫', while recovering; the without_skill run hit zero errors because it never shells out to the CLI at all.
- Time overhead is the most consistent signal: with_skill took longer on wall clock in all 5/5 evals, from 1.4x (eval-2: 160s vs 105s) to 2.6x (eval-4: 477s vs 186s) - never faster, never comparable.
- Token overhead is smaller and more mixed: with_skill used more tokens in 4 of 5 evals, ranging from about 1.2x (eval-2) to about 1.8x (eval-4). This benchmark ran only 1 sample per (eval, configuration) cell, so the +-stddev figures in run_summary reflect variability ACROSS the 5 different scenarios, not run-to-run flakiness within a single repeated scenario - genuine flakiness/variance was not measured in this pass and would need repeated sampling per cell to assess.
- A recurring, independently-rediscovered coping pattern (not a literal shared script, but the same fix applied from scratch each time) appeared in 3 of 5 with_skill runs (eval-3, eval-4, eval-5): the CLI's own Cyrillic JSON output renders as mojibake in the Windows console, so the model stops trusting the console text and re-reads the underlying .exam-prep/*.json file directly instead. This cost extra tool calls in all three, and escalated to a genuine crash-and-recover sequence in eval-5 (record-observation wrote valid UTF-8 data successfully but then crashed printing its own confirmation containing an integral sign, which the agent initially mistook for a failed write, requiring a follow-up idempotency check to confirm no data was lost). None of the without_skill runs hit this, since they never shell out through the CLI. This is a CLI stdout-encoding bug worth fixing once in scripts/, not something each conversation should have to work around.
- eval-3 shows the largest process-to-task-simplicity mismatch: for a one-line 'let's continue?' message, with_skill ran 13 tool-call steps (several re-confirming information `status` already returned in Step 1) for the same 5/5 outcome without_skill reached with about 10 direct file reads.
- eval-4's with_skill run spent roughly 6 tool calls reading raw Python source (capabilities.py, curriculum.py, source_provider.py) to reverse-engineer two undocumented validation mechanics not covered by commands.md or source-of-truth.md - a documentation gap rather than a pedagogy gap.
- verification.md / the `verify` CLI command was never invoked in any of the 5 with_skill runs, even though eval-2 and eval-5 both involve the tutor hand-grading calculus (integration by parts, a series-convergence test) with no cross-check - exactly the failure mode verification.md says the verifier exists to guard against.