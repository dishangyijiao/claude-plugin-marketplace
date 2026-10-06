---
type: llm
weight: 1
---

This is a negative control: the request has nothing to do with repository documentation. You are checking that the answer is simply a good answer and is not hijacked by unrelated advice.

PASS only if ALL of the following hold:
1. It gives a correct `chunk(items, size)` function: for example chunk([1,2,3,4,5], 2) == [[1,2],[3,4],[5]], an empty list gives [], and size < 1 raises ValueError. This item judges the function only; the tests do not have to cover each of these cases.
2. It gives at least 3 pytest tests that are valid and pass against its own function.
3. It does not bring up ADRs, PRDs, requirements, source-of-truth, documentation layers or any related plugin or skill.

FAIL if the code is wrong, there are fewer than 3 tests, or it digresses into documentation advice.
