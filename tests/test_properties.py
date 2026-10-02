"""Property tests for ci_timing.py and audit_runs_on.py.

Standard library only: each property runs over many inputs drawn from a seeded
`random.Random`, so a failure names the seed and can be replayed exactly. Three
kinds of property are used: an independent model of the answer (`oracle`),
a change of the input that must not change the answer (metamorphic), and
hostile input that must neither crash the script nor reach the terminal.
"""

import io
import json
import random
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "ci-perf" / "scripts"))

import audit_runs_on  # noqa: E402
import ci_timing  # noqa: E402

CASES = 200
UNSAFE = {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}
HOSTILE = ["\x1b", "\u202e", "\u2028", "\u2029", "\ud800", "\ue000", "\u0378", "\x00", "\u200b", "\r"]
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def seeds(count=CASES):
    return range(count)


def ts(seconds):
    return (EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def hostile_text(rng, length=12):
    pool = HOSTILE + list("abc XYZ_-.,()[]中é")
    return "".join(rng.choice(pool) for _ in range(rng.randint(0, length)))


def has_unsafe(text, allowed=""):
    return any(unicodedata.category(c) in UNSAFE and c not in allowed for c in text)


def random_job(rng, name=None, base=0):
    created = base + rng.randint(0, 50)
    started = created + rng.randint(0, 30)
    completed = started + rng.randint(0, 100)
    return {
        "name": name or rng.choice(["unit", "lint", "build", "e2e"]),
        "conclusion": rng.choice(["success", "success", "failure"]),
        "runner_name": rng.choice(["r1", "r2", "r3", None]),
        "created_at": ts(created),
        "started_at": ts(started),
        "completed_at": ts(completed),
        "steps": [],
    }


def damage(rng, job):
    """Turn a good job into one the statistics must ignore or count as skipped."""
    kind = rng.choice(["unfinished", "cancelled", "skew-start", "skew-end", "garbage", "nameless"])
    if kind == "unfinished":
        job["completed_at"] = None
    elif kind == "cancelled":
        job["conclusion"] = "cancelled"
    elif kind == "skew-start":
        job["started_at"] = ts(-5)
        job["created_at"] = ts(10)
    elif kind == "skew-end":
        job["completed_at"] = ts(-5)
    elif kind == "garbage":
        job["started_at"] = "not a time"
    else:
        job["name"] = ""
    return job


def random_runs(rng, damaged=True):
    runs = []
    for run_id in range(rng.randint(0, 6)):
        jobs = []
        for _ in range(rng.randint(0, 6)):
            j = random_job(rng)
            jobs.append(damage(rng, j) if damaged and rng.random() < 0.25 else j)
        runs.append({"id": run_id, "event": "push", "jobs": jobs})
    return runs


def is_good(job):
    """Independent statement of what a countable job is."""
    if job["conclusion"] not in ("success", "failure") or not job["name"]:
        return False
    try:
        c, s, e = (ci_timing.parse_ts(job[k]) for k in ("created_at", "started_at", "completed_at"))
    except (ValueError, TypeError, AttributeError):
        return False
    return c <= s <= e


def shift(runs, seconds):
    moved = json.loads(json.dumps(runs))
    for run in moved:
        for j in run["jobs"]:
            for key in ("created_at", "started_at", "completed_at"):
                if j.get(key) and j[key] != "not a time":
                    j[key] = ts((ci_timing.parse_ts(j[key]) - EPOCH).total_seconds() + seconds)
    return moved


class SanitizerProperties(unittest.TestCase):
    def test_clean_replaces_exactly_the_unsafe_characters_and_nothing_else(self):
        for seed in seeds():
            text = hostile_text(random.Random(seed))
            with self.subTest(seed=seed):
                out = ci_timing.clean(text)
                self.assertEqual(len(out), len(text))
                self.assertFalse(has_unsafe(out))
                for before, after in zip(text, out):
                    expected = "?" if unicodedata.category(before) in UNSAFE else before
                    self.assertEqual(after, expected)

    def test_clean_is_idempotent_and_width_is_a_prefix_of_the_full_result(self):
        for seed in seeds():
            rng = random.Random(seed)
            text, width = hostile_text(rng), rng.randint(0, 15)
            with self.subTest(seed=seed):
                self.assertEqual(ci_timing.clean(ci_timing.clean(text)), ci_timing.clean(text))
                self.assertEqual(ci_timing.clean(text, width), ci_timing.clean(text)[:width])

    def test_the_audit_sanitizer_agrees_with_the_timing_sanitizer(self):
        for seed in seeds():
            rng = random.Random(seed)
            text, width = hostile_text(rng), rng.randint(0, 15)
            with self.subTest(seed=seed):
                self.assertEqual(audit_runs_on._printable(text, width), ci_timing.clean(text, width))


class SplitNamesProperties(unittest.TestCase):
    PIECES = ["a", "b c", "build (ubuntu, 3.11)", "x [1, 2]", "f((x, y), z)", "web-ui", "e2e (a, b) [c, d]"]

    def test_a_comma_list_of_balanced_names_splits_back_into_those_names(self):
        for seed in seeds():
            rng = random.Random(seed)
            names = [rng.choice(self.PIECES) for _ in range(rng.randint(0, 6))]
            pad = lambda: " " * rng.randint(0, 2)  # noqa: E731
            text = ",".join(pad() + n + pad() for n in names)
            if rng.random() < 0.3:
                text += ",,"  # empty items are dropped
            with self.subTest(seed=seed, text=text):
                self.assertEqual(ci_timing.split_names(text), names)

    def test_every_result_is_non_empty_and_trimmed_for_any_text(self):
        for seed in seeds():
            text = hostile_text(random.Random(seed), 30)
            with self.subTest(seed=seed):
                for name in ci_timing.split_names(text):
                    self.assertTrue(name)
                    self.assertEqual(name, name.strip())

    def test_text_without_brackets_splits_exactly_like_str_split(self):
        for seed in seeds():
            rng = random.Random(seed)
            text = "".join(rng.choice("ab ,,") for _ in range(rng.randint(0, 20)))
            with self.subTest(seed=seed, text=text):
                self.assertEqual(ci_timing.split_names(text), [p.strip() for p in text.split(",") if p.strip()])


class PercentileProperties(unittest.TestCase):
    def test_nearest_rank_definition_holds_for_every_value_and_percentile(self):
        import math

        for seed in seeds():
            rng = random.Random(seed)
            values = [rng.randint(0, 20) for _ in range(rng.randint(1, 30))]
            p = rng.randint(1, 100)
            result = ci_timing.percentile(values, p)
            need = math.ceil(p / 100 * len(values))
            with self.subTest(seed=seed):
                self.assertIn(result, values)
                self.assertGreaterEqual(sum(v <= result for v in values), need)
                self.assertLess(sum(v < result for v in values), need)

    def test_it_is_monotonic_in_p_bounded_by_min_and_max_and_ignores_order(self):
        for seed in seeds():
            rng = random.Random(seed)
            values = [rng.uniform(0, 100) for _ in range(rng.randint(1, 30))]
            shuffled = values[:]
            rng.shuffle(shuffled)
            with self.subTest(seed=seed):
                results = [ci_timing.percentile(values, p) for p in range(0, 101, 5)]
                self.assertEqual(results, sorted(results))
                self.assertEqual(results[0], min(values))
                self.assertEqual(results[-1], max(values))
                self.assertEqual(ci_timing.percentile(shuffled, 90), ci_timing.percentile(values, 90))


class JobStatsProperties(unittest.TestCase):
    def test_counts_match_an_independent_filter_and_orderings_hold(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = random_runs(rng)
            all_jobs = [j for r in runs for j in r["jobs"]]
            stats = ci_timing.job_stats(runs)
            with self.subTest(seed=seed):
                good = [j for j in all_jobs if is_good(j)]
                self.assertEqual(sum(s["n"] for s in stats.values()), len(good))
                self.assertEqual(sum(s["failed"] for s in stats.values()), sum(j["conclusion"] == "failure" for j in good))
                finished = [j for j in all_jobs if j["conclusion"] in ("success", "failure") and j["started_at"] and j["completed_at"]]
                self.assertEqual(ci_timing.invalid_job_count(runs), len(finished) - len(good))
                for s in stats.values():
                    self.assertLessEqual(s["failed"], s["n"])
                    self.assertLessEqual(0, s["queue_med"])
                    self.assertLessEqual(s["queue_med"], s["queue_p90"])
                    self.assertLessEqual(s["run_med"], s["run_p90"])
                    self.assertLessEqual(s["run_p90"], s["run_max"])

    def test_the_result_ignores_the_order_of_runs_and_jobs_and_a_shift_in_time(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = random_runs(rng)
            shuffled = json.loads(json.dumps(runs))
            rng.shuffle(shuffled)
            for run in shuffled:
                rng.shuffle(run["jobs"])
            with self.subTest(seed=seed):
                expected = ci_timing.job_stats(runs)
                self.assertEqual(ci_timing.job_stats(shuffled), expected)
                self.assertEqual(ci_timing.job_stats(shift(runs, rng.randint(-1000, 100000))), expected)


class TimeToCheckProperties(unittest.TestCase):
    def test_it_is_the_check_completion_minus_the_earliest_created_job(self):
        for seed in seeds():
            rng = random.Random(seed)
            run = {"jobs": [random_job(rng) if rng.random() > 0.2 else damage(rng, random_job(rng)) for _ in range(rng.randint(0, 6))]}
            result = ci_timing.time_to_check(run, "unit")
            with self.subTest(seed=seed):
                checks = [j for j in run["jobs"] if j["name"] == "unit" and is_good(j)]
                if not checks:
                    self.assertIsNone(result)
                    continue
                created = [ci_timing.parse_ts(j["created_at"]) for j in run["jobs"] if j["created_at"]]
                expected = (ci_timing.parse_ts(checks[0]["completed_at"]) - min(created)).total_seconds()
                self.assertEqual(result, expected)
                self.assertGreaterEqual(result, 0)


class OverlapProperties(unittest.TestCase):
    @staticmethod
    def model(runs, heavy, target):
        """Brute-force statement of the rule: strictly overlapping jobs on another runner."""
        jobs = [j for r in runs for j in r["jobs"] if is_good(j) and j["name"] in heavy]
        buckets = {}
        for t in jobs:
            if t["name"] != target:
                continue
            count = 0
            for o in jobs:
                if o is t:
                    continue
                if t["runner_name"] is not None and o["runner_name"] == t["runner_name"]:
                    continue
                if o["started_at"] < t["completed_at"] and o["completed_at"] > t["started_at"]:
                    count += 1
            buckets.setdefault(count, []).append(
                (ci_timing.parse_ts(t["completed_at"]) - ci_timing.parse_ts(t["started_at"])).total_seconds())
        return buckets

    def test_buckets_match_the_brute_force_model(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = random_runs(rng)
            heavy = set(rng.sample(["unit", "lint", "build", "e2e"], rng.randint(1, 4)))
            with self.subTest(seed=seed):
                got = ci_timing.overlap_buckets(runs, heavy, "unit")
                want = self.model(runs, heavy | {"unit"}, "unit") if "unit" in heavy else self.model(runs, heavy, "unit")
                self.assertEqual({k: sorted(v) for k, v in got.items()}, {k: sorted(v) for k, v in want.items()})

    def test_buckets_are_invariant_under_time_shift_and_job_order_and_bounded(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = random_runs(rng, damaged=False)
            heavy = {"unit", "lint", "build"}
            shuffled = json.loads(json.dumps(runs))
            rng.shuffle(shuffled)
            with self.subTest(seed=seed):
                base = ci_timing.overlap_buckets(runs, heavy, "unit")
                norm = lambda b: {k: sorted(v) for k, v in b.items()}  # noqa: E731
                self.assertEqual(norm(ci_timing.overlap_buckets(shuffled, heavy, "unit")), norm(base))
                self.assertEqual(norm(ci_timing.overlap_buckets(shift(runs, 86400), heavy, "unit")), norm(base))
                total_heavy = sum(j["name"] in heavy for r in runs for j in r["jobs"])
                self.assertEqual(sum(len(v) for v in base.values()), sum(j["name"] == "unit" for r in runs for j in r["jobs"]))
                self.assertTrue(all(0 <= k <= max(0, total_heavy - 1) for k in base))


class StepStatsProperties(unittest.TestCase):
    def test_rows_are_sorted_capped_and_consistent_with_the_raw_steps(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = []
            raw = {}
            for i in range(rng.randint(0, 5)):
                j = random_job(rng, "build")
                for _ in range(rng.randint(0, 5)):
                    name, start = rng.choice(["checkout", "test", "post", "lint"]), rng.randint(0, 50)
                    length = rng.randint(0, 40)
                    s = {"name": name, "started_at": ts(start), "completed_at": ts(start + length)}
                    if rng.random() < 0.2:
                        s["completed_at"] = None
                    else:
                        raw.setdefault(name, []).append(length)
                    j["steps"].append(s)
                runs.append({"id": i, "jobs": [j]})
            top = rng.randint(1, 4)
            with self.subTest(seed=seed):
                rows = ci_timing.step_stats(runs, "build", top=top)
                self.assertLessEqual(len(rows), top)
                medians = [r[1] for r in rows]
                self.assertEqual(medians, sorted(medians, reverse=True))
                for name, med, mx, n in rows:
                    self.assertEqual(n, len(raw[name]))
                    self.assertEqual(mx, max(raw[name]))
                    self.assertLessEqual(med, mx)
                self.assertEqual(len(ci_timing.step_stats(runs, "build", top=100)), len(raw))


class CollectProperties(unittest.TestCase):
    @staticmethod
    def fake_api(rng, total_runs, jobs_per_run):
        """A GitHub-like API: newest-first runs in pages of 100, jobs in pages of 100."""
        from urllib.parse import parse_qs, urlparse

        events = [rng.choice(["push", "pull_request", "schedule"]) for _ in range(total_runs)]
        calls = []

        def fetch(path, jq):
            calls.append(path)
            parsed = urlparse(path)
            page, size = int(parse_qs(parsed.query)["page"][0]), 100
            if "/jobs" in path:
                run_id = int(parsed.path.split("/")[-2])
                n = jobs_per_run[run_id]
                return [{"name": f"job{run_id}-{i}"} for i in range(n)][(page - 1) * size:page * size]
            rows = [{"id": i, "event": events[i], "conclusion": "success", "created_at": ts(0)} for i in range(total_runs)]
            return rows[(page - 1) * size:page * size]

        return fetch, events, calls

    def test_collect_returns_the_newest_matching_runs_up_to_the_limit_with_all_their_jobs(self):
        for seed in seeds(80):
            rng = random.Random(seed)
            total = rng.choice([0, 1, 5, 99, 100, 101, 250])
            jobs_per_run = [rng.choice([0, 1, 99, 100, 101]) for _ in range(total)]
            fetch, events, calls = self.fake_api(rng, total, jobs_per_run)
            wanted = set(rng.sample(["push", "pull_request", "schedule"], rng.randint(0, 3)))
            limit = rng.choice([1, 3, 50, 100, 101, 400])
            with self.subTest(seed=seed, total=total, limit=limit, wanted=wanted):
                runs = ci_timing.collect("o/r", "ci.yml", "2026-01-01", limit=limit, events=wanted, fetch=fetch)
                matching = [i for i in range(total) if not wanted or events[i] in wanted]
                self.assertEqual([r["id"] for r in runs], matching[:limit])
                for r in runs:
                    self.assertEqual(len(r["jobs"]), jobs_per_run[r["id"]])
                    job_pages = [c for c in calls if f"/runs/{r['id']}/jobs" in c]
                    self.assertEqual(len(job_pages), jobs_per_run[r["id"]] // 100 + 1)
                run_pages = [c for c in calls if "/jobs" not in c]
                self.assertEqual(len(run_pages), len(set(run_pages)), "a page was requested twice")
                self.assertLessEqual(len(run_pages), total // 100 + 1)

    def test_collect_never_requests_more_job_pages_than_the_guard_allows(self):
        calls = []

        def fetch(path, jq):
            calls.append(path)
            if "/jobs" in path:
                return [{"name": "j"}] * 100  # an API that ignores `page`
            return [{"id": 1, "event": "push", "conclusion": "success", "created_at": ts(0)}]

        runs = ci_timing.collect("o/r", "ci.yml", "2026-01-01", limit=1, events=set(), fetch=fetch)
        self.assertEqual(len(runs[0]["jobs"]), 2000)  # documented: 2000 jobs per run
        self.assertEqual(sum("/jobs" in c for c in calls), 20)


class ReportProperties(unittest.TestCase):
    def test_a_report_of_hostile_names_never_crashes_and_never_carries_unsafe_characters(self):
        for seed in seeds():
            rng = random.Random(seed)
            names = [hostile_text(rng, 8) or "x" for _ in range(3)]
            runs = []
            for i in range(rng.randint(0, 4)):
                jobs = []
                for _ in range(rng.randint(0, 4)):
                    j = random_job(rng, rng.choice(names))
                    j["steps"] = [{"name": hostile_text(rng, 8) or "s", "started_at": j["started_at"], "completed_at": j["completed_at"]}]
                    jobs.append(j)
                runs.append({"id": i, "event": "push", "jobs": jobs})
            with self.subTest(seed=seed):
                text = ci_timing.report(runs, check=names[0], steps=[names[1]], overlap_target=names[2], heavy=names)
                self.assertFalse(has_unsafe(text, allowed="\n"))

    def test_a_report_over_random_data_always_has_the_run_count_first_and_never_crashes(self):
        for seed in seeds():
            rng = random.Random(seed)
            runs = random_runs(rng)
            with self.subTest(seed=seed):
                text = ci_timing.report(runs, check="unit", steps=["unit"], overlap_target="unit", heavy=["lint"])
                self.assertTrue(text.startswith(f"{len(runs)} runs"))

    def test_reporting_the_same_file_twice_equals_reporting_it_once(self):
        for seed in seeds(30):
            runs = random_runs(random.Random(seed))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "r.json")
                path.write_text(json.dumps({"runs": runs}))
                outputs = []
                for files in ([str(path)], [str(path), str(path)]):
                    out = io.StringIO()
                    with redirect_stdout(out):
                        ci_timing.main(["report", *files])
                    outputs.append(out.getvalue())
            with self.subTest(seed=seed):
                self.assertEqual(outputs[0], outputs[1])


# ---------------------------------------------------------------- audit_runs_on

HOSTED_VALUES = ["ubuntu-latest", "ubuntu-22.04", "macos-14", "windows-2022"]
SELF_VALUES = ["self-hosted", "{group: big}"]
OTHER_VALUES = ["my-label", "${{ matrix.os }}", "ubuntu-${{ matrix.v }}"]


def label_kind(label):
    if "${{" in label:
        return "dynamic"
    if "self-hosted" in label or "group" in label:
        return "self-hosted"
    if label.startswith(("ubuntu", "macos", "windows")):
        return "github-hosted"
    return "dynamic"


def combined_kind(labels):
    kinds = [label_kind(l) for l in labels]
    if "dynamic" in kinds and any("${{" in l for l in labels):
        return "dynamic"
    if "self-hosted" in kinds:
        return "self-hosted"
    if "github-hosted" in kinds:
        return "github-hosted"
    return "dynamic"


def random_workflow(rng):
    """(model rows, text, plain text): the same jobs rendered in a random layout and in a fixed one."""
    jobs = []
    for i in range(rng.randint(1, 5)):
        name = f"job-{i}"
        form = rng.choice(["scalar", "seq", "flow", "uses"])
        if form == "scalar":
            value = rng.choice(HOSTED_VALUES + SELF_VALUES[:1] + OTHER_VALUES)
            jobs.append((name, form, value, label_kind(value), value))
        elif form == "uses":
            path = f"./.github/workflows/w{i}.yml"
            jobs.append((name, form, path, "reusable", path))
        else:
            labels = rng.sample(HOSTED_VALUES[:2] + ["self-hosted", "linux", "${{ matrix.os }}"], rng.randint(1, 3))
            value = " ".join("- " + l for l in labels) if form == "seq" else "[" + ", ".join(labels) + "]"
            jobs.append((name, form, labels, combined_kind(labels), value))
    model = [{"job": n, "kind": k, "value": v} for n, _, _, k, v in jobs]
    return jobs, model


def render(rng, jobs, plain=False):
    unit = 2 if plain else rng.choice([2, 3, 4])
    eol = "\n" if plain else rng.choice(["\n", "\r\n"])
    noise = (lambda: "") if plain else (lambda: rng.choice(["", "", "\n", "# a comment\n", "   \n"]).replace("\n", eol))
    out = [f"name: demo{eol}", f"on: [push]{eol}", f"jobs:{eol}"]
    ind1, ind2, ind3 = " " * unit, " " * unit * 2, " " * unit * 3
    for name, form, payload, _kind, _value in jobs:
        out.append(noise())
        out.append(f"{ind1}{name}:{eol}")
        comment = "" if plain else rng.choice(["", " # self-hosted", " # ubuntu-latest", " # note"])
        if form == "uses":
            out.append(f"{ind2}uses: {payload}{comment}{eol}")
        elif form == "scalar":
            out.append(f"{ind2}runs-on: {payload}{comment}{eol}")
        elif form == "flow":
            out.append(f"{ind2}runs-on: [{', '.join(payload)}]{comment}{eol}")
        else:
            out.append(f"{ind2}runs-on:{comment}{eol}")
            for label in payload:
                out.append(f"{ind3}- {label}{eol}")
        if not plain and form != "uses" and rng.random() < 0.5:
            out.append(f"{ind2}steps:{eol}{ind3}- run: echo hi{eol}{ind3}  env:{eol}{ind3}    runs-on: self-hosted{eol}")
    if not plain and rng.random() < 0.5:
        out.append(f"env:{eol}  runs-on: self-hosted{eol}")
    return "".join(out)


class AuditLayoutProperties(unittest.TestCase):
    def test_any_indentation_line_ending_comment_and_noise_gives_the_same_rows_as_the_model(self):
        for seed in seeds(400):
            rng = random.Random(seed)
            jobs, model = random_workflow(rng)
            text = render(rng, jobs)
            with self.subTest(seed=seed):
                rows = audit_runs_on.classify_workflow(text)
                self.assertEqual(rows, model, msg=text)
                self.assertEqual(audit_runs_on.classify_workflow(render(rng, jobs, plain=True)), model)

    def test_a_trailing_comment_never_changes_the_kind(self):
        for seed in seeds():
            rng = random.Random(seed)
            value = rng.choice(HOSTED_VALUES + SELF_VALUES[:1] + OTHER_VALUES)
            comment = rng.choice(["# self-hosted", "# ubuntu-latest", "# ${{ x }}", "#"])
            with self.subTest(seed=seed):
                plain = audit_runs_on.classify_workflow(f"jobs:\n  a:\n    runs-on: {value}\n")
                commented = audit_runs_on.classify_workflow(f"jobs:\n  a:\n    runs-on: {value} {comment}\n")
                self.assertEqual(plain, commented)

    def test_an_expression_is_always_dynamic_and_self_hosted_beats_a_hosted_name(self):
        for seed in seeds():
            rng = random.Random(seed)
            parts = [rng.choice(HOSTED_VALUES + ["self-hosted", "x", "linux"]) for _ in range(rng.randint(0, 3))]
            with self.subTest(seed=seed):
                with_expr = " ".join(parts + ["${{ matrix.os }}"])
                self.assertEqual(audit_runs_on._kind(with_expr), "dynamic")
                self.assertEqual(audit_runs_on._kind(" ".join(parts + ["self-hosted", "ubuntu-latest"])), "self-hosted")


class AuditRobustnessProperties(unittest.TestCase):
    FRAGMENTS = ["jobs:", "  a:", "    runs-on: ubuntu-latest", "    uses: ./x.yml", "runs-on:", "  - self-hosted", "\t", "#", "  # c",
                 "{", "}", "[", "]", ":", "  b: {runs-on: x}", "    runs-on: [a, b", "\"", "'", "    runs-on: # c", "      - linux", ""]

    def test_arbitrary_line_soup_never_raises_and_always_returns_well_formed_rows(self):
        for seed in seeds(500):
            rng = random.Random(seed)
            text = "\n".join(rng.choice(self.FRAGMENTS + [hostile_text(rng)]) for _ in range(rng.randint(0, 15)))
            with self.subTest(seed=seed):
                rows = audit_runs_on.classify_workflow(text)
                for row in rows:
                    self.assertEqual(set(row), {"job", "kind", "value"})
                    self.assertIn(row["kind"], {"github-hosted", "self-hosted", "dynamic", "reusable"})
                    self.assertIsInstance(row["job"], str)
                    self.assertIsInstance(row["value"], str)

    def test_hostile_job_names_and_values_never_reach_the_terminal(self):
        for seed in seeds(60):
            rng = random.Random(seed)
            name = (hostile_text(rng, 6).replace('"', "") or "x") + "j"
            value = hostile_text(rng, 10)
            with tempfile.TemporaryDirectory() as tmp:
                wf = Path(tmp, ".github", "workflows")
                wf.mkdir(parents=True)
                (wf / "ci.yml").write_text(f'jobs:\n  "{name}":\n    runs-on: ubuntu-latest {value}\n', encoding="utf-8", errors="replace")
                out = io.StringIO()
                with redirect_stdout(out):
                    audit_runs_on.main([tmp])
            with self.subTest(seed=seed):
                self.assertFalse(has_unsafe(out.getvalue(), allowed="\n"))


if __name__ == "__main__":
    unittest.main()
