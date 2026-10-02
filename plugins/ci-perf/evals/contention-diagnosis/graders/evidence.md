---
type: llm
weight: 1
---

You are grading how well the answer separates evidence from guesses.

PASS only if the answer BOTH:
1. cites specific numbers from the table the user provided (for example 522s alone versus roughly 1000 to 1400s with neighbours) rather than speaking in generalities, AND
2. is honest about uncertainty: it distinguishes what the data shows (the job slows down when neighbours run) from what is an inference (the cause is shared CPU or IO contention), or suggests a way to confirm the inference (for example comparing before and after a capacity change on real CI, or checking host CPU steal and load).

FAIL if it states the cause as certain with no mention that it is inferred or how to confirm it, or if it gives no numbers.
