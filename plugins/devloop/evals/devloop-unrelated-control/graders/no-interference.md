---
type: llm
weight: 1
---

This is a negative control: the request has nothing to do with resuming work or CI failures. You are checking that the answer is simply a good answer to the request and is not hijacked by unrelated advice.

PASS only if ALL of the following hold:
1. It gives a correct Python function flatten(nested) that flattens arbitrarily deep nested lists and keeps strings whole (for example flatten([1, [2, [3, "ab"]]]) returns [1, 2, 3, "ab"]; an empty list gives []).
2. It gives at least 3 pytest tests.
3. It does not bring up resuming a previous session, hand-off files, CI failures, triage or any other development-loop topic, and does not mention a plugin or skill by name.

FAIL if the code is wrong, if there are fewer than 3 tests, or if it digresses.
