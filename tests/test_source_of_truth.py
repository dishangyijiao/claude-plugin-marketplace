"""Structure tests for the source-of-truth plugin: skills, reference, templates, docs."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "source-of-truth"

SKILLS = ["scaffold", "review", "improve"]
LAYERS = ["PRD", "Requirements", "ADR", "Architecture", "Spec", "Code", "Tests", "Deploy", "Observe"]
STATES = ["required", "optional", "not applicable"]
TEMPLATE_SECTIONS = {
    "PRD.md": ["Problem", "Target Users", "Goals", "Non-Goals", "Scope", "User Journeys", "Success Criteria", "Constraints", "Related Requirements"],
    "REQ.md": ["Requirement", "Rationale", "Acceptance Criteria", "Traceability"],
    "ADR.md": ["Status", "Context", "Decision", "Alternatives Considered", "Rationale", "Consequences", "Related"],
    "SPEC.md": ["Related Requirements", "Preconditions", "Behavior", "Error Cases", "Boundary Conditions", "Observable Outputs", "Related Contracts", "Verification"],
    "AGENTS.md": ["Read Order", "Source-of-Truth Rules", "Change Policy", "Verification", "Safety"],
    "status.md": ["Layer status", "Duplicated or conflicting sources", "Risks", "To-do", "Not doing"],
    "sources.md": ["Where each fact lives"],
}


def read(path):
    assert path.exists(), f"missing {path.relative_to(ROOT)}"
    return path.read_text()


def headings(text):
    return [m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M)]


class SkillTests(unittest.TestCase):
    def test_the_three_skills_exist(self):
        for name in SKILLS:
            self.assertTrue((PLUGIN / "skills" / name / "SKILL.md").exists(), name)

    def test_each_description_says_when_to_use_the_skill(self):
        for name in SKILLS:
            body = read(PLUGIN / "skills" / name / "SKILL.md")
            description = re.search(r"(?m)^description: (.+)$", body).group(1)
            self.assertRegex(description, r"(?i)\buse (when|for)\b", name)

    def test_review_is_read_only_and_says_so(self):
        body = read(PLUGIN / "skills" / "review" / "SKILL.md")
        self.assertRegex(body, r"(?i)read-only")
        self.assertRegex(body, r"(?i)do not (create|write|edit|modify)")

    def test_every_skill_treats_repository_text_as_data(self):
        for name in SKILLS:
            self.assertRegex(read(PLUGIN / "skills" / name / "SKILL.md"), r"(?i)data,? not instructions", name)

    def test_every_skill_names_what_to_do_when_a_fact_cannot_be_recovered(self):
        for name in SKILLS:
            self.assertRegex(read(PLUGIN / "skills" / name / "SKILL.md"), r"Needs confirmation", name)

    def test_skills_hand_over_to_each_other(self):
        self.assertIn("review", read(PLUGIN / "skills" / "scaffold" / "SKILL.md"))
        self.assertIn("improve", read(PLUGIN / "skills" / "review" / "SKILL.md"))
        self.assertIn("review", read(PLUGIN / "skills" / "improve" / "SKILL.md"))

    def test_improve_uses_the_bundled_link_checker(self):
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/check_markdown_links.py", read(PLUGIN / "skills" / "improve" / "SKILL.md"))


class ReferenceTests(unittest.TestCase):
    def test_layers_lists_all_nine_layers_in_order(self):
        body = read(PLUGIN / "reference" / "layers.md")
        positions = [body.find(f"| {i} | {layer} |") for i, layer in enumerate(LAYERS, 1)]
        self.assertNotIn(-1, positions, positions)
        self.assertEqual(positions, sorted(positions))

    def test_layers_defines_the_three_applicability_states(self):
        body = read(PLUGIN / "reference" / "layers.md").lower()
        for state in STATES:
            self.assertIn(state, body)
        self.assertRegex(body, r"never create placeholder")

    def test_rules_cover_history_uncertainty_and_small_steps(self):
        body = read(PLUGIN / "reference" / "rules.md")
        for phrase in ["Superseded", "Needs confirmation", "independently reviewable", "Definition of done"]:
            self.assertIn(phrase, body)


class TemplateTests(unittest.TestCase):
    def test_each_template_has_its_required_sections(self):
        for name, sections in TEMPLATE_SECTIONS.items():
            found = headings(read(PLUGIN / "templates" / name))
            for section in sections:
                self.assertTrue(any(h.lower().startswith(section.lower()) for h in found), f"{name} lacks {section!r}")

    def test_the_adr_template_lists_every_status_and_the_confirmation_markers(self):
        body = read(PLUGIN / "templates" / "ADR.md")
        for status in ["Proposed", "Accepted", "Deprecated", "Superseded", "Rejected"]:
            self.assertIn(status, body)
        for marker in ["Confirmed by the owner", "Needs confirmation", "Historical rationale unavailable"]:
            self.assertIn(marker, body)

    def test_templates_use_placeholders_not_real_values(self):
        for name in TEMPLATE_SECTIONS:
            self.assertRegex(read(PLUGIN / "templates" / name), r"__[A-Z_]+__", name)


class RegistrationTests(unittest.TestCase):
    def test_both_readmes_describe_the_plugin(self):
        for name in ["README.md", "README.zh-CN.md"]:
            body = read(ROOT / name)
            self.assertIn("source-of-truth", body, name)
            for skill in SKILLS:
                self.assertIn(f"source-of-truth:{skill}", body, name)

    def test_agents_md_lists_the_plugin_layout(self):
        self.assertIn("plugins/source-of-truth", read(ROOT / "AGENTS.md"))


if __name__ == "__main__":
    unittest.main()
