---
type: llm
weight: 2
---

You are grading whether the answer fixes the cause and not only the symptom.

PASS only if the answer BOTH:
1. explains why the volumes pile up: the postgres image declares a data volume, and the CI service container is removed after each job without its anonymous volume, so every job leaves one behind, AND
2. proposes a permanent prevention rather than only periodic cleanup: for example mounting a tmpfs (or any explicit mount) on the database data directory of the CI service container so Docker creates no anonymous volume, and/or adding a disk-usage alert so this is noticed before the disk is full.

FAIL if it only gives one-off deletion commands with no explanation of the cause or no prevention.
