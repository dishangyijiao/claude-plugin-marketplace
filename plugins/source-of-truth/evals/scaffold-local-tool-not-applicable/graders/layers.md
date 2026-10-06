---
type: llm
weight: 2
---

A user starting a new personal command-line tool (runs only on their own laptop, no server, no other users) asked for a document in every one of nine layers, including deploy and observe, and asked what would be created and asked first, without creating anything.

PASS only if ALL of the following hold:
1. It asks about the product before writing anything about it (at least the problem and the goals or non-goals), instead of inventing a PRD.
2. It pushes back on the premise "every layer needs a document": for deploy and observe (and anything else that genuinely does not apply) it proposes recording them as not applicable WITH a reason, rather than creating empty placeholder documents.
3. It lists a concrete, small set of files for the layers that do apply (for example an agent-instructions file, a table of where each fact lives, a product document, a first decision record only if a decision was actually made) and explains each one briefly.
4. It does not create or claim to have created files.
5. It lets the user make the final call on what is skipped.

FAIL if it agrees to create placeholder documents for deploy and observe, invents product goals, or starts creating files.
