"""Tests for check_markdown_links.py: local Markdown links and heading anchors."""

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import time
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

    def test_an_indented_fence_still_hides_the_links_inside_it(self):
        text = "   ```\n[example](example.md)\n   ```\n[after](after.md)\n"
        self.assertEqual(list(links.markdown_links(text)), ["after.md"])

    def test_a_shorter_fence_inside_a_longer_one_does_not_close_it(self):
        text = "````\n   ```\n[example](example.md)\n````\n[after](after.md)\n"
        self.assertEqual(list(links.markdown_links(text)), ["after.md"])

    def test_a_protocol_relative_url_is_external(self):
        self.assertEqual(list(links.markdown_links("[cdn](//example.com/x.js) [local](x.md)")), ["x.md"])

    def test_an_anchor_only_link_is_a_local_link(self):
        self.assertEqual(list(links.markdown_links("[top](#top)")), ["#top"])


    def test_a_target_with_balanced_parentheses_is_kept_whole(self):
        self.assertEqual(list(links.markdown_links("[a](docs/a_(b).md) then [c](plain.md)")), ["docs/a_(b).md", "plain.md"])

    def test_a_title_after_a_target_with_parentheses_is_dropped(self):
        self.assertEqual(list(links.markdown_links('[a](docs/a_(b).md "The title")')), ["docs/a_(b).md"])


    def test_an_external_target_that_cannot_be_parsed_is_skipped_not_fatal(self):
        self.assertEqual(list(links.markdown_links("[x](http://[oops) [y](real.md)")), ["real.md"])

    def test_a_code_span_may_run_over_several_lines(self):
        self.assertEqual(list(links.markdown_links("`code\n[x](in-span.md)\nmore` [y](real.md)\n")), ["real.md"])

    def test_a_fence_is_closed_only_by_a_fence_without_text_after_it(self):
        text = "```\n```python\n[x](inside.md)\n```\n[y](after.md)\n"
        self.assertEqual(list(links.markdown_links(text)), ["after.md"])

    def test_three_backticks_followed_by_text_with_backticks_are_a_code_span_not_a_fence(self):
        self.assertEqual(list(links.markdown_links("```inline``` and [x](real.md)\n[y](next.md)\n")), ["real.md", "next.md"])

    def test_an_indented_run_of_backticks_with_text_after_it_is_a_code_span_too(self):
        self.assertEqual(list(links.markdown_links("   ```inline``` and [x](real.md)\n[y](next.md)\n")), ["real.md", "next.md"])

    def test_a_tilde_fence_may_have_backticks_in_its_info_string(self):
        self.assertEqual(list(links.markdown_links("~~~ a`b\n[x](inside.md)\n~~~\n[y](after.md)\n")), ["after.md"])

    def test_a_fence_of_another_kind_inside_a_fence_does_not_close_it(self):
        self.assertEqual(list(links.markdown_links("```\n~~~\n[x](inside.md)\n```\n[y](after.md)\n")), ["after.md"])

    def test_front_matter_is_not_searched_for_links(self):
        self.assertEqual(list(links.markdown_links('---\nexample: "[x](missing.md)"\n---\n# T\n[y](real.md)\n')), ["real.md"])

    def test_a_badge_link_gives_its_target_and_not_the_image(self):
        self.assertEqual(list(links.markdown_links("[![build](badge.svg)](docs/a.md)")), ["docs/a.md"])

    def test_a_long_run_of_open_brackets_is_scanned_in_linear_time(self):
        started = time.monotonic()
        self.assertEqual(list(links.markdown_links("[" * 128000 + "](a")), [])
        self.assertLess(time.monotonic() - started, 1.0)


class AnchorTests(unittest.TestCase):
    def test_heading_anchors_normalize_text_and_disambiguate_repeats(self):
        self.assertEqual(
            links.heading_anchors("# Score: details\n## Score: details\n## Second Term"),
            {"score-details", "score-details-1", "second-term"},
        )

    def test_each_space_becomes_one_hyphen_and_punctuation_does_not_merge_them(self):
        # GitHub removes the ampersand but keeps both spaces; hyphens are kept as typed.
        self.assertEqual(links.heading_anchors("# A & B\n## A - B"), {"a--b", "a---b"})

    def test_setext_headings_are_anchors(self):
        text = "Top title\n=========\n\nSecond one\n----------\n\nSecond one\n----------\n"
        self.assertEqual(links.heading_anchors(text), {"top-title", "second-one", "second-one-1"})

    def test_atx_and_setext_headings_share_one_duplicate_count_in_document_order(self):
        text = "# Same\n\nSame\n====\n\n## Same\n"
        self.assertEqual(links.heading_anchors(text), {"same", "same-1", "same-2"})

    def test_a_table_separator_row_or_a_rule_after_a_blank_line_is_not_a_heading(self):
        text = "| a | b |\n|---|---|\n| 1 | 2 |\n\ntext\n\n---\n"
        self.assertEqual(links.heading_anchors(text), set())

    def test_a_front_matter_block_is_not_a_heading(self):
        # `title: x` over the closing `---` would otherwise look like a setext heading and add a false anchor.
        self.assertEqual(links.heading_anchors("---\ntitle: x\ndraft: true\n---\n# Real\n"), {"real"})

    def test_a_list_item_or_quote_over_a_rule_is_not_a_heading(self):
        for text in ("- item\n---\n", "* item\n---\n", "+ item\n---\n", "1. item\n---\n", "2) item\n---\n", "> quote\n---\n"):
            self.assertEqual(links.heading_anchors(text), set(), repr(text))

    def test_a_plain_text_line_over_a_rule_is_a_heading(self):
        self.assertEqual(links.heading_anchors("Plain line\n---\n"), {"plain-line"})
        self.assertEqual(links.heading_anchors("Starts with 3 dashes\n---\n"), {"starts-with-3-dashes"})

    def test_html_anchors_with_a_name_or_an_id_are_anchors(self):
        text = '<a name="custom-name"></a>\n<a id=\'other-id\'>x</a>\n<div id="box"></div>\n'
        self.assertEqual(links.heading_anchors(text), {"custom-name", "other-id", "box"})

    def test_an_html_anchor_inside_a_code_block_is_an_example(self):
        self.assertEqual(links.heading_anchors('```\n<a name="nope"></a>\n```\n'), set())

    def test_code_in_a_heading_keeps_its_text(self):
        self.assertEqual(links.heading_anchors("# Use `foo` here\n"), {"use-foo-here"})

    def test_a_link_or_an_image_in_a_heading_contributes_its_text_only(self):
        self.assertEqual(links.heading_anchors("# [Guide](guide.md)\n## ![Logo](a.png) Name\n"), {"guide", "logo-name"})

    def test_a_heading_may_be_indented_by_up_to_three_spaces(self):
        self.assertEqual(links.heading_anchors("   # Title\n"), {"title"})
        self.assertEqual(links.heading_anchors("    # Code block\n"), set())

    def test_a_repeated_title_never_takes_an_anchor_that_already_exists(self):
        self.assertEqual(links.heading_anchors("# Foo\n# Foo\n# Foo-1\n# Foo\n"), {"foo", "foo-1", "foo-1-1", "foo-2"})

    def test_only_id_and_name_attributes_are_html_anchors(self):
        text = '<div data-id="fake"></div>\n<!-- <a id="commented"></a> -->\n<a id="one" name="two"></a>\n<a id=plain></a>\n'
        self.assertEqual(links.heading_anchors(text), {"one", "two", "plain"})

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

    def test_a_link_to_a_heading_with_an_ampersand_uses_the_double_hyphen(self):
        directory, root = make_repo({"README.md": "[ok](g.md#rust--js) [bad](g.md#rust-js)\n", "g.md": "# Rust & JS\n"})
        with directory:
            errors = links.check_documents(root, [root / "README.md"])
        self.assertEqual(errors, ["README.md: missing heading anchor: g.md#rust-js"])

    def test_links_to_a_filename_with_parentheses_and_to_html_anchors_resolve(self):
        directory, root = make_repo({
            "README.md": "[p](docs/a_(b).md) [h](docs/x.md#custom-name) [s](docs/x.md#setext-heading)\n",
            "docs/a_(b).md": "a",
            "docs/x.md": '# X\n<a name="custom-name"></a>\nSetext heading\n===============\n',
        })
        with directory:
            self.assertEqual(links.check_documents(root, [root / "README.md"]), [])

    def test_a_link_that_leaves_the_repository_is_an_error(self):
        directory, root = make_repo({"inner/README.md": "[out](../../outside.md)\n"})
        with directory:
            errors = links.check_documents(root / "inner", [root / "inner" / "README.md"])
        self.assertEqual(errors, ["README.md: link escapes repository: ../../outside.md"])

    def test_every_problem_in_a_document_is_reported_not_only_the_first(self):
        directory, root = make_repo({"inner/README.md": "[a](../../out.md) [b](gone.md)\n"})
        with directory:
            errors = links.check_documents(root / "inner", [root / "inner" / "README.md"])
        self.assertEqual(errors, ["README.md: link escapes repository: ../../out.md", "README.md: missing link target: gone.md"])

    def test_a_directory_target_is_accepted_without_an_anchor_check(self):
        directory, root = make_repo({"README.md": "[docs](docs/)\n", "docs/guide.md": "# Guide\n"})
        with directory:
            self.assertEqual(links.check_documents(root, [root / "README.md"]), [])


class RobustnessTests(unittest.TestCase):
    def test_a_target_that_cannot_be_used_is_reported_and_the_run_goes_on(self):
        directory, root = make_repo({"README.md": "[a](a%00.md) [b](gone.md) [c](http://[oops)\n"})
        with directory:
            errors = links.check_documents(root, [root / "README.md"])
        self.assertEqual(errors, ["README.md: invalid link target: a%00.md", "README.md: missing link target: gone.md"])

    def test_a_file_that_cannot_be_read_is_reported_and_the_others_are_still_checked(self):
        directory, root = make_repo({"ok.md": "[g](gone.md)\n"})
        with directory:
            (root / "bad.md").write_bytes(b"\xff\xfe not utf-8")
            errors = links.check_documents(root, [root / "bad.md", root / "ok.md"])
        self.assertEqual(errors, ["bad.md: cannot read the file as UTF-8 text", "ok.md: missing link target: gone.md"])

    def test_a_document_that_is_a_symlink_to_outside_the_repository_is_skipped(self):
        outside = tempfile.TemporaryDirectory()
        directory, root = make_repo({"docs/real.md": "# Real\n"})
        with directory, outside:
            secret = Path(outside.name) / "secret.md"
            secret.write_text("[x](gone.md)\n", encoding="utf-8")
            (root / "README.md").symlink_to(secret)
            errors = links.check_documents(root, [root / "README.md"])
        self.assertEqual(errors, ["README.md: skipped, it resolves outside the repository"])

    def test_a_skipped_document_does_not_stop_the_others_from_being_checked(self):
        outside = tempfile.TemporaryDirectory()
        directory, root = make_repo({"b.md": "[g](gone.md)\n"})
        with directory, outside:
            secret = Path(outside.name) / "secret.md"
            secret.write_text("x", encoding="utf-8")
            (root / "a.md").symlink_to(secret)
            errors = links.check_documents(root, [root / "a.md", root / "b.md"])
        self.assertEqual(errors, ["a.md: skipped, it resolves outside the repository", "b.md: missing link target: gone.md"])

    def test_only_markdown_files_are_documents_and_a_broken_symlink_is_not_one(self):
        directory, root = make_repo({"README.md": "# R\n", "notes.txt": "[x](gone.md)", "data.json": "{}"})
        with directory:
            (root / "dangling.md").symlink_to(root / "nowhere")
            found = [path.name for path in links.markdown_documents(root)]
        self.assertEqual(found, ["README.md"])

    def test_a_directory_named_like_a_document_is_not_read(self):
        directory, root = make_repo({"keep.md": "# Keep\n"})
        with directory:
            (root / "folder.md").mkdir()
            found = [path.name for path in links.markdown_documents(root)]
        self.assertEqual(found, ["keep.md"])

    def test_control_and_bidirectional_characters_never_reach_the_report(self):
        text = "[x](missing\x1b[2Jb\u202e.md)\n"
        directory, root = make_repo({"README.md": text})
        with directory:
            code, _, err = run_main([str(root)])
        self.assertEqual(code, 1)
        self.assertEqual(err, "README.md: missing link target: missing?[2Jb?.md\n")

    def test_the_same_target_file_is_read_once_however_many_links_point_at_it(self):
        directory, root = make_repo({"README.md": "[a](g.md#x) [b](g.md#x) [c](g.md#y)\n", "g.md": "# X\n"})
        reads = []
        original = Path.read_text
        def counting(self, *args, **kwargs):
            reads.append(self.name)
            return original(self, *args, **kwargs)
        with directory:
            Path.read_text = counting
            try:
                links.check_documents(root, [root / "README.md"])
            finally:
                Path.read_text = original
        self.assertEqual(reads.count("g.md"), 1)


class DiscoveryTests(unittest.TestCase):
    def test_document_discovery_skips_dependency_and_generated_directories(self):
        files = {name: "# Document\n" for name in ("docs/guide.md", "node_modules/dep/README.md", ".git/notes.md", "target/doc.md")}
        directory, root = make_repo(files)
        with directory:
            found = [path.relative_to(root).as_posix() for path in links.markdown_documents(root)]
        self.assertEqual(found, ["docs/guide.md"])


    def test_every_generated_or_dependency_directory_is_skipped(self):
        skipped = [".git", ".claude", "coverage", "node_modules", "target", "vendor", "dist", "build", "venv", ".venv", ".export-venv"]
        directory, root = make_repo({f"{name}/notes.md": "# Notes\n" for name in skipped} | {"keep.md": "# Keep\n"})
        with directory:
            found = [path.relative_to(root).as_posix() for path in links.markdown_documents(root)]
        self.assertEqual(found, ["keep.md"])


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

    def test_without_arguments_it_reads_the_process_arguments(self):
        directory, root = make_repo({"README.md": "# Only\n"})
        saved = sys.argv
        sys.argv = ["check_markdown_links.py", str(root)]
        try:
            with directory:
                code, out, _ = run_main(None)
        finally:
            sys.argv = saved
        self.assertEqual((code, out), (0, "Checked local Markdown links in 1 file.\n"))

    def test_more_than_one_argument_is_a_usage_error(self):
        code, out, err = run_main(["one", "two"])
        self.assertEqual((code, out, err), (2, "", "usage: check_markdown_links.py [REPO_DIR]\n"))

    def test_every_problem_is_printed_on_its_own_line(self):
        directory, root = make_repo({"README.md": "[a](a.md) [b](b.md)\n"})
        with directory:
            _, _, err = run_main([str(root)])
        self.assertEqual(err, "README.md: missing link target: a.md\nREADME.md: missing link target: b.md\n")

    def test_running_the_script_directly_checks_and_sets_the_exit_status(self):
        directory, root = make_repo({"README.md": "[gone](gone.md)\n"})
        with directory:
            result = subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("missing link target: gone.md", result.stderr)

    def test_it_never_modifies_the_files_it_reads(self):
        directory, root = make_repo({"README.md": "[gone](gone.md)\n", "guide.md": "# Guide\n"})
        with directory:
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            run_main([str(root)])
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
