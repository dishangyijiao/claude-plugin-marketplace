---
type: llm
weight: 1
---

This is a functional smoke test of a plugin's bundled analysis script, not a judgement of advice quality. The task asked the agent to save the JSON as runs.json, analyse it with an existing tool (not by mental arithmetic), and paste the tool's report verbatim.

The plugin's script prints a report with these exact section headings:
  `== Jobs (queue = waiting for a runner, run = executing)`
  `== Time to required check 'gate' (PR event -> check done)`
and, for this data, these values: job `build` queue median 20s and run median 560s; job `gate` queue median 5s and run median 75s; time to required check `gate`: median 11.0 min.

PASS only if ALL of the following hold:
1. The answer contains a pasted report with BOTH exact section headings above (this proves the plugin's script actually ran and its output was pasted, rather than numbers computed or invented by hand).
2. The pasted report shows build run median 560s and a time to required check median of 11.0 min.
3. The final one-sentence conclusion is consistent with those numbers.

FAIL if the headings are missing or differ (for example a hand-written table or a differently formatted report), or if the numbers are wrong, or if the agent says it could not find or run the tool.
