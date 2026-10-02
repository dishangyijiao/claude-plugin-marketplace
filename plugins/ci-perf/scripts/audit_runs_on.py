#!/usr/bin/env python3
"""List which workflow jobs run on GitHub-hosted runners (they bill hosted minutes).

    audit_runs_on.py [REPO_DIR]        # defaults to the current directory

Static and read-only: it only reads `.github/workflows/*.yml`. Nothing is guessed:
  github-hosted  runs-on names an ubuntu/windows/macos image
  self-hosted    runs-on mentions self-hosted or a runner group
  dynamic        runs-on is an expression (e.g. a matrix) - check by hand
  reusable       the job calls another workflow; the runner is decided there

Limits (it is a line-based reader, not a YAML parser, to stay dependency-free):
  * it follows the indentation actually used in each file (2 or 4 spaces, ...),
  * it supports block-style `jobs:` mappings only; flow style (`jobs: {a: {...}}`)
    is reported as "parsed 0 jobs" instead of being silently skipped.

Only runs that actually execute a job are billed: jobs skipped by an `if:` cost
nothing, and every job is rounded up to a full minute. Frequency matters more than
the label - a hosted job on every pull request costs far more than one that only
runs on release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HOSTED = re.compile(r"\b(ubuntu|windows|macos)[-\w.]*\b", re.I)


def _kind(value: str) -> str:
    if "${{" in value:
        return "dynamic"
    if "self-hosted" in value or re.search(r"\bgroup\b", value):
        return "self-hosted"
    if HOSTED.search(value):
        return "github-hosted"
    return "dynamic"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skippable(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def classify_workflow(text: str):
    """Return [{'job', 'kind', 'value'}] for every job of one workflow file."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    rows = []
    in_jobs = False
    job_indent = None   # indentation of the job keys, learned from the first job
    prop_indent = None  # indentation of a job's own properties (runs-on, uses, ...)
    for idx, line in enumerate(lines):
        if not in_jobs:
            in_jobs = bool(re.match(r"^jobs:\s*(#.*)?$", line))
            continue
        if _skippable(line):
            continue
        indent = _indent(line)
        if indent == 0:  # next top-level key: the jobs section is over
            break
        if job_indent is None:
            job_indent = indent
        if indent == job_indent:
            match = re.match(r"^\s*([A-Za-z0-9_-]+):\s*(#.*)?$", line)
            if match:
                rows.append({"job": match.group(1), "kind": "dynamic", "value": ""})
                prop_indent = None
            continue
        if not rows or indent < job_indent:
            continue
        if prop_indent is None:
            prop_indent = indent
        if indent != prop_indent:
            continue  # nested deeper (a step's env, a matrix, ...): not the job's own runner
        body = line.strip()
        if body.startswith("uses:"):
            rows[-1].update(kind="reusable", value=body.split("uses:", 1)[1].strip())
        elif body.startswith("runs-on:"):
            value = body.split("runs-on:", 1)[1].strip()
            if not value or value.startswith("#"):  # block form: the more-indented lines that follow
                block = []
                for nxt in lines[idx + 1 :]:
                    if _skippable(nxt):
                        continue
                    if _indent(nxt) > prop_indent:
                        block.append(nxt.strip())
                    else:
                        break
                value = " ".join(block)
            rows[-1].update(kind=_kind(value), value=value)
    return rows


def workflow_files(repo_dir: Path):
    return sorted((Path(repo_dir) / ".github" / "workflows").glob("*.y*ml"))


def audit_directory(repo_dir: Path):
    rows = []
    for path in workflow_files(repo_dir):
        for row in classify_workflow(path.read_text()):
            rows.append({"file": path.name, **row})
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(argv[0]) if argv else Path.cwd()
    files = workflow_files(repo)
    if not files:
        print(f"no workflow files found under {repo}/.github/workflows")
        return 1
    rows = audit_directory(repo)
    if not rows:
        print(
            f"found {len(files)} workflow file(s) but parsed 0 jobs - "
            "only block-style `jobs:` mappings are supported; read them by hand"
        )
        return 2
    for row in rows:
        print(f"{row['file']:28s} {row['job']:28s} {row['kind']:14s} {row['value'][:60]}")
    hosted = [r for r in rows if r["kind"] == "github-hosted"]
    print(f"\n{len(hosted)} of {len(rows)} jobs use GitHub-hosted runners (ask: how often does each run?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
