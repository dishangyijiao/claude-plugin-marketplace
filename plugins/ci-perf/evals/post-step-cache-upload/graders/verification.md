---
type: llm
weight: 1
---

You are grading whether the answer says how to verify the fix with evidence.

PASS only if the answer BOTH:
1. says to compare step timings before and after on a run where the lockfile changed (the previously slow case), looking at the Post step and the install step, AND
2. notes that the first run on a given runner starts with an empty local store, so the warm-store benefit only shows on a later run on the same runner (or equivalent: it must not claim the gain from a single run).

FAIL if it just asserts the fix will work with no way to check, or claims the benefit is visible on the first run.
