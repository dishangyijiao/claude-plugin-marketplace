"""Tests for audit_runs_on.py: classify which workflow jobs use GitHub-hosted runners."""

import io
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "ci-perf" / "scripts" / "audit_runs_on.py"
sys.path.insert(0, str(SCRIPT.parent))

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


class UntrustedInputTests(unittest.TestCase):
    def test_trailing_comment_does_not_change_the_kind(self):
        text = "jobs:\n  a:\n    runs-on: ubuntu-latest # self-hosted soon\n  b:\n    runs-on: [self-hosted] # ubuntu-latest\n"
        rows = {r["job"]: r for r in audit_runs_on.classify_workflow(text)}
        self.assertEqual(rows["a"]["kind"], "github-hosted")
        self.assertEqual(rows["a"]["value"], "ubuntu-latest")
        self.assertEqual(rows["b"]["kind"], "self-hosted")

    def test_comment_inside_block_runs_on_is_ignored(self):
        text = "jobs:\n  a:\n    runs-on:\n      group: ci # ubuntu-latest\n      labels: [x]\n"
        self.assertEqual(audit_runs_on.classify_workflow(text)[0]["kind"], "self-hosted")

    def test_symlinked_workflow_files_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "secret.txt"
            secret.write_text("jobs:\n  leak:\n    runs-on: ubuntu-latest\n")
            wf = Path(tmp) / "repo" / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "link.yml").symlink_to(secret)
            self.assertEqual(audit_runs_on.workflow_files(Path(tmp) / "repo"), [])

    def test_symlinked_workflows_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "x.yml").write_text("jobs:\n  leak:\n    runs-on: ubuntu-latest\n")
            repo = Path(tmp) / "repo"
            (repo / ".github").mkdir(parents=True)
            (repo / ".github" / "workflows").symlink_to(outside)
            self.assertEqual(audit_runs_on.workflow_files(repo), [])

    def test_oversized_workflow_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "big.yml").write_text("#" * (audit_runs_on.MAX_WORKFLOW_BYTES + 1))
            (wf / "ok.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n")
            self.assertEqual([p.name for p in audit_runs_on.workflow_files(Path(tmp))], ["ok.yml"])

    def test_bidi_and_line_separator_characters_are_replaced(self):
        self.assertEqual(audit_runs_on._printable("a\u202eb\u2028c", 20), "a?b?c")

    def test_output_has_no_control_characters(self):
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_text("jobs:\n  a:\n    runs-on: \x1b[31mubuntu-latest\n")
            out = io.StringIO()
            with redirect_stdout(out):
                audit_runs_on.main([tmp])
        self.assertNotIn("\x1b", out.getvalue())


class JobsSectionBoundaryTests(unittest.TestCase):
    def kinds(self, text):
        return [(r["job"], r["kind"]) for r in audit_runs_on.classify_workflow(text)]

    def test_jobs_section_ends_at_the_next_top_level_key(self):
        text = "jobs:\n  a:\n    runs-on: ubuntu-latest\nenv:\n  b:\n    runs-on: [self-hosted]\n"
        self.assertEqual(self.kinds(text), [("a", "github-hosted")])

    def test_a_line_at_job_level_that_is_not_a_job_key_is_ignored(self):
        text = "jobs:\n  a:\n    runs-on: ubuntu-latest\n  - stray\n  b:\n    runs-on: [self-hosted]\n"
        self.assertEqual(self.kinds(text), [("a", "github-hosted"), ("b", "self-hosted")])

    def test_a_less_indented_line_inside_jobs_is_ignored(self):
        text = "jobs:\n    a:\n  odd: 1\n        runs-on: ubuntu-latest\n"
        self.assertEqual(self.kinds(text), [("a", "github-hosted")])

    def test_blank_and_comment_lines_inside_a_block_runs_on_are_skipped(self):
        text = "jobs:\n  a:\n    runs-on:\n\n      # note\n      group: ci\n"
        self.assertEqual(self.kinds(text), [("a", "self-hosted")])


class YamlSpellingTests(unittest.TestCase):
    """Valid YAML that the line reader must not silently misread or drop."""

    def rows(self, text):
        return {r["job"]: r for r in audit_runs_on.classify_workflow(text)}

    def test_a_sequence_at_the_same_indent_as_runs_on_is_read(self):
        rows = self.rows("jobs:\n  a:\n    runs-on:\n    - ubuntu-latest\n    steps:\n    - run: x\n  b:\n    runs-on:\n    - self-hosted\n    - linux\n")
        self.assertEqual(rows["a"]["kind"], "github-hosted")
        self.assertNotIn("run", rows["a"]["value"])
        self.assertEqual(rows["b"]["kind"], "self-hosted")

    def test_flow_style_jobs_are_reported_not_dropped(self):
        rows = self.rows("jobs:\n  a: {runs-on: ubuntu-latest, steps: []}\n  b: {runs-on: [self-hosted, linux]}\n  c: {uses: org/repo/.github/workflows/x.yml@main}\n  d:\n    runs-on: ubuntu-latest\n")
        self.assertEqual({k: v["kind"] for k, v in rows.items()}, {"a": "github-hosted", "b": "self-hosted", "c": "reusable", "d": "github-hosted"})

    def test_a_job_with_an_unreadable_value_is_listed_as_dynamic(self):
        rows = self.rows("jobs:\n  a: *shared\n  b:\n    runs-on: ubuntu-latest\n")
        self.assertEqual(rows["a"]["kind"], "dynamic")
        self.assertEqual(rows["b"]["kind"], "github-hosted")

    def test_quoted_job_keys_are_read(self):
        rows = self.rows("jobs:\n  'a':\n    runs-on: ubuntu-latest\n  \"b\":\n    runs-on: [self-hosted]\n")
        self.assertEqual({k: v["kind"] for k, v in rows.items()}, {"a": "github-hosted", "b": "self-hosted"})

    def test_a_utf8_byte_order_mark_does_not_hide_the_jobs_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_bytes(b"\xef\xbb\xbfjobs:\n  a:\n    runs-on: ubuntu-latest\n")
            self.assertEqual([r["kind"] for r in audit_runs_on.audit_directory(Path(tmp))], ["github-hosted"])


class WorkflowFileSelectionTests(unittest.TestCase):
    def test_only_yml_and_yaml_files_are_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            for name in ("a.yml", "b.yaml", "c.yxml", "d.yaml.ml", "e.yml.bak", "f.yml.yml"):
                (wf / name).write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n")
            self.assertEqual([p.name for p in audit_runs_on.workflow_files(Path(tmp))], ["a.yml", "b.yaml", "f.yml.yml"])


class CommandLineTests(unittest.TestCase):
    def test_help_prints_usage_instead_of_treating_it_as_a_path(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = audit_runs_on.main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("audit_runs_on.py [REPO_DIR]", out.getvalue())

    def test_non_ascii_names_and_comments_survive_an_ascii_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "构建.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest  # 构建\n", encoding="utf-8")
            env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
            proc = subprocess.run([sys.executable, "-X", "utf8=0", str(SCRIPT), tmp], capture_output=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn(b"github-hosted", proc.stdout)

    def test_main_replaces_unencodable_characters_on_a_strict_ascii_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "构建.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
            raw = io.BytesIO()
            stream = io.TextIOWrapper(raw, encoding="ascii", errors="strict")
            with redirect_stdout(stream):
                code = audit_runs_on.main([tmp])
            stream.flush()
        self.assertEqual(code, 0)
        self.assertIn(b"github-hosted", raw.getvalue())


class ScriptEntryPointTests(unittest.TestCase):
    def test_running_the_file_as_a_program_exits_with_the_main_return_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with mock.patch.object(sys, "argv", [str(SCRIPT), tmp]), redirect_stdout(out), self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("no workflow files", out.getvalue())


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


class KindClassificationTests(unittest.TestCase):
    def kinds(self, runs_on):
        rows = audit_runs_on.classify_workflow(f"jobs:\n  a:\n    runs-on: {runs_on}\n")
        return rows[0]["kind"]

    def test_each_runner_value_maps_to_exactly_one_kind(self):
        cases = {
            "ubuntu-latest": "github-hosted",
            "macos-14": "github-hosted",
            "windows-2022": "github-hosted",
            "self-hosted": "self-hosted",
            "[self-hosted, linux]": "self-hosted",
            "{group: big-runners}": "self-hosted",
            "my-custom-label": "dynamic",
            "ubuntu-${{ matrix.version }}": "dynamic",
            "[self-hosted, ${{ matrix.os }}]": "dynamic",
            "${{ matrix.os }}": "dynamic",
        }
        for value, kind in cases.items():
            with self.subTest(runs_on=value):
                self.assertEqual(self.kinds(value), kind)


class GroupWordBoundaryTests(unittest.TestCase):
    def test_group_is_a_whole_word_not_a_prefix_of_another_label(self):
        kind = lambda value: audit_runs_on.classify_workflow(f"jobs:\n  a:\n    runs-on: {value}\n")[0]["kind"]  # noqa: E731
        self.assertEqual(kind("groupie"), "dynamic")
        self.assertEqual(kind("ubuntu-groupie"), "github-hosted")
        self.assertEqual(kind("{group: big}"), "self-hosted")


class RowShapeTests(unittest.TestCase):
    def test_rows_have_exactly_job_kind_and_value(self):
        text = "jobs:\n  a:\n    runs-on: ubuntu-latest\n  b:\n    uses: ./.github/workflows/x.yml\n  c:\n    name: no runner\n"
        self.assertEqual(audit_runs_on.classify_workflow(text), [
            {"job": "a", "kind": "github-hosted", "value": "ubuntu-latest"},
            {"job": "b", "kind": "reusable", "value": "./.github/workflows/x.yml"},
            {"job": "c", "kind": "dynamic", "value": ""},
        ])

    def test_a_job_with_only_a_comment_after_its_key_has_an_empty_value(self):
        self.assertEqual(audit_runs_on.classify_workflow("jobs:\n  a: # later\n"), [{"job": "a", "kind": "dynamic", "value": ""}])

    def test_quotes_around_an_inline_runs_on_are_removed(self):
        for source in ('{runs-on: "ubuntu-latest"}', "{runs-on: 'ubuntu-latest'}"):
            with self.subTest(source=source):
                rows = audit_runs_on.classify_workflow(f"jobs:\n  a: {source}\n")
                self.assertEqual(rows, [{"job": "a", "kind": "github-hosted", "value": "ubuntu-latest"}])

    def test_a_value_that_repeats_the_key_is_kept_whole(self):
        rows = audit_runs_on.classify_workflow("jobs:\n  a:\n    uses: ./w/uses:y.yml\n  b:\n    runs-on: x runs-on: y\n")
        self.assertEqual([r["value"] for r in rows], ["./w/uses:y.yml", "x runs-on: y"])

    def test_block_sequences_are_joined_with_single_spaces_and_may_follow_a_comment(self):
        text = "jobs:\n  a:\n    runs-on: # which runner\n      - self-hosted\n      - linux\n"
        self.assertEqual(audit_runs_on.classify_workflow(text), [{"job": "a", "kind": "self-hosted", "value": "- self-hosted - linux"}])


class LayoutTolerance(unittest.TestCase):
    def test_a_comment_in_column_zero_does_not_end_the_jobs_section(self):
        text = "jobs:\n  a:\n    runs-on: ubuntu-latest\n# note\n  b:\n    runs-on: self-hosted\n"
        self.assertEqual([r["job"] for r in audit_runs_on.classify_workflow(text)], ["a", "b"])

    def test_windows_line_endings_leave_no_carriage_returns_in_values(self):
        text = "jobs:\r\n  a:\r\n    runs-on: ubuntu-latest\r\n  b:\r\n    runs-on:\r\n      - self-hosted\r\n"
        rows = audit_runs_on.classify_workflow(text)
        self.assertEqual([(r["job"], r["kind"], r["value"]) for r in rows], [("a", "github-hosted", "ubuntu-latest"), ("b", "self-hosted", "- self-hosted")])


class SanitizerAndSizeTests(unittest.TestCase):
    def test_every_unsafe_category_is_replaced(self):
        self.assertEqual(audit_runs_on._printable("a\x1bb\u202ec\u2028d\u2029e\ud800f\ue000g\u0378h", 40), "a?b?c?d?e?f?g?h")

    def write_workflow(self, root, name, size):
        wf = Path(root) / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        head = "jobs:\n  a:\n    runs-on: ubuntu-latest\n#"
        (wf / name).write_text(head + "x" * (size - len(head)))

    def test_the_size_limit_is_one_million_bytes_inclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_workflow(tmp, "exact.yml", 1_000_000)
            self.write_workflow(tmp, "over.yml", 1_000_001)
            self.assertEqual([p.name for p in audit_runs_on.workflow_files(Path(tmp))], ["exact.yml"])

    def test_a_file_with_invalid_utf8_is_still_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "a.yml").write_bytes(b"jobs:\n  a:\n    runs-on: ubuntu-latest # \xff\xfe\n")
            rows = audit_runs_on.audit_directory(Path(tmp))
        self.assertEqual([(r["job"], r["kind"]) for r in rows], [("a", "github-hosted")])


class CommandLineSummaryTests(unittest.TestCase):
    def test_short_help_flag_prints_usage(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(audit_runs_on.main(["-h"]), 0)
        self.assertIn("audit_runs_on.py [REPO_DIR]", out.getvalue())

    def test_the_summary_counts_only_github_hosted_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "a.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n  b:\n    runs-on: self-hosted\n  c:\n    runs-on: self-hosted\n")
            out = io.StringIO()
            with redirect_stdout(out):
                code = audit_runs_on.main([tmp])
        self.assertEqual(code, 0)
        self.assertIn("1 of 3 jobs use GitHub-hosted runners", out.getvalue())


class OutputFormatTests(unittest.TestCase):
    def test_a_row_is_three_padded_columns_cut_at_28_28_and_60_then_the_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / ("f" * 35 + ".yml")).write_text(f'jobs:\n  "{"j" * 40}":\n    runs-on: ubuntu-{"x" * 80}\n  short:\n    runs-on: self-hosted\n')
            out = io.StringIO()
            with redirect_stdout(out):
                audit_runs_on.main([tmp])
        first, second = out.getvalue().split("\n")[:2]
        self.assertEqual(first, f"{'f' * 28} {'j' * 28} {'github-hosted':14s} {('ubuntu-' + 'x' * 80)[:60]}")
        self.assertEqual(second, f"{'f' * 28} {'short':28s} {'self-hosted':14s} self-hosted")


class InlineReusableTests(unittest.TestCase):
    def test_an_inline_job_calling_a_workflow_keeps_only_the_path_as_its_value(self):
        rows = audit_runs_on.classify_workflow("jobs:\n  a: {uses: ./.github/workflows/x.yml, with: {k: v}}\n")
        self.assertEqual(rows, [{"job": "a", "kind": "reusable", "value": "./.github/workflows/x.yml"}])


class ReusableCommentTests(unittest.TestCase):
    def test_a_trailing_comment_is_not_part_of_the_called_workflow(self):
        rows = audit_runs_on.classify_workflow("jobs:\n  a:\n    uses: ./.github/workflows/x.yml # shared build\n")
        self.assertEqual(rows, [{"job": "a", "kind": "reusable", "value": "./.github/workflows/x.yml"}])

    def test_a_hash_without_a_space_before_it_belongs_to_the_value(self):
        rows = audit_runs_on.classify_workflow("jobs:\n  a:\n    uses: org/repo/.github/workflows/x.yml@v1#tag\n")
        self.assertEqual(rows[0]["value"], "org/repo/.github/workflows/x.yml@v1#tag")


class CommentAfterQuotesTests(unittest.TestCase):
    def value(self, line):
        return audit_runs_on.classify_workflow(f"jobs:\n  a:\n    {line}\n")[0]["value"]

    def test_a_comment_after_a_closed_quoted_value_is_removed(self):
        self.assertEqual(self.value('runs-on: "ubuntu-latest" # note'), '"ubuntu-latest"')
        self.assertEqual(self.value("uses: './x.yml' # note"), "'./x.yml'")

    def test_an_empty_quoted_value_ends_at_its_second_quote(self):
        self.assertEqual(self.value('runs-on: "" # note'), '""')
        self.assertEqual(self.value("runs-on: '' # note"), "''")

    def test_an_apostrophe_inside_a_plain_value_does_not_start_a_quote(self):
        self.assertEqual(self.value("runs-on: it's-mine # self-hosted"), "it's-mine")


class HashInsideQuotesTests(unittest.TestCase):
    def value(self, line):
        return audit_runs_on.classify_workflow(f"jobs:\n  a:\n    {line}\n")[0]["value"]

    def test_a_hash_inside_a_quoted_value_is_not_a_comment(self):
        self.assertEqual(self.value('uses: "./.github/workflows/build #1.yml"'), '"./.github/workflows/build #1.yml"')
        self.assertEqual(self.value("runs-on: 'my #label'"), "'my #label'")

    def test_a_real_comment_after_a_quoted_value_with_a_hash_is_still_removed(self):
        self.assertEqual(self.value("uses: './x #1.yml' # shared"), "'./x #1.yml'")

    def test_an_escaped_double_quote_does_not_end_the_quoted_value(self):
        self.assertEqual(self.value(r'runs-on: "a \" # b" # c'), r'"a \" # b"')

    def test_a_quoted_label_inside_a_flow_sequence_may_hold_a_hash(self):
        self.assertEqual(self.value("runs-on: [self-hosted, 'a #b'] # c"), "[self-hosted, 'a #b']")


class QuotesInPlainAndFlowValuesTests(unittest.TestCase):
    def value(self, line):
        return audit_runs_on.classify_workflow(f"jobs:\n  a:\n    {line}\n")[0]["value"]

    def test_a_quote_pair_inside_a_plain_value_is_ordinary_text(self):
        self.assertEqual(self.value("runs-on: a 'b' # c"), "a 'b'")

    def test_a_quoted_value_in_an_inline_job_may_hold_a_hash(self):
        rows = audit_runs_on.classify_workflow('jobs:\n  a: {runs-on: "x #y"}\n')
        self.assertEqual(rows, [{"job": "a", "kind": "dynamic", "value": "x #y"}])


class QuoteBoundaryTests(unittest.TestCase):
    def value(self, line):
        return audit_runs_on.classify_workflow(f"jobs:\n  a:\n    {line}\n")[0]["value"]

    def test_a_doubled_single_quote_is_an_escaped_apostrophe_not_the_end_of_the_value(self):
        self.assertEqual(self.value("runs-on: 'it''s #label' # note"), "'it''s #label'")

    def test_a_quote_after_a_closed_quoted_value_is_not_a_new_scalar_boundary(self):
        self.assertEqual(self.value("runs-on: \"a\" 'b # c"), "\"a\" 'b")

    def test_a_hyphen_is_a_sequence_marker_only_at_the_start_and_before_whitespace(self):
        self.assertEqual(self.value("runs-on: a - 'b # c"), "a - 'b")
        self.assertEqual(self.value("runs-on: -'y #z'"), "-'y")
        self.assertEqual(self.value("runs-on: - 'z #w' # c"), "- 'z #w'")

    def test_a_quote_inside_a_started_plain_value_does_not_hide_the_comment(self):
        self.assertEqual(self.value("runs-on: foo 'bar # comment"), "foo 'bar")
        self.assertEqual(self.value('runs-on: foo "bar # comment'), 'foo "bar')


class QuotedBlockSequenceItemTests(unittest.TestCase):
    def test_a_quoted_item_of_a_block_sequence_may_hold_a_hash(self):
        text = "jobs:\n  a:\n    runs-on:\n      - 'my #label' # one\n      - \"self-hosted\" # two\n"
        self.assertEqual(audit_runs_on.classify_workflow(text),
                         [{"job": "a", "kind": "self-hosted", "value": "- 'my #label' - \"self-hosted\""}])


if __name__ == "__main__":
    unittest.main()
