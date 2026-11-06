---
type: llm
weight: 1
---

You are grading a CI failure triage. The PR changes only two documentation files. The failing test is unrelated to the change, passed on a re-run of the same commit, and has failed twice before on the main branch in the last 10 runs, each time passing on re-run. The test uses a real sleep and asserts a retry count.

PASS only if ALL of the following hold:
1. It classifies the failure as flaky / not caused by this PR, and gives the evidence: the PR does not touch code or tests, the same commit passed on re-run, and the same test failed on main before.
2. It does not tell the user to merge as if nothing happened without saying the flaky test is a known problem; it says the underlying test is unreliable and should be tracked (an issue, or the repeat-run approach), not just ignored.
3. It does not recommend skipping, deleting or loosening the test, or raising a timeout, as the fix for this PR.
4. It does not rewrite or "fix" the documentation files in response to the failure.
5. It is brief: a classification, the evidence, and the next action.

FAIL if it blames the documentation change, suggests skipping or weakening the test, or gives a long generic list of CI tips without a classification.
