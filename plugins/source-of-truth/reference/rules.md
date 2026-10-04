# Rules for migration and maintenance

## Rules

1. No big-bang rewrite. Move in small steps.
2. Do not rename or relocate mature framework directories without a concrete benefit.
3. Do not change runtime behavior unless the step explicitly requires it.
4. Do not invent missing product or architectural decisions. Mark them `Unknown`, `Needs confirmation` or `Historical rationale unavailable`. Never state a guess as fact; a candidate alternative that nobody recorded may appear only as a labelled hypothesis.
5. Do not duplicate canonical information. Prefer references over copied content.
6. Prefer executable truth over prose.
7. Keep accepted ADRs immutable except for metadata: status, `Superseded by`, links. A changed decision gets a new ADR.
8. Do not weaken or delete tests to make a step pass.
9. Derive a contract from verified behavior; never from assumptions.
10. Every step is independently reviewable, with one clear purpose.

## Order of work for an existing project

1. Review (read-only): inventory, canonical sources today, duplicates and conflicts, missing artifacts, high-risk areas.
2. Agent instructions and the sources table (where each fact lives).
3. Architecture overview from the existing implementation.
4. ADRs for important decisions that are currently implicit.
5. Requirements and specs for the highest-risk flows first (authentication, money, data migration, ownership, critical journeys).
6. Machine-readable contracts for external boundaries, with validation in CI.
7. Connect the highest-value requirements and specs to tests.
8. Deployment, rollback and recovery documentation where they apply.
9. Lightweight repository checks in CI: links valid, contracts valid, required files exist.

Repeat feature by feature. Skip any step whose layer is not applicable.

## Closing report for every step

The `review` skill changes nothing, so it has its own report; every skill that changes files closes with these six items.

- files changed
- source-of-truth impact (which canonical sources changed or were added)
- behavior impact (normally none)
- checks executed, with results
- unresolved uncertainty
- follow-up work

Never claim a step is done before the checks have run.

## Definition of done

A migration is not done because directories exist. For every applicable layer:

- **PRD**: major capabilities have product context, with unconfirmed statements marked.
- **Requirements**: important requirements are explicit, testable and have stable identifiers.
- **ADR**: major decisions have ADRs; replaced decisions stay visible; nothing is duplicated.
- **Architecture**: boundaries, major components, data flows and trust boundaries are documented.
- **Spec**: critical behavior, edge cases and state transitions are specified; external interfaces have validated contracts that the specs reference.
- **Code**: documentation does not restate code-level facts.
- **Tests**: high-risk behavior has meaningful automated verification, CI runs it, and requirement links are checked automatically.
- **Deploy**: desired runtime state is version controlled and reproducible; rollback is documented.
- **Observe**: failure detection and recovery are documented; actual state stays in telemetry.

The agent-instructions file connects the layers: it exists, defines the read order and verification rules, and lets an agent tell where a fact belongs before editing it.

Layers that are not applicable are recorded with a reason; that counts as done.
