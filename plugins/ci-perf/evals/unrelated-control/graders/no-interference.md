---
type: llm
weight: 1
---

This is a negative control: the request has nothing to do with CI. You are checking that the answer is simply a good answer to the request and is not hijacked by unrelated advice.

PASS only if ALL of the following hold:
1. It gives a Python function is_palindrome(s) that ignores case and all non-alphanumeric characters and is correct (for example "A man, a plan, a canal: Panama" is True and "race a car" is False; an empty string or only punctuation is True).
2. It gives at least 3 pytest tests.
3. It does not bring up CI performance, self-hosted runners, Docker volumes, flaky tests or any other CI topic, and does not mention a CI-related skill or plugin.

FAIL if the code is wrong, if there are fewer than 3 tests, or if it digresses into CI advice.
