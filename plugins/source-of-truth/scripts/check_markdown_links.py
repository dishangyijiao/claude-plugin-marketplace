#!/usr/bin/env python3
"""Check local Markdown links and heading anchors in a repository.

    check_markdown_links.py [REPO_DIR]        # defaults to the current directory

Read-only: it only reads `*.md` files. It reports links to files that do not exist,
links that leave the repository, and `#fragment`s that match no heading.

Limits (it is a small regex reader, not a Markdown parser):
  * only inline links `[text](target)` are checked; reference-style links
    (`[text][ref]`) and autolinks are not,
  * a target may contain one level of parentheses (`docs/a_(b).md`); deeper nesting is cut short,
  * links inside fenced code blocks and inline code are treated as examples,
  * a setext heading is only the one line above its underline, so a paragraph of several lines gets the
    anchor of its last line; a YAML front matter block at the top is skipped,
  * anchors are the headings (ATX `# Title` and setext `Title` over `===` or `---`, numbered
    together in document order, following the GitHub slug rule: lower case, punctuation
    removed, each space becomes one hyphen) plus any `id=` or `name=` attribute of an HTML tag.

Exit status: 0 all links resolve, 1 at least one problem, 2 usage error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# A target may hold one level of balanced parentheses, as in `docs/a_(b).md`.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(((?:[^()]|\([^()]*\))+)\)")
# An ATX heading (`# Title`) or a setext heading (a text line underlined with `===` or `---`), in one pattern so that
# repeated titles are numbered in document order. The setext text line must not look like a table row, a quote or a
# list item (`-`, `*`, `+` or `1.` / `1)` followed by a space), which are not headings when a rule follows them.
HEADING = re.compile(
    r"^#{1,6}\s+(.+?)\s*#*\s*$|^(?![#|>]|[-*+]\s|\d+[.)]\s)(\S[^\n]*)\n(?:=+|-+)[ \t]*$",
    re.MULTILINE,
)
FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
HTML_ANCHOR = re.compile(r"<[A-Za-z][^>]*?\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']")
INLINE_CODE = re.compile(r"(`+).+?\1")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
IGNORED_DIRECTORIES = {".git", ".claude", "coverage", "node_modules", "target", "vendor", "dist", "build", "venv", ".venv", ".export-venv"}


def without_code(text):
    """Blank out fenced code blocks and inline code so examples are not checked."""
    kept = []
    fence = None
    for line in text.splitlines():
        opening = FENCE.match(line)
        if fence is None:
            if opening:
                fence = opening.group(1)
                continue
            kept.append(INLINE_CODE.sub("", line))
        elif opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence):
            fence = None
    return "\n".join(kept)


def markdown_links(text):
    """Yield local link targets, excluding images, code and external URLs."""
    for match in LINK.finditer(without_code(text)):
        raw = match.group(1).strip()
        target = raw[1:].split(">", 1)[0] if raw.startswith("<") else raw.split(maxsplit=1)[0]
        if not urlsplit(target).scheme and not target.startswith("//"):
            yield target


def heading_anchors(text):
    """Return GitHub-style anchors for ATX headings, including duplicate suffixes."""
    anchors = set()
    counts = {}
    plain = FRONT_MATTER.sub("", without_code(text), count=1)
    for match in HEADING.finditer(plain):
        heading = re.sub(r"[`*_~]", "", match.group(1) or match.group(2)).lower().strip()
        slug = re.sub(r"[^\w -]", "", heading, flags=re.UNICODE).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(f"{slug}-{count}" if count else slug)
    anchors.update(match.group(1).lower() for match in HTML_ANCHOR.finditer(plain))
    return anchors


def check_documents(root, documents):
    """Return human-readable errors for missing local files and heading fragments."""
    errors = []
    for document in documents:
        name = document.relative_to(root)
        for target in markdown_links(document.read_text(encoding="utf-8")):
            parsed = urlsplit(target)
            relative = unquote(parsed.path)
            destination = (document.parent / relative).resolve() if relative else document.resolve()
            try:
                destination.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{name}: link escapes repository: {target}")
                continue
            if not destination.exists():
                errors.append(f"{name}: missing link target: {target}")
                continue
            if parsed.fragment and destination.is_file() and destination.suffix.lower() == ".md":
                if unquote(parsed.fragment).lower() not in heading_anchors(destination.read_text(encoding="utf-8")):
                    errors.append(f"{name}: missing heading anchor: {target}")
    return errors


def markdown_documents(root):
    """Find project Markdown files while skipping generated and dependency trees."""
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts)
    )


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: check_markdown_links.py [REPO_DIR]", file=sys.stderr)
        return 2
    root = Path(args[0] if args else ".")
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
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
