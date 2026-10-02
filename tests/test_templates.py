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


if __name__ == "__main__":
    unittest.main()
