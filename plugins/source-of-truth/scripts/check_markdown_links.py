#!/usr/bin/env python3
"""Check local Markdown links and heading anchors in a repository.

    check_markdown_links.py [REPO_DIR]        # defaults to the current directory

Read-only: it only reads `*.md` files. It reports links to files that do not exist,
links that leave the repository, and `#fragment`s that match no heading or HTML anchor.

Everything it prints that comes from the repository (file names, link targets) is
untrusted text: control, bidirectional-override, zero-width and line-separator
characters are replaced before printing. A document that is a symlink resolving outside
the repository is skipped, so the check cannot be made to read files elsewhere.

Limits (it is a small regex reader, not a Markdown parser):
  * only inline links `[text](target)` are checked; reference-style links
    (`[text][ref]`) and autolinks are not,
  * a target may contain one level of parentheses (`docs/a_(b).md`); deeper nesting is cut short,
  * fenced code blocks, code spans (also over several lines) and a YAML front matter block at the
    top are treated as examples and not searched,
  * a setext heading is only the one line above its underline, so a paragraph of several lines gets the
    anchor of its last line,
  * anchors are the headings (ATX `# Title` and setext `Title` over `===` or `---`, numbered
    together in document order, following the GitHub slug rule: lower case, punctuation
    removed, each space becomes one hyphen) plus any `id=` or `name=` attribute of an HTML tag.

Exit status: 0 all links resolve, 1 at least one problem, 2 usage error.
"""

from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

# A target may hold one level of balanced parentheses, as in `docs/a_(b).md`. The link text may hold one level of
# brackets (a badge: `[![alt](img)](target)`). Every repetition is bounded and unambiguous, so the scan is linear.
LINK = re.compile(
    r"(?<!!)\[(?:[^\[\]\n]|\[[^\[\]\n]{0,200}\]){0,500}\]\(((?:[^()\n]|\([^()\n]{0,200}\)){1,2000})\)"
)
# An ATX heading (`# Title`) or a setext heading (a text line underlined with `===` or `---`), both indented by at
# most three spaces, in one pattern so that repeated titles are numbered in document order. The setext text line must
# not look like a table row, a quote or a list item (`-`, `*`, `+` or `1.` / `1)` followed by a space).
HEADING = re.compile(
    r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$|^ {0,3}(?![#|>]|[-*+]\s|\d+[.)]\s)(\S[^\n]*)\n {0,3}(?:=+|-+)[ \t]*$",
    re.MULTILINE,
)
FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
OPENING_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
CLOSING_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f؜​-‏ -‮⁠-⁩﻿]")
IGNORED_DIRECTORIES = {".git", ".claude", "coverage", "node_modules", "target", "vendor", "dist", "build", "venv", ".venv", ".export-venv"}


def safe(text):
    """Make repository text safe to print: replace characters that can rewrite or hide terminal output."""
    return UNSAFE.sub("?", str(text))


def without_code_blocks(text):
    """Drop a front matter block and blank out fenced code blocks, keeping their lines so that structure does not change."""
    text = FRONT_MATTER.sub("", text)
    kept = []
    fence = None
    for line in text.split("\n"):
        if fence is None:
            opening = OPENING_FENCE.match(line)
            # An info string after a backtick fence cannot contain a backtick; otherwise it is not a fence.
            if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
                fence = opening.group(1)
                kept.append("")
            else:
                kept.append(line)
        else:
            closing = CLOSING_FENCE.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                fence = None
            kept.append("")
    return "\n".join(kept)


def without_code(text):
    """Drop code blocks and code spans too (used only to find links, which do not depend on line structure)."""
    return CODE_SPAN.sub("", without_code_blocks(text))


def markdown_links(text):
    """Yield local link targets, excluding images, code and external URLs."""
    for match in LINK.finditer(without_code(text)):
        raw = match.group(1).strip()
        target = raw[1:].split(">", 1)[0] if raw.startswith("<") else raw.split(maxsplit=1)[0]
        if not SCHEME.match(target) and not target.startswith("//"):
            yield target


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.found = []

    def handle_starttag(self, tag, attrs):
        self.found.extend(value.lower() for name, value in attrs if name in ("id", "name") and value)


def heading_text(raw):
    """The visible text of a heading: links and images contribute their text, code keeps its text."""
    raw = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", raw)
    return re.sub(r"[`*_~]", "", raw).lower().strip()


def heading_anchors(text):
    """Return GitHub-style anchors for headings, with duplicate numbering, plus `id`/`name` anchors of HTML tags."""
    anchors = set()
    counts = {}
    plain = without_code_blocks(text)
    for match in HEADING.finditer(plain):
        slug = re.sub(r"[^\w -]", "", heading_text(match.group(1) or match.group(2)), flags=re.UNICODE).replace(" ", "-")
        number = counts.get(slug, 0)
        candidate = slug if number == 0 else f"{slug}-{number}"
        while candidate in anchors:
            number += 1
            candidate = f"{slug}-{number}"
        counts[slug] = number + 1
        anchors.add(candidate)
    parser = _Anchors()
    parser.feed(plain)
    anchors.update(parser.found)
    return anchors


def read_document(path):
    """Return the text of a Markdown file, or None when it cannot be read as UTF-8 text."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def check_documents(root, documents):
    """Return human-readable errors for missing local files and heading fragments."""
    errors = []
    anchor_cache = {}
    resolved_root = root.resolve()

    def anchors_of(path):
        if path not in anchor_cache:
            content = read_document(path)
            anchor_cache[path] = None if content is None else heading_anchors(content)
        return anchor_cache[path]

    for document in documents:
        name = safe(document.relative_to(root))
        try:
            document.resolve().relative_to(resolved_root)
        except ValueError:
            errors.append(f"{name}: skipped, it resolves outside the repository")
            continue
        content = read_document(document)
        if content is None:
            errors.append(f"{name}: cannot read the file as UTF-8 text")
            continue
        for target in markdown_links(content):
            shown = safe(target)
            try:
                parsed = urlsplit(target)
                relative = unquote(parsed.path)
                destination = (document.parent / relative).resolve() if relative else document.resolve()
            except (ValueError, OSError):
                errors.append(f"{name}: invalid link target: {shown}")
                continue
            try:
                destination.relative_to(resolved_root)
            except ValueError:
                errors.append(f"{name}: link escapes repository: {shown}")
                continue
            if not destination.exists():
                errors.append(f"{name}: missing link target: {shown}")
                continue
            if parsed.fragment and destination.is_file() and destination.suffix.lower() == ".md":
                found = anchors_of(destination)
                if found is not None and unquote(parsed.fragment).lower() not in found:
                    errors.append(f"{name}: missing heading anchor: {shown}")
    return errors


def markdown_documents(root):
    """Find project Markdown files while skipping generated and dependency trees."""
    found = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRECTORIES]
        for name in files:
            path = Path(directory) / name
            if name.lower().endswith(".md") and path.is_file():
                found.append(path)
    return sorted(found)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: check_markdown_links.py [REPO_DIR]", file=sys.stderr)
        return 2
    root = Path(args[0] if args else ".")
    if not root.is_dir():
        print(f"error: not a directory: {safe(root)}", file=sys.stderr)
        return 2
    documents = markdown_documents(root)
    errors = check_documents(root, documents)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Checked local Markdown links in {len(documents)} {'file' if len(documents) == 1 else 'files'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
