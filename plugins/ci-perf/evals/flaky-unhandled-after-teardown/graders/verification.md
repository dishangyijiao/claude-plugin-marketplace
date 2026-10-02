---
type: llm
weight: 1
---

You are grading how the answer proposes to prove the fix works.

PASS only if the answer BOTH:
1. proposes a deterministic test that does not depend on real time, for example using fake timers to assert that no timer is left pending after unmount (and that two consecutive schedule calls leave only one), AND
2. proposes verifying on CI by repeating the exact test command many times and counting failures, and notes that because the failure is intermittent (about 1 in 4), a single green run proves little while many consecutive clean runs is strong evidence.

FAIL if it only says "run it again and see" or has no deterministic test.
