---
type: llm
weight: 2
---

The user pasted a description of an existing repository and asked for a review against nine engineering layers (PRD, requirements, ADR, architecture, spec, code, tests, deploy, observe), without changing anything.

PASS only if ALL of the following hold:
1. It covers all nine layers (it may group some together) and gives each a verdict such as present, partial, missing or not applicable, with the evidence it relies on.
2. It identifies the three overlapping endpoint descriptions (README, docs/api.md, openapi.yaml) as duplicated or conflicting sources and proposes ONE canonical source, preferring the machine-readable contract; it notes the contract looks stale and must be derived from verified behavior rather than assumed.
3. It does not invent the reason Redis was chosen or the origin of the payment deadline; it marks them as unknown or needing confirmation.
4. It separates what it observed in the pasted description from what it infers.
5. It proposes a small first step (one reviewable change), not a repository-wide rewrite.
6. It does not claim to have created, edited or deleted any file, and it offers to hand the chosen gap on to an improvement step only after the user decides.

FAIL if it rewrites the repository layout wholesale, invents rationale, skips layers without saying why, or claims to have changed files.
