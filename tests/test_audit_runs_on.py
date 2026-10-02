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
