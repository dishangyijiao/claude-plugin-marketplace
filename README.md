# claude-plugin-marketplace

English | [简体中文](README.zh-CN.md)

A personal Claude Code plugin marketplace. Every plugin is distilled from real engineering work and keeps **only generic methods and read-only tooling**.

## Plugin: `ci-perf`

A CI performance and reliability playbook for self-hosted GitHub Actions runners. Core principle: **measure before optimizing, audit read-only before touching anything, and don't draw conclusions without evidence.**

| Skill | When to use it |
|---|---|
| `ci-perf-investigation` | CI is slow, jobs queue for a long time, or you are optimizing performance: how to collect data, which four tables to read, which causes map to which symptoms, common misdiagnoses |
| `self-hosted-runner-health` | A self-hosted runner fails at random, the disk fills up, container volumes leak, caches are slow, or you want to know which jobs burn GitHub-hosted minutes |
| `flaky-test-hunt` | Tests fail intermittently, "all tests passed but the run failed", or you need to prove an intermittent failure is fixed |

> The skill bodies (`SKILL.md`) are written in Chinese; each `description` is bilingual (English and Chinese) so it triggers in either language. Claude follows the skills regardless of the language you talk to it in.

Bundled tools (standard library only, read-only):

```bash
# Collect data and print a report: queue vs. run time, slowest steps,
# time to required check (from the run's first job being created to the check completing),
# duration bucketed by concurrency. --steps and --heavy accept comma-separated job names.
python3 plugins/ci-perf/scripts/ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since 2026-09-01 --out runs.json
python3 plugins/ci-perf/scripts/ci_timing.py report runs.json --check "<required-check job>" --steps "<slowest job>" \
    --overlap-target "<heaviest job>" --heavy "<other heavy jobs, comma-separated>"

# Which jobs run on GitHub-hosted runners (and therefore burn hosted minutes)
python3 plugins/ci-perf/scripts/audit_runs_on.py <repo directory>
```

Templates (run them from a throwaway branch with `on: push`, then delete the branch):
- `plugins/ci-perf/skills/self-hosted-runner-health/templates/runner-readonly-audit.yml`: read-only audit of the runner host (disk, containers, volumes)
- `plugins/ci-perf/skills/flaky-test-hunt/templates/repeat-tests.yml`: run the tests N times and keep the full log of every round

## Plugin: `source-of-truth`

A playbook for keeping a repository the source of truth for a system's intended state, across nine engineering layers: PRD, requirements, ADR, architecture, spec, code, tests, deploy, observe. Core principles: **one canonical source per fact, executable truth over prose, never invent a missing decision, and a layer that does not apply is recorded with a reason instead of filled with placeholders.**

| Skill | When to use it |
|---|---|
| `source-of-truth:scaffold` | A new project: interview first, then create only the layers that apply, plus `AGENTS.md` and a table of where each fact lives |
| `source-of-truth:review` | An existing project: a read-only audit of the nine layers that finds missing, duplicated or conflicting sources and proposes one small first step |
| `source-of-truth:improve` | After a review: close one chosen gap (architecture overview, ADR, requirement, spec, contract, agent instructions) as one reviewable step, without changing behavior |

Bundled files: `reference/layers.md` (the layers, three applicability states, evidence labels), `reference/rules.md` (migration rules, order of work, definition of done), seven document templates in `templates/`, and a read-only, standard-library link checker:

```bash
python3 plugins/source-of-truth/scripts/check_markdown_links.py <repo directory>   # exit 0 ok, 1 broken links, 2 usage error
```

**Evaluation (one run, 2 runs per arm, 5 cases, about US$1.74):** the four functional cases scored 1.00 with the plugin and 1.00 without it, so **no benefit over the no-plugin baseline was measured**: the model already refuses to rewrite an accepted ADR, to invent a missing rationale, or to create placeholder documents for layers that do not apply. The unrelated control scored 0.50 with the plugin and 1.00 without: in the one failing run the code and tests were correct and nothing digressed, but it was the only answer without an empty-list test, and the rubric's wording about the empty list is ambiguous. That points at the rubric, not at interference, but the rubric has not been changed. What the plugin adds is consistency: the same templates, applicability states and checks each time, which these cases do not measure.

## Install

```bash
claude plugin marketplace add dishangyijiao/claude-plugin-marketplace
claude plugin install ci-perf@dishangyijiao-plugins
claude plugin install source-of-truth@dishangyijiao-plugins
```

Try it locally without installing: `claude --plugin-dir plugins/ci-perf` or `claude --plugin-dir plugins/source-of-truth`

## Development

```bash
python3 -m unittest discover -s tests     # script logic + manifests + privacy check + template read-only check
python3 tools/mutate.py plugins/ci-perf/scripts/audit_runs_on.py --tests tests.test_audit_runs_on tests.test_properties   # mutation test
claude plugin validate .                  # marketplace manifest
claude plugin validate plugins/ci-perf    # plugin manifest
claude plugin validate plugins/ci-perf/skills
claude plugin validate plugins/source-of-truth
claude plugin validate plugins/source-of-truth/skills
```

`tests/test_repo_hygiene.py` rejects internal IPs, tokens, keys, personal email addresses, project/host names, and any delete-style command in the audit templates. **Before adding anything to this repo, ask: is it generic, and is it read-only?**

## Evaluation (`claude plugin eval`)

`plugins/ci-perf/evals/` holds 6 cases. Each ships its own data (only the `Skill` tool is allowed: no file reads, no network), is scored by LLM grading rubrics, and automatically runs a **no-plugin baseline arm** for comparison.

```bash
claude plugin eval plugins/ci-perf --runs 2 -j 2 --trust-plugin --no-publish --max-cost-usd 4
```

- It spawns subprocesses with your own credentials; about 24 runs, 5 to 6 minutes, roughly US$2.4. `--no-publish` keeps the report local instead of publishing it to claude.ai.
- Use `--trust-plugin` only for plugins you wrote yourself. Results land in `evals*/results/` (excluded by `.gitignore`).

**The script case lives separately in `evals-extra/`.** `run-timing-script` makes the agent actually run a script from the plugin, which requires granting `Bash` and `Write`. It is kept out of the default suite so that a missing grant doesn't drag the score down. It is a **functional smoke test** (it checks that the script path is found after installation), **not a comparison against the baseline**: the baseline has no such script, so a score of 0 is expected.

```bash
claude plugin eval plugins/ci-perf --eval-dir evals-extra --allow-tools Bash Write --trust-plugin --no-publish --max-cost-usd 2
```

> It **does not run on my machine**: granting `Bash` triggers the sandbox security check, and `~/.docker` (the Docker credential store) contains symlinks, so the eval harness rejects the whole run. Instead I verified the two halves separately with a restricted non-interactive call: once the skill fires, `${CLAUDE_PLUGIN_ROOT}` expands to a real path, and the script's report on data written by the agent matches the reference answer. **The full chain has never run end to end in one go.**

> The results below were measured **before** the review fixes (examples, scope notes, safety notes added to the skills; the `time to required check` label and the contention case text changed). The suite has not been re-run since.

**Results** (2 runs per arm, grader model defaults to haiku; the sample is tiny, so treat them as hints only. These are from the latest run after slimming the skills; the numbers in parentheses are from before slimming):

| Case | With plugin | Without plugin | Reading |
|---|---|---|---|
| contention-diagnosis | 1.00 | 1.00 | The baseline already knows this → **no evidence of value** (still true after making the case harder) |
| disk-full-safe-cleanup | 1.00 | 1.00 | The baseline is already safe → **no evidence of value** (still true after removing the hints) |
| unproven-fix-honesty | 1.00 | 1.00 | The baseline resisted pressure to write "fixed" → **no evidence of value** |
| unrelated-control (negative control) | 1.00 | 1.00 | The plugin did not interfere with an unrelated task |
| flaky-unhandled-after-teardown | 0.83 (1.00) | 0.67 | The gap is in "verification method" (a deterministic fake-timer test plus repeated-run statistics). **The skill was not invoked in either run**, so the difference most likely comes from the always-on skill descriptions. Slimming shortened the descriptions and the gap fell from +0.33 to +0.17, but with n=2 **I can't tell slimming from noise** |
| post-step-cache-upload | 1.00 (1.00) | 0.67 (0.50) | The baseline varied between rounds (0.50 before slimming, 0.67 now), which is within noise at n=2. **Part of the with-plugin lift exists because I wrote the answer the rubric wants into the skill, so it is not independent evidence** |

Overall: 0.97 with the plugin, about 0.89 without, a mean gap of +0.08 (+0.14 before slimming). **Only "method" scenarios (verifying intermittent failures, cache saving and instance isolation) show a difference. For things the model already knows (don't add a runner to the same machine, check before deleting volumes, don't overstate an unproven fix), no value was measured.**

**Cost**: `claude plugin details` reports about 157 always-on tokens and roughly 0.4 to 0.6k per skill when it fires (about 1.5k if all three fire). The 312 / 425 / 5.7k / 3.9k figures from the earlier slimming round came from a different measurement that I could not reproduce, so only compare numbers from the same tool. The skills grew slightly after the review fixes (added examples and safety notes).

Known biases and gaps:
- The rubrics were written from the skill content ("the question author is the textbook author"). Multi-condition PASS rules are judged by a small model; for a final run, add `--judge-model` with a stronger model and spot-check by hand.
- Only 2 runs per arm, and the conclusions apply to this one model. As models improve, baseline scores will keep rising and these gaps may shrink.
- No rubric item checks whether the skill was invoked, so skill-trigger behavior is not part of the score.

## Safety notes

- Job names, step names and workflow files are written by whoever can edit a workflow, so they are untrusted. The scripts replace control, bidi-override, zero-width and line-separator characters before printing, `ci_timing.py` validates `--repo` and `--workflow` before calling `gh api`, `audit_runs_on.py` skips symlinked workflow files, and the skills tell the agent to treat such text as data.
- Both workflow templates are for **private repositories** and a runner you are willing to run the code on. Pushing them to a self-hosted runner needs the user's confirmation; the test and setup commands in `repeat-tests.yml` must come from the project owner, never from CI logs.
- The templates pin their GitHub Actions to commit SHAs, validate `__RUNS__` as an integer, and escape lines that start with `::` when echoing test output or directory names into the log.
- The skills do not set `allowed-tools`: in Claude Code that field pre-approves tools rather than restricting them.

## Releasing

1. Bump the version: change `version` in `plugins/ci-perf/.claude-plugin/plugin.json` and, if present, in the marketplace entry.
2. Run `claude plugin tag plugins/ci-perf` to create the `ci-perf--vX.Y.Z` tag (it checks that both versions match), then push the tag.

Current release: `ci-perf--v0.1.4`.

## Not done yet / known limitations

- See the evaluation section above: only some scenarios show a benefit, the rubrics have known biases and gaps, and the script case can't run under the eval harness on some machines.
- `ci_timing.py` fetches data through `gh api` (one request per run), paginating on demand and stopping once it has enough; it is still subject to API rate limits. The concurrency analysis only sees the jobs you collected; see the "工具局限" (tool limitations) section of `ci-perf-investigation`.
- `audit_runs_on.py` reads line by line rather than parsing YAML, and only supports block-style `jobs:`.
- The experience behind this comes from self-hosted runner + Docker + pnpm + pytest xdist setups. In other environments, treat it as a checklist rather than a conclusion.

## License

MIT, see `LICENSE`.
