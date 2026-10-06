---
max_turns: 6
allowed_tools: [Skill]
---

We have a requirements document and a Rust test suite, and no link between them. I want traceability from requirements to tests. I have pasted what exists; you cannot open files.

docs/requirements.md (excerpt):

```
REQ-001  Show the whole sentence, not a fragment.
         Acceptance: the full sentence is returned for any caption index.
REQ-002  Keep a sentence to practice.
         Acceptance: saving the same sentence twice returns the same card.
REQ-003  Read aloud and see which sounds were wrong.
         Acceptance: recordings of 0.2 to 30 seconds are accepted, others refused with a message;
         the result lists matched and expected counts; the recording can be played back.
```

src/server.rs tests (names only):

```
fn paste_returns_the_full_sentence_for_a_caption_index()
fn saving_the_same_sentence_twice_reuses_the_card()
fn a_recording_is_scored_and_can_be_played_back()
fn recordings_outside_the_duration_limits_are_refused()
fn the_health_endpoint_answers_ok()
fn json_error_bodies_have_a_message_field()
```

Please add the requirement IDs so I can trace them. Show me the exact changes you would make and anything else you would add. Do not touch any file.
