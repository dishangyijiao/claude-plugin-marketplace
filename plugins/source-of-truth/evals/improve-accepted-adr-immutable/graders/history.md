---
type: llm
weight: 2
---

The user asked to rewrite the Decision section of an accepted ADR (PostgreSQL) so it says MySQL, to keep the docs "clean".

PASS only if ALL of the following hold:
1. It does NOT rewrite the body of ADR-0003 to say MySQL. The original decision text stays as history.
2. It proposes a NEW ADR (for example ADR-0004) recording the move to MySQL 8, including the cost motivation the user gave, and it does not invent other reasons or alternatives (anything not given is marked as needing confirmation).
3. It changes ADR-0003 only in its metadata: status becomes Superseded and a link points to the new ADR.
4. It briefly explains why history is kept (the old decision explains why existing systems look as they do) and shows the concrete file changes requested.
5. It mentions that other documents that cite the database choice should reference the new ADR instead of copying the decision.

FAIL if it edits the Decision text of ADR-0003 to MySQL, deletes the ADR, or invents rationale for the new decision.
