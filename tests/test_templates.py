"""Run the shell blocks of the workflow templates for real, with fakes for docker and the test command."""

import os
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

    def run_audit(self, info_exit=0):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp, "bin")
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text(self.FAKE_DOCKER)
            docker.chmod(0o755)
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

    def test_an_exit_in_the_test_command_does_not_end_the_whole_job(self):
        proc, _ = self.run_repeat("exit 3")
        self.assertIn("SUMMARY failures=2 of 2", proc.stdout)


if __name__ == "__main__":
    unittest.main()
