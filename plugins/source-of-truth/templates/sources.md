# Documentation and sources of truth

Principle: each fact has one source. Everywhere else references it and does not copy it. The repository records what the system should be; the runtime state is whatever the running system and its logs say.

## Where each fact lives

| Question | Source | State |
|---|---|---|
| Why build this, and for whom | __PRD_PATH__ | __STATE__ |
| Why a technical decision was made | __ADR_DIR__ | __STATE__ |
| The HTTP API (if any) | __CONTRACT_PATH__ | __STATE__ |
| Data shape | __MIGRATIONS_OR_SCHEMA_PATH__ | __STATE__ |
| Behavior of a feature | __SPEC_PATH__ | __STATE__ |
| How to install, run and test | `README.md` | Canonical |
| Rules for AI agents | `AGENTS.md` | Canonical |
| What a term means | __GLOSSARY_PATH__ | __STATE__ |

Remove rows that do not apply. A row exists only when its source exists.
