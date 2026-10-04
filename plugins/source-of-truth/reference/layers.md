# The nine layers

A repository is the source of truth for a system's **intended** state. Runtime telemetry stays the source of truth for its **actual** state. The nine layers are lifecycle stages, not nine directories: put a layer where the project's own conventions already put it, and create a directory only when something real goes in it.

| # | Layer | Answers | Canonical source | Plane |
|---|---|---|---|---|
| 1 | PRD | Why are we building this, and for whom? | Product requirements document | Intent |
| 2 | Requirements | What must be true? | Requirement records with stable IDs and acceptance criteria | Intent |
| 3 | ADR | Why did we choose this technical approach? | Architecture decision records (immutable history) | Decision and design |
| 4 | Architecture | How is the system structured? | Architecture overview: boundaries, data flows, trust boundaries | Decision and design |
| 5 | Spec | How exactly should this behavior work? | Behavioral specs, plus machine-readable contracts (OpenAPI, schemas, events) | Contract |
| 6 | Code | How is it implemented? | The code itself | Implementation and verification |
| 7 | Tests | Does the implementation satisfy the intended behavior? | Automated tests, contract checks | Implementation and verification |
| 8 | Deploy | What should the runtime environment look like, and how is software delivered? | Infrastructure as code, deployment config, CI/CD | Operations |
| 9 | Observe | How do we detect failure and recover? | SLOs, alert rules, dashboards, runbooks | Operations |

Git history, reviews, CI, traceability links and the agent-instructions file (`AGENTS.md`) connect the planes.

## Applicability

Every layer gets a verdict in every review. A layer is in exactly one state:

- **required**: the project cannot be understood or operated safely without it (for example, an external API needs a contract).
- **optional**: useful, but the project works without it; add it when the cost is justified.
- **not applicable**: the layer does not exist for this project (for example, no deployment or telemetry for a tool that only runs on one person's machine). Record the state and the **reason** in the status table. Never create placeholder documents for a layer that is not applicable.

A layer can also be applicable but empty. Say so as a gap in the status table; do not fill it with generic text.

## Canonical sources and formats

Each fact has one canonical source; every other place references it instead of copying it.

| Kind of fact | Format | Why |
|---|---|---|
| Intent, rationale, decisions, human-readable behavior, runbooks | Markdown | Meant for human reasoning |
| HTTP API, events, data exchange | OpenAPI, JSON Schema, Protobuf | Machine-checkable boundary |
| Data shape | Migrations or a schema definition | Executable |
| Implementation | Code | Executable |
| Verification | Tests | Executable |
| Desired runtime state | Infrastructure as code, deployment config | Declarative |
| Actual runtime state | Metrics, logs, traces | Observed, never copied into the repository |

Prefer executable truth over prose. When a fact must live in two languages or files and cannot share a source, pin the copies to each other with a test.

## Evidence labels

In reviews and recovered documents, label each statement:

- **Observed**: you saw it in a file, a test or a command result. Name the file.
- **Inferred**: a judgment drawn from observations. Say what it rests on.
- **Unknown**: not recoverable from the repository. Mark it `Needs confirmation` or `Historical rationale unavailable`. Never fill it in.

## Traceability

Where it adds value, links should run PRD, requirement, ADR and architecture, spec, code, tests. From code upward it answers "why does this exist?"; from a requirement downward, "was it implemented and verified?". Add identifiers to tests that guard a requirement; do not tag trivial tests mechanically.
