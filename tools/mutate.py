#!/usr/bin/env python3
"""Mutation testing with the standard library only.

A test suite that is green proves little by itself. This tool changes the code under
test one small step at a time (a `<` becomes `<=`, an `and` becomes `or`, a `1`
becomes `2`, a returned value becomes `None`, ...) and runs the tests again. A test
suite that guards the code fails for every such change: the mutant is "killed". A mutant
that leaves the suite green "survived", which means either a missing test or a change
that does not alter the behavior at all (an equivalent mutant, to be judged by a human).

    python3 tools/mutate.py plugins/ci-perf/scripts/audit_runs_on.py \\
        --tests tests.test_audit_runs_on tests.test_properties
    python3 tools/mutate.py SCRIPT --tests MODULE ... --list      # only show the mutants
    python3 tools/mutate.py SCRIPT --tests MODULE ... --allow 4   # 4 known equivalents

Every mutant runs in its own copy of the repository (the working tree is never
changed), with bytecode caching off, so that two mutants of the same size cannot see each
other's `.pyc` file. The tests must pass without any mutation, otherwise the run stops.
Exit status: 0 when at most `--allow` mutants survived, 1 when more did, 2 for a usage
error or a failing baseline.
"""

from __future__ import annotations

import argparse
import ast
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".coverage", "node_modules", ".venv", "venv")

# (pattern that finds the operator between its operands, replacement, label)
COMPARE = {
    ast.Lt: (r"<(?!=)", "<="), ast.LtE: (r"<=", "<"),
    ast.Gt: (r">(?!=)", ">="), ast.GtE: (r">=", ">"),
    ast.Eq: (r"==", "!="), ast.NotEq: (r"!=", "=="),
    ast.Is: (r"\bis\b(?!\s+not\b)", "is not"), ast.IsNot: (r"\bis\s+not\b", "is"),
    ast.In: (r"\bin\b", "not in"), ast.NotIn: (r"\bnot\s+in\b", "in"),
}
COMPARE_NAMES = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
    ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in",
}
ARITHMETIC = {
    ast.Add: (r"\+", "-", "+"), ast.Sub: (r"-", "+", "-"),
    ast.Mult: (r"\*(?!\*)", "/", "*"), ast.Div: (r"/(?!/)", "*", "/"), ast.FloorDiv: (r"//", "/", "//"),
}
BOOLEAN = {ast.And: (r"\band\b", "or", "and"), ast.Or: (r"\bor\b", "and", "or")}


@dataclass(frozen=True)
class Mutant:
    start: int
    end: int
    text: str
    line: int
    label: str


@dataclass(frozen=True)
class Result:
    mutant: Mutant
    status: str  # "killed", "survived" or "timeout"


def generate(source, strings=True):
    """Every single-step mutant of `source` that is valid Python, in source order."""
    tree = ast.parse(source)
    lines = source.split("\n")
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def offset(line, column):  # ast columns count UTF-8 bytes
        return starts[line - 1] + len(lines[line - 1].encode()[:column].decode())

    def span(node):
        return offset(node.lineno, node.col_offset), offset(node.end_lineno, node.end_col_offset)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))

    found = []

    def between(left_end, right_start, pattern, new, label, line):
        match = re.search(pattern, source[left_end:right_start])
        if match:
            found.append(Mutant(left_end + match.start(), left_end + match.end(), new, line, f"L{line}: {label}"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left_end = span(node.left)[1]
            for op, right in zip(node.ops, node.comparators):
                pattern, new = COMPARE[type(op)]
                old = COMPARE_NAMES[type(op)]
                between(left_end, span(right)[0], pattern, new, f"{old} -> {new}", node.lineno)
                left_end = span(right)[1]
        elif isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            pattern, new, old = ARITHMETIC[type(node.op)]
            between(span(node.left)[1], span(node.right)[0], pattern, new, f"{old} -> {new}", node.lineno)
        elif isinstance(node, ast.BoolOp):
            pattern, new, old = BOOLEAN[type(node.op)]
            for left, right in zip(node.values, node.values[1:]):
                between(span(left)[1], span(right)[0], pattern, new, f"{old} -> {new}", node.lineno)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            start, _ = span(node)
            match = re.match(r"not\s*", source[start:])
            found.append(Mutant(start, start + match.end(), "", node.lineno, f"L{node.lineno}: drop not"))
        elif isinstance(node, ast.Constant) and id(node) not in docstrings:
            start, end = span(node)
            value = node.value
            if value is True or value is False:
                found.append(Mutant(start, end, str(not value), node.lineno, f"L{node.lineno}: {value} -> {not value}"))
            elif isinstance(value, int):
                found.append(Mutant(start, end, str(value + 1), node.lineno, f"L{node.lineno}: {value} -> {value + 1}"))
                if value > 0:
                    found.append(Mutant(start, end, str(value - 1), node.lineno, f"L{node.lineno}: {value} -> {value - 1}"))
            elif strings and isinstance(value, str) and value and source[start] in "\"'" and source[start:start + 3] not in ('"""', "'''"):
                found.append(Mutant(end - 1, end - 1, "X", node.lineno, f"L{node.lineno}: str {value[:20]!r} + X"))
        elif isinstance(node, ast.Break):
            start, end = span(node)
            found.append(Mutant(start, end, "continue", node.lineno, f"L{node.lineno}: break -> continue"))
        elif isinstance(node, ast.Continue):
            start, end = span(node)
            found.append(Mutant(start, end, "break", node.lineno, f"L{node.lineno}: continue -> break"))
        elif isinstance(node, ast.Return) and node.value is not None:
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                start, end = span(node.value)
                found.append(Mutant(start, end, "None", node.lineno, f"L{node.lineno}: return -> None"))

    valid = []
    for mutant in sorted(found, key=lambda m: (m.start, m.label)):
        mutated = apply(source, mutant)
        if mutated == source:
            continue
        try:
            ast.parse(mutated)
        except SyntaxError:
            continue
        valid.append(mutant)
    return valid


def apply(source, mutant):
    return source[:mutant.start] + mutant.text + source[mutant.end:]


def run_tests(directory, tests, timeout):
    """'passed', 'failed' or 'timeout' for the unittest modules `tests` run inside `directory`."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run([sys.executable, "-m", "unittest", *tests, "-q", "-f"], cwd=directory,
                              capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "timeout"
    return "passed" if proc.returncode == 0 else "failed"


def run_mutants(root, script, tests, workers=4, timeout=60, strings=True):
    """Run every mutant of `script` (a path inside `root`) and return a Result for each."""
    root = Path(root).resolve()
    source = (root / script).read_text(encoding="utf-8")
    mutants = generate(source, strings)
    workers = max(1, min(workers, len(mutants)))
    base = Path(tempfile.mkdtemp(prefix="mutate-"))
    free = queue.Queue()
    try:
        for index in range(workers):
            copy = base / f"w{index}"
            shutil.copytree(root, copy, ignore=COPY_IGNORE)
            free.put(copy)

        def one(mutant):
            copy = free.get()
            try:
                (copy / script).write_text(apply(source, mutant), encoding="utf-8")
                outcome = run_tests(copy, tests, timeout)
            finally:
                free.put(copy)
            return Result(mutant, {"passed": "survived", "failed": "killed", "timeout": "timeout"}[outcome])

        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(one, mutants))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", help="the file to mutate, relative to --root")
    parser.add_argument("--tests", nargs="+", required=True, metavar="MODULE",
                        help="unittest modules that must fail for every mutant (comma lists are fine)")
    parser.add_argument("--root", default=".", help="repository root the tests run from (default: the current directory)")
    parser.add_argument("--workers", type=int, default=4, help="mutants tested in parallel (default 4)")
    parser.add_argument("--timeout", type=int, default=60, help="seconds a test run may take before the mutant counts as timed out")
    parser.add_argument("--list", action="store_true", help="only list the mutants, do not run any test")
    parser.add_argument("--no-strings", action="store_true", help="do not mutate string constants (messages, help text)")
    parser.add_argument("--allow", type=int, default=0, help="number of surviving mutants that are accepted (known equivalents)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    tests = [name for item in args.tests for name in item.split(",") if name]
    try:
        source = (root / args.script).read_text(encoding="utf-8")
    except OSError as err:
        print(f"cannot read {args.script}: {err.strerror or err}", file=sys.stderr)
        return 2
    mutants = generate(source, strings=not args.no_strings)
    if args.list:
        for mutant in mutants:
            print(mutant.label)
        print(f"{len(mutants)} mutants")
        return 0

    baseline = run_tests(root, tests, args.timeout * 4)
    if baseline != "passed":
        print(f"the tests fail without any mutation ({baseline}); fix them first: python3 -m unittest {' '.join(tests)}", file=sys.stderr)
        return 2
    results = run_mutants(root, args.script, tests, args.workers, args.timeout, strings=not args.no_strings)
    lines = source.split("\n")
    survivors = [r for r in results if r.status == "survived"]
    timeouts = sum(r.status == "timeout" for r in results)
    for result in survivors:
        print(f"SURVIVED {result.mutant.label}    | {lines[result.mutant.line - 1].strip()}")
    note = f" ({timeouts} timed out)" if timeouts else ""
    print(f"{args.script}: killed {len(results) - len(survivors)} of {len(results)} mutants{note}; {len(survivors)} survived")
    return 1 if len(survivors) > args.allow else 0


if __name__ == "__main__":
    sys.exit(main())
