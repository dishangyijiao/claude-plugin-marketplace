#!/usr/bin/env python3
"""Measure GitHub Actions timing: queue vs run, slow steps, time-to-check, contention.

Standard library only; talks to GitHub through the `gh` CLI (read-only API calls).

    ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since 2026-09-01 --out runs.json
    ci_timing.py report runs.json --check "quality gates" --steps "web" \
        --overlap-target "pytest" --heavy "pytest,web"

Why these views (each one answered a real question during a CI investigation):
  * queue vs run      - is the time spent waiting for a runner or doing work?
  * slow steps        - where inside the job the time goes (incl. Post steps)
  * time-to-check     - what a developer feels: PR event -> the required check done
  * overlap buckets   - does a job get slower when other heavy jobs run at the same
                        time on other runners? (the signature of CPU contention on
                        a shared host: same job, ~2-3x slower with 2+ neighbours)
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from statistics import median

FINISHED = {"success", "failure"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values, p):
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _seconds(start: str, end: str) -> float:
    return (parse_ts(end) - parse_ts(start)).total_seconds()


def _finished(job) -> bool:
    return bool(job.get("started_at") and job.get("completed_at") and job.get("conclusion") in FINISHED)


def job_stats(runs):
    """Per job name: count, failures, queue and run time (median/p90/max)."""
    groups: dict[str, list[dict]] = {}
    for run in runs:
        for job in run.get("jobs", []):
            if _finished(job):
                groups.setdefault(job["name"], []).append(job)
    stats = {}
    for name, jobs in groups.items():
        queue = [_seconds(j["created_at"], j["started_at"]) for j in jobs]
        run = [_seconds(j["started_at"], j["completed_at"]) for j in jobs]
        stats[name] = {
            "n": len(jobs),
            "failed": sum(1 for j in jobs if j["conclusion"] == "failure"),
            "queue_med": median(queue),
            "queue_p90": percentile(queue, 90),
            "run_med": median(run),
            "run_p90": percentile(run, 90),
            "run_max": max(run),
        }
    return stats


def step_stats(runs, job_name, top=10):
    """Slowest steps of one job: [(step name, median s, max s, n)], slowest first."""
    durations: dict[str, list[float]] = {}
    for run in runs:
        for job in run.get("jobs", []):
            if job["name"] != job_name:
                continue
            for s in job.get("steps", []):
                if s.get("started_at") and s.get("completed_at"):
                    durations.setdefault(s["name"], []).append(_seconds(s["started_at"], s["completed_at"]))
    rows = [(name, median(v), max(v), len(v)) for name, v in durations.items()]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:top]


def time_to_check(run, check_name):
    """Seconds from the run's first job being created to `check_name` completing."""
    jobs = run.get("jobs", [])
    # A skipped check (e.g. a draft pull request) has timestamps but no real duration.
    check = [j for j in jobs if j["name"] == check_name and _finished(j)]
    if not check:
        return None
    first = min(parse_ts(j["created_at"]) for j in jobs)
    return (parse_ts(check[0]["completed_at"]) - first).total_seconds()


def overlap_buckets(runs, heavy_names, target_name):
    """Run time of `target_name` jobs bucketed by how many OTHER heavy jobs overlapped.

    Only jobs on a different runner count as neighbours: a runner executes one job
    at a time, so the same runner can never be a concurrent neighbour. Pass several
    repositories' runs together to see cross-repo contention on a shared host.
    """
    heavy = [
        j
        for run in runs
        for j in run.get("jobs", [])
        if j["name"] in heavy_names and _finished(j)  # skipped/cancelled jobs are not real load
    ]
    buckets: dict[int, list[float]] = {}
    for target in heavy:
        if target["name"] != target_name:
            continue
        t0, t1 = parse_ts(target["started_at"]), parse_ts(target["completed_at"])
        neighbours = 0
        for other in heavy:
            if other is target or other.get("runner_name") == target.get("runner_name"):
                continue
            if parse_ts(other["started_at"]) < t1 and parse_ts(other["completed_at"]) > t0:
                neighbours += 1
        buckets.setdefault(neighbours, []).append((t1 - t0).total_seconds())
    return buckets


# --------------------------------------------------------------------------- IO


def _gh_lines(path: str, jq: str):
    proc = subprocess.run(
        ["gh", "api", "--paginate", path, "--jq", jq],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"gh api failed for {path}: {proc.stderr.strip()[:300]}")
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")]


def collect(repo, workflow, since, limit, events):
    created = urllib.parse.quote(f">={since}", safe="")
    runs_path = f"repos/{repo}/actions/workflows/{workflow}/runs?per_page=100&created={created}"
    runs = _gh_lines(runs_path, ".workflow_runs[]|{id,event,conclusion,created_at,head_branch}")
    runs = [r for r in runs if not events or r["event"] in events][:limit]
    jq_jobs = (
        ".jobs[]|{name,conclusion,runner_name,created_at,started_at,completed_at,"
        "steps:[.steps[]|{name,conclusion,started_at,completed_at}]}"
    )
    for run in runs:
        run["jobs"] = _gh_lines(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100", jq_jobs)
    return runs


def _fmt(seconds):
    return "-" if seconds is None else f"{seconds:7.0f}s"


def report(runs, check=None, steps=(), overlap_target=None, heavy=()):
    lines = [f"{len(runs)} runs\n", "== Jobs (queue = waiting for a runner, run = executing)"]
    lines.append(f"{'job':34s} {'n':>4s} {'fail':>4s} {'queue med':>10s} {'queue p90':>10s} {'run med':>9s} {'run p90':>9s} {'run max':>9s}")
    for name, s in sorted(job_stats(runs).items(), key=lambda kv: -kv[1]["run_med"]):
        lines.append(
            f"{name[:34]:34s} {s['n']:4d} {s['failed']:4d} {_fmt(s['queue_med']):>10s} {_fmt(s['queue_p90']):>10s} "
            f"{_fmt(s['run_med']):>9s} {_fmt(s['run_p90']):>9s} {_fmt(s['run_max']):>9s}"
        )
    for job_name in steps:
        lines += ["", f"== Slowest steps of '{job_name}' (include 'Post ...' steps)"]
        for name, med, mx, n in step_stats(runs, job_name):
            lines.append(f"  {name[:48]:48s} median {med:6.0f}s  max {mx:6.0f}s  n={n}")
    if check:
        values = [v for v in (time_to_check(r, check) for r in runs) if v is not None]
        lines += ["", f"== Time to required check '{check}' (PR event -> check done), n={len(values)}"]
        if values:
            lines.append(f"  median {median(values) / 60:5.1f} min   p90 {percentile(values, 90) / 60:5.1f} min   max {max(values) / 60:5.1f} min")
    if overlap_target:
        buckets = overlap_buckets(runs, set(heavy) | {overlap_target}, overlap_target)
        lines += ["", f"== '{overlap_target}' run time by number of other heavy jobs running at the same time"]
        for k in sorted(buckets):
            v = buckets[k]
            lines.append(f"  {k} neighbours: n={len(v):3d}  median {median(v):6.0f}s  min {min(v):6.0f}s  max {max(v):6.0f}s")
        lines.append("  (a large jump with neighbours = CPU/IO contention on a shared host)")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="download runs, jobs and steps with `gh api` (read-only)")
    c.add_argument("--repo", required=True, help="OWNER/NAME")
    c.add_argument("--workflow", required=True, help="workflow file name, e.g. ci.yml")
    c.add_argument("--since", required=True, help="YYYY-MM-DD")
    c.add_argument("--limit", type=int, default=100)
    c.add_argument("--events", default="pull_request,push", help="comma list; empty = all")
    c.add_argument("--out", required=True)

    r = sub.add_parser("report", help="print statistics from a collected file")
    r.add_argument("files", nargs="+", help="one or more files from `collect` (pass several to see cross-repo contention)")
    r.add_argument("--check", help="required-check job name for time-to-check")
    r.add_argument("--steps", default="", help="comma list of job names to break down by step")
    r.add_argument("--overlap-target", help="job whose run time is bucketed by concurrent neighbours")
    r.add_argument("--heavy", default="", help="comma list of job names counted as neighbours")

    args = parser.parse_args(argv)
    if args.cmd == "collect":
        events = {e for e in args.events.split(",") if e}
        runs = collect(args.repo, args.workflow, args.since, args.limit, events)
        Path(args.out).write_text(json.dumps({"runs": runs}))
        print(f"wrote {len(runs)} runs to {args.out}")
        return 0
    runs = []
    for f in args.files:
        runs += json.loads(Path(f).read_text())["runs"]
    split = lambda s: [x for x in s.split(",") if x]  # noqa: E731
    print(report(runs, args.check, split(args.steps), args.overlap_target, split(args.heavy)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
