"""Repo hygiene: no private data in the plugin, valid manifests, read-only templates."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

# A published plugin must stay generic: no project names, internal addresses,
# or credentials. Add a pattern here the moment a new kind of leak is possible.
FORBIDDEN = {
    "private LAN address": r"\b10\.0\.0\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b",
    "tailscale address": r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b",
    "github token": r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
    "aws key": r"\bAKIA[0-9A-Z]{16}\b",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "personal email": r"[\w.+-]+@(gmail|qq|163|outlook)\.com",
    "password assignment": r"(?i)\b(password|passwd|secret|token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]",
}
# Project/host names that must never be baked into the shared plugin. Kept as
# fragments joined at runtime so this file does not trip its own check.
FORBIDDEN_WORDS = ["new" + "-magnet", "right" + "here", "hao" + "lab", "1pass" + "word", "magne" + "tu"]

# Commands a read-only audit template must never contain.
DESTRUCTIVE = [r"\brm\s+-", r"\bprune\b", r"volume\s+rm", r"\bkill\b", r"\bdrop\s+database\b", r"\bmkfs\b"]


def text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix in {".pyc"}:
            continue
        if path == SELF or "__pycache__" in path.parts:
            continue
        yield path


class PrivacyTests(unittest.TestCase):
    def test_no_private_data(self):
        problems = []
        for path in text_files():
            body = path.read_text(errors="ignore")
            for label, pattern in FORBIDDEN.items():
                if re.search(pattern, body):
                    problems.append(f"{path.relative_to(ROOT)}: {label}")
            for word in FORBIDDEN_WORDS:
                if word in body.lower():
                    problems.append(f"{path.relative_to(ROOT)}: forbidden word {word!r}")
        self.assertEqual(problems, [])


class ManifestTests(unittest.TestCase):
    def test_marketplace_lists_existing_plugins(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertRegex(market["name"], r"^[a-z0-9][a-z0-9-]*$")
        self.assertTrue(market["plugins"])
        for entry in market["plugins"]:
            plugin_dir = ROOT / entry["source"]
            manifest = plugin_dir / ".claude-plugin" / "plugin.json"
            self.assertTrue(manifest.exists(), f"missing {manifest}")
            data = json.loads(manifest.read_text())
            self.assertEqual(data["name"], entry["name"])
            self.assertRegex(data["version"], r"^\d+\.\d+\.\d+$")

    def test_every_skill_has_frontmatter_with_name_and_description(self):
        skills = list((ROOT / "plugins").glob("*/skills/*/SKILL.md"))
        self.assertTrue(skills, "no skills found")
        for skill in skills:
            body = skill.read_text()
            match = re.match(r"^---\n(.*?)\n---\n", body, re.S)
            self.assertIsNotNone(match, f"{skill} has no frontmatter")
            front = match.group(1)
            self.assertIn(f"name: {skill.parent.name}", front)
            self.assertRegex(front, r"(?m)^description: .{40,}")


class ReadOnlyTemplateTests(unittest.TestCase):
    def test_audit_template_has_no_destructive_commands(self):
        template = ROOT / "plugins" / "ci-perf" / "skills" / "self-hosted-runner-health" / "templates" / "runner-readonly-audit.yml"
        self.assertTrue(template.exists())
        body = template.read_text()
        for pattern in DESTRUCTIVE:
            self.assertIsNone(re.search(pattern, body, re.I), f"destructive pattern {pattern!r} in audit template")

    def test_templates_use_placeholders_not_real_values(self):
        for template in (ROOT / "plugins" / "ci-perf" / "skills").glob("*/templates/*.yml"):
            self.assertRegex(template.read_text(), r"__[A-Z_]+__", f"{template.name} has no placeholders")


if __name__ == "__main__":
    unittest.main()
