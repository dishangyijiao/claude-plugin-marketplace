---
max_turns: 6
allowed_tools: [Skill]
---

Please review this existing repository against the nine engineering layers (PRD, requirements, ADR, architecture, spec, code, tests, deploy, observe) and tell me what is missing or duplicated. I have pasted what is in it; you cannot open files.

```
README.md                      # 3 pages: setup, a list of REST endpoints with request/response examples, "why we use Redis"
docs/api.md                    # a second list of the same REST endpoints, slightly different field names
openapi.yaml                   # a third description of the endpoints; last changed 14 months ago
src/                           # Python service, about 40 modules
tests/                         # pytest; payment_reconciliation_test.py checks that paid orders are queued within 15 minutes
db/migrations/                 # 62 migrations
.github/workflows/ci.yml       # runs pytest and ruff
Dockerfile, helm/              # deployment; no rollback notes anywhere
```

README excerpt: "We use Redis because it is fast and everyone knows it." Nothing else in the repository records why Redis was chosen, who asked for the payment deadline, or what happens when reconciliation fails.

Give me the review. I have not decided yet whether to change anything, so please do not change anything.
