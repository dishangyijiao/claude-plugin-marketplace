"""Run the shell blocks of the workflow templates for real, with fakes for docker and the test command."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "ci-perf" / "skills"
REPEAT = SKILLS / "flaky-test-hunt" / "templates" / "repeat-tests.yml"
AUDIT = SKILLS / "self-hosted-runner-health" / "templates" / "runner-readonly-audit.yml"


def run_block(template: Path) -> str:
    """The body of the first multi-line `run: |` step, dedented to column 0."""
    body = template.read_text().split("        run: |\n", 1)[1]
    lines = []
    for line in body.splitlines():
        if line.strip() and not line.startswith(" " * 10):
            break  # next step
        lines.append(line[10:])
    return "\n".join(lines)


class AuditVolumeCountTests(unittest.TestCase):
    """The audit template with a scripted `docker`: counts must follow the three-condition rule."""

    HEX_A = "a" * 64   # anonymous label, dangling
    HEX_B = "b" * 64   # looks anonymous but has no label, dangling
    NAMED = "pgdata"   # named volume, referenced by nobody

    FAKE_DOCKER = """#!/bin/sh
case "$*" in
  "info") exit ${DOCKER_INFO_EXIT:-0} ;;
  "volume ls -q") printf '%s\\n' @A @B @NAMED ;;
  "volume ls -q -f dangling=true") printf '%s\\n' @A @B ;;
  "volume ls -q -f dangling=true -f label=com.docker.volume.anonymous") printf '%s\\n' @A ;;
  "ps -aq") ;;
  *) ;;
esac
""".replace("@A", HEX_A).replace("@B", HEX_B).replace("@NAMED", NAMED)

    def run_audit(self, info_exit=0, fakes=None):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp, "bin")
            fake_bin.mkdir()
            for name, body in {"docker": self.FAKE_DOCKER, **(fakes or {})}.items():
                (fake_bin / name).write_text(body)
                (fake_bin / name).chmod(0o755)
            env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}", HOME=tmp, RUNNER_NAME="r", DOCKER_INFO_EXIT=str(info_exit))
            proc = subprocess.run(["bash", "-c", run_block(AUDIT)], env=env, capture_output=True, text=True, cwd=tmp)
        return proc

    def test_counts_follow_dangling_hex_name_and_anonymous_label(self):
        out = self.run_audit().stdout
        self.assertIn("total volumes:                           3", out)
        self.assertIn("unreferenced (dangling):                 2", out)
        self.assertIn("dangling AND 64-hex name:                2", out)
        self.assertIn("dangling AND 64-hex AND anonymous label: 1", out)
        self.assertIn("named volumes:                           1", out)
        self.assertIn(self.NAMED, out)

    def test_unreachable_daemon_is_reported_not_shown_as_zero_counts(self):
        out = self.run_audit(info_exit=1).stdout.lower()
        self.assertIn("docker daemon is not reachable", out)
        self.assertNotIn("total volumes:", out)

    # `du` is the only command whose output carries attacker-controlled file names.
    HOSTILE_DU = """#!/bin/sh
case "$*" in
  *"/var/log"*) echo "1K	/var/log" ;;
  *) printf '4K\tinnocent\\n   ::add-mask::hunter2\\n::stop-commands::x\\n' ;;
esac
"""

    def test_directory_names_cannot_inject_workflow_commands_into_the_log(self):
        out = self.run_audit(fakes={"du": self.HOSTILE_DU}).stdout
        injected = [l for l in out.splitlines() if l.lstrip().startswith("::") and not l.startswith(("::group::", "::endgroup::"))]
        self.assertEqual(injected, [])
        self.assertIn("__::add-mask::hunter2", out)

    def test_each_du_listing_is_filtered(self):
        out = self.run_audit(fakes={"du": self.HOSTILE_DU}).stdout
        self.assertEqual(out.count("__::stop-commands::x"), 3, out)

    def test_without_docker_the_audit_says_so_and_still_finishes(self):
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp, "bin")
            bin_dir.mkdir()
            for tool in ("bash", "sed", "du", "df", "sort", "head", "grep", "id", "cat", "tr", "wc", "xargs", "uniq", "cut"):
                (bin_dir / tool).symlink_to(shutil.which(tool))
            env = {"PATH": str(bin_dir), "HOME": tmp, "RUNNER_NAME": "r"}
            proc = subprocess.run([str(bin_dir / "bash"), "-c", run_block(AUDIT)], env=env, capture_output=True, text=True, cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("docker not installed on this runner", proc.stdout)
        self.assertIn("system directories and logs", proc.stdout)


class RepeatTestsTemplateTests(unittest.TestCase):
    """The repeat-tests template with a harmless test command in place of the real one."""

    def run_repeat(self, test_command, runs="2"):
        script = run_block(REPEAT).replace("__TEST_COMMAND__", test_command)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "bin").mkdir()
            nproc = Path(tmp, "bin", "nproc")
            nproc.write_text("#!/bin/sh\necho 1\n")
            nproc.chmod(0o755)
            Path(tmp, "work", "sub").mkdir(parents=True)
            env = dict(os.environ, PATH=f"{tmp}/bin:{os.environ['PATH']}", RUNS=runs,
                       RUNNER_TEMP=f"{tmp}/temp", RUNNER_NAME="r", CI="true")
            proc = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
                                  env=env, capture_output=True, text=True, cwd=f"{tmp}/work")
            logs = {f.name: f.read_text() for f in Path(tmp, "temp", "repeat-logs").glob("run-*.log")}
        return proc, logs

    def test_runs_must_be_between_1_and_999(self):
        for runs in ("0", "1000"):
            with self.subTest(runs=runs):
                proc, _ = self.run_repeat("true", runs=runs)
                self.assertEqual(proc.returncode, 2)
                self.assertNotIn("SUMMARY", proc.stdout)

    def test_failing_runs_are_counted_and_do_not_stop_the_loop(self):
        proc, _ = self.run_repeat("false", runs="3")
        self.assertIn("SUMMARY failures=3 of 3", proc.stdout)

    def test_a_directory_change_in_one_run_does_not_leak_into_the_next(self):
        proc, _ = self.run_repeat("cd sub && pwd")
        self.assertEqual(proc.stdout.count("exit=0"), 2, proc.stdout)

    def test_every_part_of_a_compound_command_is_logged(self):
        _, logs = self.run_repeat("echo first; echo second; false", runs="1")
        self.assertIn("first", logs["run-1.log"])
        self.assertIn("second", logs["run-1.log"])

    def test_a_trailing_comment_in_the_test_command_does_not_break_the_script(self):
        proc, logs = self.run_repeat("echo hi  # the real suite", runs="1")
        self.assertIn("SUMMARY failures=0 of 1", proc.stdout, proc.stderr)
        self.assertIn("hi", logs["run-1.log"])

    def test_a_multiline_test_command_with_a_heredoc_works(self):
        proc, logs = self.run_repeat("cat <<EOT\nline one\nEOT\nfalse", runs="1")
        self.assertIn("SUMMARY failures=1 of 1", proc.stdout, proc.stderr)
        self.assertIn("line one", logs["run-1.log"])

    def test_test_output_cannot_inject_workflow_commands_into_the_log(self):
        proc, _ = self.run_repeat("echo '   ::add-mask::hunter2'; echo 'FAIL x ::stop-commands::'; exit 1", runs="1")
        injected = [l for l in proc.stdout.splitlines() if l.lstrip().startswith("::") and not l.startswith(("::group::", "::endgroup::"))]
        self.assertEqual(injected, [], proc.stdout)
        self.assertIn("__::add-mask::hunter2", proc.stdout)

    def test_failure_section_shows_first_40_matches_and_tail_shows_last_40_lines(self):
        proc, _ = self.run_repeat("for n in $(seq 1 100); do echo \"FAIL $n\"; done; exit 1", runs="1")
        self.assertIn("40:FAIL 40", proc.stdout)
        self.assertNotIn("41:FAIL 41", proc.stdout)
        tail = proc.stdout.split("last 40 lines of run 1 ----", 1)[1]
        self.assertIn("FAIL 61", tail)
        self.assertNotIn("FAIL 60\n", tail)

    def test_only_failed_runs_leave_a_failed_log_for_the_artifact(self):
        script = run_block(REPEAT).replace("__TEST_COMMAND__", 'test "$(cat n 2>/dev/null || echo 0)" != 1 && { echo 1 > n; exit 1; }; true')
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, RUNS="3", RUNNER_TEMP=f"{tmp}/temp", RUNNER_NAME="r", CI="true")
            subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script], env=env, capture_output=True, text=True, cwd=tmp)
            names = sorted(f.name for f in Path(tmp, "temp", "repeat-logs").glob("FAILED-*.log"))
        self.assertEqual(names, ["FAILED-run-1.log"])

    def test_an_exit_in_the_test_command_does_not_end_the_whole_job(self):
        proc, _ = self.run_repeat("exit 3")
        self.assertIn("SUMMARY failures=2 of 2", proc.stdout)


@unittest.skipUnless(shutil.which("ruby"), "ruby is not installed")
class TemplateYamlTests(unittest.TestCase):
    """Filled-in templates must be valid workflows with the safety settings the docs promise."""

    FILL = {"__BRANCH__": "tmp-audit", "__RUNNER_GROUP__": "ci", "__RUNNER_LABELS__": "[linux, x64]",
            "__SETUP_COMMAND__": "npm ci", "__RUNS__": "7", "__TEST_COMMAND__": "npm test"}

    def load(self, template):
        text = template.read_text()
        for key, value in self.FILL.items():
            text = text.replace(key, value)
        proc = subprocess.run(["ruby", "-ryaml", "-rjson", "-e", "puts JSON.generate(YAML.safe_load(STDIN.read))"],
                              input=text, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        if "true" in doc:  # YAML 1.1 reads the key `on` as a boolean; GitHub treats it as "on"
            doc["on"] = doc.pop("true")
        return doc

    def test_both_templates_parse_after_filling_in_the_placeholders(self):
        for template in (REPEAT, AUDIT):
            with self.subTest(template=template.name):
                doc = self.load(template)
                self.assertEqual(doc["on"]["push"]["branches"], ["tmp-audit"])
                self.assertEqual(doc["permissions"], {"contents": "read"})
                job = next(iter(doc["jobs"].values()))
                self.assertEqual(job["runs-on"], {"group": "ci", "labels": ["linux", "x64"]})
                self.assertIn("timeout-minutes", job)

    def test_every_action_is_pinned_to_a_full_commit_sha(self):
        for template in (REPEAT, AUDIT):
            for step in next(iter(self.load(template)["jobs"].values()))["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"@[0-9a-f]{40}$", template.name)

    def test_the_checkout_does_not_persist_the_repository_token(self):
        steps = next(iter(self.load(REPEAT)["jobs"].values()))["steps"]
        checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
        self.assertIs(checkout["with"]["persist-credentials"], False)

    def test_the_test_command_is_documented_as_a_single_line(self):
        self.assertRegex(REPEAT.read_text().split("name: repeat tests")[0], r"__TEST_COMMAND__[^\n]*single line|single line[^\n]*__TEST_COMMAND__")


if __name__ == "__main__":
    unittest.main()
