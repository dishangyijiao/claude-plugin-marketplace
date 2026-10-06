---
type: llm
weight: 2
---

The user asked for traceability from requirements to tests in a project that has a requirements document with acceptance criteria and a list of test names. Nothing may be changed; the assistant shows the changes.

PASS only if ALL of the following hold:
1. It tags only the tests that guard a stated acceptance criterion (the paste, save, recording and duration-limit tests), saying which criterion each guards, and leaves the unrelated tests (health endpoint, error body shape) untagged on purpose instead of tagging everything mechanically.
2. It adds an automated check that runs with the project's existing test suite (not a manual procedure) and that fails when the links rot. At minimum: every requirement ID cited in code or tests must exist in the requirements document.
3. The check, or a second one, also fails when a test that should carry its ID loses it, or when a named test is renamed or misspelled, so the link does not silently disappear.
4. It says which requirements or tests remain untagged and records that as a known gap, instead of claiming full traceability.
5. It does not claim to have changed files; it shows the exact changes it proposes.

FAIL if it tags every test, if it adds IDs with no automated check, if the only check would pass when the tags are deleted, or if it claims full traceability.
