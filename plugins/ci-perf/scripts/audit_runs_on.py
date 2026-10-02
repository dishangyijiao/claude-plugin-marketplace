#!/usr/bin/env python3
"""List which workflow jobs run on GitHub-hosted runners (they bill hosted minutes).

    audit_runs_on.py [REPO_DIR]        # defaults to the current directory

Static and read-only: it only reads `.github/workflows/*.yml`. Nothing is guessed:
  github-hosted  runs-on names an ubuntu/windows/macos image
  self-hosted    runs-on mentions self-hosted or a runner group
  dynamic        runs-on is an expression (e.g. a matrix) - check by hand
  reusable       the job calls another workflow; the runner is decided there

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


def classify_workflow(text: str):
    """Return [{'job', 'kind', 'value'}] for every job of one workflow file."""
    lines = text.split("\n")
    rows = []
    in_jobs = False
    job = None
    for i, line in enumerate(lines):
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            job = match.group(1)
            rows.append({"job": job, "kind": "dynamic", "value": ""})
            continue
        if job is None:
            continue
        if re.match(r"^    uses:", line):
            rows[-1].update(kind="reusable", value=line.split("uses:", 1)[1].strip())
        elif re.match(r"^    runs-on:", line):
            value = line.split("runs-on:", 1)[1].strip()
            if not value:  # block form: look at the indented lines that follow
                block = []
                for nxt in lines[i + 1 :]:
                    if re.match(r"^      \S", nxt):
                        block.append(nxt.strip())
                    else:
                        break
                value = " ".join(block)
            rows[-1].update(kind=_kind(value), value=value)
    return rows


def audit_directory(repo_dir: Path):
    rows = []
    for path in sorted((Path(repo_dir) / ".github" / "workflows").glob("*.y*ml")):
        for row in classify_workflow(path.read_text()):
            rows.append({"file": path.name, **row})
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(argv[0]) if argv else Path.cwd()
    rows = audit_directory(repo)
    if not rows:
        print(f"no workflows found under {repo}/.github/workflows")
        return 1
    for row in rows:
        print(f"{row['file']:28s} {row['job']:28s} {row['kind']:14s} {row['value'][:60]}")
    hosted = [r for r in rows if r["kind"] == "github-hosted"]
    print(f"\n{len(hosted)} of {len(rows)} jobs use GitHub-hosted runners (ask: how often does each run?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
