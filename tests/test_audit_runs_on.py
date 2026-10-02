"""Tests for audit_runs_on.py: classify which workflow jobs use GitHub-hosted runners."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "ci-perf" / "scripts"))

import audit_runs_on  # noqa: E402

WORKFLOW = """\
name: demo
on: [push]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
  build:
    runs-on:
      group: ci
      labels: [self-hosted, linux]
    steps:
      - run: echo hi
  inline:
    runs-on: [self-hosted, linux]
    steps:
      - run: echo hi
  matrix:
    runs-on: ${{ matrix.os }}
    steps:
      - run: echo hi
  call:
    uses: some-org/some-repo/.github/workflows/reusable.yml@main
  mac:
    runs-on: macos-14
    steps:
      - run: echo hi
"""


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.by_job = {j["job"]: j for j in audit_runs_on.classify_workflow(WORKFLOW)}

    def test_github_hosted_labels(self):
        self.assertEqual(self.by_job["lint"]["kind"], "github-hosted")
        self.assertEqual(self.by_job["mac"]["kind"], "github-hosted")

    def test_self_hosted_block_and_inline(self):
        self.assertEqual(self.by_job["build"]["kind"], "self-hosted")
        self.assertEqual(self.by_job["inline"]["kind"], "self-hosted")

    def test_dynamic_and_reusable_are_not_guessed(self):
        self.assertEqual(self.by_job["matrix"]["kind"], "dynamic")
        self.assertEqual(self.by_job["call"]["kind"], "reusable")

    def test_every_job_is_reported_once(self):
        self.assertEqual(sorted(self.by_job), ["build", "call", "inline", "lint", "mac", "matrix"])

    def test_text_before_jobs_is_ignored(self):
        text = "name: x\nenv:\n  runs-on: ubuntu-latest\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        self.assertEqual([j["job"] for j in audit_runs_on.classify_workflow(text)], ["a"])


class IndentationTests(unittest.TestCase):
    """Real workflow files are not always indented with 2 spaces."""

    def test_four_space_indentation(self):
        text = "jobs:\n    lint:\n        runs-on: ubuntu-latest\n        steps:\n            - run: x\n"
        rows = audit_runs_on.classify_workflow(text)
        self.assertEqual([(r["job"], r["kind"]) for r in rows], [("lint", "github-hosted")])

    def test_four_space_block_runs_on(self):
        text = "jobs:\n    build:\n        runs-on:\n            group: ci\n            labels: [self-hosted]\n"
        self.assertEqual(audit_runs_on.classify_workflow(text)[0]["kind"], "self-hosted")

    def test_comments_and_blank_lines_after_jobs(self):
        text = "jobs:\n\n  # a comment\n  a:\n    # runs-on: ubuntu-latest\n    runs-on: [self-hosted]\n"
        rows = audit_runs_on.classify_workflow(text)
        self.assertEqual([(r["job"], r["kind"]) for r in rows], [("a", "self-hosted")])

    def test_nested_runs_on_in_a_step_is_not_the_job_runner(self):
        text = "jobs:\n  a:\n    runs-on: [self-hosted]\n    steps:\n      - run: echo\n        env:\n          runs-on: ubuntu-latest\n"
        self.assertEqual(audit_runs_on.classify_workflow(text)[0]["kind"], "self-hosted")


class MainMessageTests(unittest.TestCase):
    def run_main(self, repo):
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            code = audit_runs_on.main([str(repo)])
        return code, out.getvalue()

    def test_no_workflows_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self.run_main(tmp)
        self.assertEqual(code, 1)
        self.assertIn("no workflow files", text)

    def test_files_found_but_no_jobs_parsed_is_not_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "odd.yml").write_text("name: odd\non: push\njobs: {a: {runs-on: ubuntu-latest}}\n")  # flow style
            code, text = self.run_main(tmp)
        self.assertEqual(code, 2)
        self.assertIn("1 workflow file", text)
        self.assertIn("0 jobs", text)


class AuditDirTests(unittest.TestCase):
    def test_directory_audit_flags_hosted_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_text(WORKFLOW)
            rows = audit_runs_on.audit_directory(Path(tmp))
        hosted = sorted(r["job"] for r in rows if r["kind"] == "github-hosted")
        self.assertEqual(hosted, ["lint", "mac"])
        self.assertTrue(all(r["file"] == "ci.yml" for r in rows))


if __name__ == "__main__":
    unittest.main()
