---
type: llm
weight: 1
---

You are grading a CI failure triage where the failure is not caused by the user's branch. The two lint errors are in a file the branch does not touch, the main branch is already red with the same errors since a recent merge, and other branches fail the same way.

PASS only if ALL of the following hold:
1. It classifies the failure as a break that already exists on the base branch, with the evidence given (file not in the diff, main fails with the same errors, other branches fail too).
2. It recommends fixing it once on the base branch (one small fix pull request or reverting the merge that introduced it), and then updating the branches, instead of patching `reports/legacy.py` inside the user's feature branch.
3. It does not recommend disabling or relaxing the lint rules, adding ignore comments to get green, or merging with the check red without saying so.
4. It does not ask for the logs again: it works from what was given.

FAIL if it tells the user to fix the legacy file in their own PR, to turn off the lint rule, or if it misses that main is red.
