"""Tests for check_markdown_links.py: local Markdown links and heading anchors."""

import hashlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "source-of-truth" / "scripts" / "check_markdown_links.py"
sys.path.insert(0, str(SCRIPT.parent))

import check_markdown_links as links  # noqa: E402


def make_repo(files):
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return directory, root


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = links.main(argv)
    return code, out.getvalue(), err.getvalue()


class LinkExtractionTests(unittest.TestCase):
    def test_finds_inline_links_and_ignores_images_and_external_links(self):
        text = "[guide](guide.md) ![diagram](image.png) [site](https://example.com) [mail](mailto:a@b.c)"
        self.assertEqual(list(links.markdown_links(text)), ["guide.md"])

    def test_a_link_title_is_not_part_of_the_target(self):
        self.assertEqual(list(links.markdown_links('[a](guide.md "The guide") [b](<spaced.md>)')), ["guide.md", "spaced.md"])

    def test_links_inside_fenced_code_blocks_are_examples_not_links(self):
        text = "[real](real.md)\n```\n[example](example.md)\n```\n~~~md\n[other](other.md)\n~~~\n[after](after.md)\n"
        self.assertEqual(list(links.markdown_links(text)), ["real.md", "after.md"])

    def test_links_inside_inline_code_are_examples_not_links(self):
        self.assertEqual(list(links.markdown_links("Write `[text](path.md)` like [this](real.md).")), ["real.md"])

    def test_an_anchor_only_link_is_a_local_link(self):
        self.assertEqual(list(links.markdown_links("[top](#top)")), ["#top"])


class AnchorTests(unittest.TestCase):
    def test_heading_anchors_normalize_text_and_disambiguate_repeats(self):
        self.assertEqual(
            links.heading_anchors("# Score: details\n## Score: details\n## Second Term"),
            {"score-details", "score-details-1", "second-term"},
        )

    def test_headings_inside_fenced_code_blocks_are_not_anchors(self):
        self.assertEqual(links.heading_anchors("# Real\n```\n# Not a heading\n```\n"), {"real"})


class CheckDocumentsTests(unittest.TestCase):
    def test_reports_missing_paths_and_missing_anchors(self):
        directory, root = make_repo({"README.md": "[missing](nope.md) [anchor](guide.md#absent)\n", "guide.md": "# Present\n"})
        with directory:
            errors = links.check_documents(root, [root / "README.md", root / "guide.md"])
        self.assertEqual(
            errors,
            ["README.md: missing link target: nope.md", "README.md: missing heading anchor: guide.md#absent"],
        )

    def test_accepts_relative_paths_and_case_insensitive_anchors(self):
        directory, root = make_repo({"README.md": "[a](guide.md#hello-world) [b](#intro)\n# Intro\n", "guide.md": "# Hello World\n"})
        with directory:
            self.assertEqual(links.check_documents(root, [root / "README.md"]), [])

    def test_a_link_that_leaves_the_repository_is_an_error(self):
        directory, root = make_repo({"inner/README.md": "[out](../../outside.md)\n"})
        with directory:
            errors = links.check_documents(root / "inner", [root / "inner" / "README.md"])
        self.assertEqual(errors, ["README.md: link escapes repository: ../../outside.md"])

    def test_a_directory_target_is_accepted_without_an_anchor_check(self):
        directory, root = make_repo({"README.md": "[docs](docs/)\n", "docs/guide.md": "# Guide\n"})
        with directory:
            self.assertEqual(links.check_documents(root, [root / "README.md"]), [])


class DiscoveryTests(unittest.TestCase):
    def test_document_discovery_skips_dependency_and_generated_directories(self):
        files = {name: "# Document\n" for name in ("docs/guide.md", "node_modules/dep/README.md", ".git/notes.md", "target/doc.md")}
        directory, root = make_repo(files)
        with directory:
            found = [path.relative_to(root).as_posix() for path in links.markdown_documents(root)]
        self.assertEqual(found, ["docs/guide.md"])


class CommandLineTests(unittest.TestCase):
    def test_checks_the_directory_given_as_an_argument(self):
        directory, root = make_repo({"README.md": "[ok](guide.md)\n", "guide.md": "# Guide\n"})
        with directory:
            code, out, err = run_main([str(root)])
        self.assertEqual((code, out, err), (0, "Checked local Markdown links in 2 files.\n", ""))

    def test_reports_errors_on_stderr_and_fails(self):
        directory, root = make_repo({"README.md": "[gone](gone.md)\n"})
        with directory:
            code, out, err = run_main([str(root)])
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, "README.md: missing link target: gone.md\n")

    def test_defaults_to_the_current_directory(self):
        directory, root = make_repo({"README.md": "# Only\n"})
        previous = os.getcwd()
        os.chdir(root)
        try:
            with directory:
                code, out, _ = run_main([])
        finally:
            os.chdir(previous)
        self.assertEqual((code, out), (0, "Checked local Markdown links in 1 file.\n"))

    def test_a_missing_directory_is_a_usage_error(self):
        code, out, err = run_main(["/nonexistent/path/for/the/check"])
        self.assertEqual((code, out), (2, ""))
        self.assertIn("not a directory", err)

    def test_it_never_modifies_the_files_it_reads(self):
        directory, root = make_repo({"README.md": "[gone](gone.md)\n", "guide.md": "# Guide\n"})
        with directory:
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            run_main([str(root)])
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
