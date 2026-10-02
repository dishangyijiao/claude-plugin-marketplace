"""Tests for ci_timing.py: pure analysis functions on synthetic run data."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "ci-perf" / "scripts"))

import ci_timing  # noqa: E402


def ts(seconds: int) -> str:
    """ISO timestamp `seconds` after a fixed epoch, in the GitHub API format."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def job(name, created, started, completed, runner="r1", conclusion="success", steps=None):
    return {
        "name": name,
        "conclusion": conclusion,
        "runner_name": runner,
        "created_at": ts(created),
        "started_at": ts(started) if started is not None else None,
        "completed_at": ts(completed) if completed is not None else None,
        "steps": steps or [],
    }


def step(name, start, end, conclusion="success"):
    return {"name": name, "conclusion": conclusion, "started_at": ts(start), "completed_at": ts(end)}


class PercentileTests(unittest.TestCase):
    def test_nearest_rank(self):
        values = list(range(1, 11))
        self.assertEqual(ci_timing.percentile(values, 50), 5)
        self.assertEqual(ci_timing.percentile(values, 90), 9)
        self.assertEqual(ci_timing.percentile(values, 100), 10)

    def test_single_value_and_empty(self):
        self.assertEqual(ci_timing.percentile([7], 90), 7)
        self.assertIsNone(ci_timing.percentile([], 50))

    def test_input_order_does_not_matter(self):
        self.assertEqual(ci_timing.percentile([9, 1, 5], 50), ci_timing.percentile([1, 5, 9], 50))


class JobStatsTests(unittest.TestCase):
    def test_queue_and_run_are_separated(self):
        runs = [{"id": 1, "jobs": [job("test", created=0, started=30, completed=130)]}]
        stats = ci_timing.job_stats(runs)["test"]
        self.assertEqual(stats["n"], 1)
        self.assertEqual(stats["queue_med"], 30)
        self.assertEqual(stats["run_med"], 100)

    def test_skipped_and_unfinished_jobs_are_ignored(self):
        runs = [
            {
                "id": 1,
                "jobs": [
                    job("test", 0, None, None, conclusion="skipped"),
                    job("test", 0, 5, None, conclusion=None),
                    job("test", 0, 5, 65),
                ],
            }
        ]
        self.assertEqual(ci_timing.job_stats(runs)["test"]["n"], 1)

    def test_failures_are_counted_as_runs_but_flagged(self):
        runs = [{"id": 1, "jobs": [job("test", 0, 0, 10), job("test", 0, 0, 20, conclusion="failure")]}]
        stats = ci_timing.job_stats(runs)["test"]
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["failed"], 1)


class StepStatsTests(unittest.TestCase):
    def test_slowest_steps_first(self):
        steps = [step("install", 0, 20), step("unit tests", 20, 320), step("lint", 320, 340)]
        runs = [{"id": 1, "jobs": [job("web", 0, 0, 340, steps=steps)]}]
        top = ci_timing.step_stats(runs, "web", top=2)
        self.assertEqual([s[0] for s in top], ["unit tests", "install"])
        self.assertEqual(top[0][1], 300)

    def test_unknown_job_gives_empty_list(self):
        self.assertEqual(ci_timing.step_stats([], "nope"), [])


class TimeToCheckTests(unittest.TestCase):
    def test_from_first_job_created_to_check_completed(self):
        run = {"id": 1, "jobs": [job("plan", 0, 5, 30), job("gate", 100, 105, 120)]}
        self.assertEqual(ci_timing.time_to_check(run, "gate"), 120)

    def test_missing_or_unfinished_check_is_none(self):
        run = {"id": 1, "jobs": [job("plan", 0, 5, 30)]}
        self.assertIsNone(ci_timing.time_to_check(run, "gate"))
        run = {"id": 1, "jobs": [job("gate", 0, 5, None, conclusion=None)]}
        self.assertIsNone(ci_timing.time_to_check(run, "gate"))


    def test_skipped_check_does_not_count(self):
        # e.g. a draft pull request: the gate is skipped, there is no real "time to check"
        run = {"id": 1, "jobs": [job("plan", 0, 1, 2, conclusion="skipped"), job("gate", 0, 1, 1, conclusion="skipped")]}
        self.assertIsNone(ci_timing.time_to_check(run, "gate"))


class OverlapTests(unittest.TestCase):
    def test_counts_overlapping_heavy_jobs_on_other_runners(self):
        runs = [
            {
                "id": 1,
                "jobs": [
                    job("pytest", 0, 0, 100, runner="r1"),  # target
                    job("pytest", 0, 50, 150, runner="r2"),  # overlaps the target
                    job("pytest", 0, 200, 300, runner="r3"),  # does not overlap
                ],
            }
        ]
        buckets = ci_timing.overlap_buckets(runs, heavy_names={"pytest"}, target_name="pytest")
        # target r1 sees 1 other (r2); r2 sees 1 other (r1); r3 sees none
        self.assertEqual(sorted(buckets.keys()), [0, 1])
        self.assertEqual(sorted(buckets[1]), [100, 100])
        self.assertEqual(buckets[0], [100])

    def test_same_runner_is_never_counted_as_concurrent(self):
        runs = [{"id": 1, "jobs": [job("pytest", 0, 0, 100, runner="r1"), job("pytest", 0, 50, 150, runner="r1")]}]
        buckets = ci_timing.overlap_buckets(runs, {"pytest"}, "pytest")
        self.assertEqual(list(buckets.keys()), [0])

    def test_skipped_and_cancelled_jobs_are_not_samples_or_neighbours(self):
        runs = [
            {
                "id": 1,
                "jobs": [
                    job("pytest", 0, 0, 100, runner="r1"),
                    job("pytest", 0, 50, 50, runner="r2", conclusion="skipped"),  # zero-length, overlaps
                    job("pytest", 0, 60, 90, runner="r3", conclusion="cancelled"),
                ],
            }
        ]
        buckets = ci_timing.overlap_buckets(runs, {"pytest"}, "pytest")
        self.assertEqual(buckets, {0: [100]})  # only the real job, and nobody counted as a neighbour

    def test_overlap_works_across_runs(self):
        runs = [
            {"id": 1, "jobs": [job("a", 0, 0, 100, runner="r1")]},
            {"id": 2, "jobs": [job("b", 0, 10, 90, runner="r2")]},
        ]
        buckets = ci_timing.overlap_buckets(runs, {"a", "b"}, "a")
        self.assertEqual(buckets, {1: [100]})


class ReportTests(unittest.TestCase):
    def test_report_cli_prints_job_table(self):
        runs = [{"id": 1, "event": "pull_request", "jobs": [job("unit", 0, 10, 70, steps=[step("tests", 10, 70)])]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.json"
            path.write_text(json.dumps({"runs": runs}))
            out = io.StringIO()
            with redirect_stdout(out):
                code = ci_timing.main(["report", str(path), "--check", "unit", "--steps", "unit"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("unit", text)
        self.assertIn("queue", text.lower())
        self.assertIn("tests", text)


if __name__ == "__main__":
    unittest.main()
