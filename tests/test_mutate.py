"""Tests for tools/mutate.py: the mutation runner that checks how well the suite guards the scripts."""

import ast
import collections
import dataclasses
import errno
import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import mutate  # noqa: E402


def variants(source, **kwargs):
    """{label: mutated source} for every mutant of `source`; a label that is missing reads as None."""
    found = collections.defaultdict(lambda: None)
    for m in mutate.generate(source, **kwargs):
        found.setdefault(m.label, mutate.apply(source, m))
    return found


class OperatorTests(unittest.TestCase):
    def test_comparison_operators_are_flipped_to_their_neighbour(self):
        for old, new in (("<", "<="), ("<=", "<"), (">", ">="), (">=", ">"), ("==", "!="), ("!=", "=="),
                         ("is", "is not"), ("is not", "is"), ("in", "not in"), ("not in", "in")):
            with self.subTest(op=old):
                got = variants(f"x = a {old} b\n")
                self.assertEqual(got[f"L1: {old} -> {new}"], f"x = a {new} b\n")

    def test_arithmetic_and_boolean_operators_are_swapped(self):
        self.assertEqual(variants("x = a + b\n")["L1: + -> -"], "x = a - b\n")
        self.assertEqual(variants("x = a - b\n")["L1: - -> +"], "x = a + b\n")
        self.assertEqual(variants("x = a * b\n")["L1: * -> /"], "x = a / b\n")
        self.assertEqual(variants("x = a / b\n")["L1: / -> *"], "x = a * b\n")
        self.assertEqual(variants("x = a // b\n")["L1: // -> /"], "x = a / b\n")
        self.assertEqual(variants("x = a and b\n")["L1: and -> or"], "x = a or b\n")
        self.assertEqual(variants("x = a or b\n")["L1: or -> and"], "x = a and b\n")

    def test_every_operator_of_a_chain_gets_its_own_mutant(self):
        got = variants("x = a < b < c\n")
        self.assertEqual(got["L1: < -> <="], "x = a <= b < c\n")  # the first one is listed; both exist
        self.assertEqual(len([m for m in mutate.generate("x = a < b < c\n") if "< -> <=" in m.label]), 2)
        self.assertEqual(len([m for m in mutate.generate("x = a or b or c\n") if "or -> and" in m.label]), 2)

    def test_not_is_dropped_and_booleans_and_loop_jumps_are_flipped(self):
        self.assertEqual(variants("x = not a\n")["L1: drop not"], "x = a\n")
        self.assertEqual(variants("x = True\n")["L1: True -> False"], "x = False\n")
        self.assertEqual(variants("x = False\n")["L1: False -> True"], "x = True\n")
        loop = "for i in r:\n    if i:\n        break\n    continue\n"
        self.assertEqual(variants(loop)["L3: break -> continue"], loop.replace("break", "continue"))
        self.assertEqual(variants(loop)["L4: continue -> break"], loop.replace("    continue\n", "    break\n"))

    def test_integers_move_by_one_and_zero_only_goes_up(self):
        got = variants("x = 5\ny = 0\n")
        self.assertEqual(got["L1: 5 -> 6"], "x = 6\ny = 0\n")
        self.assertEqual(got["L1: 5 -> 4"], "x = 4\ny = 0\n")
        self.assertEqual(got["L2: 0 -> 1"], "x = 5\ny = 1\n")
        self.assertNotIn("L2: 0 -> -1", got)

    def test_a_return_value_becomes_none_but_a_bare_return_is_left_alone(self):
        self.assertEqual(variants("def f():\n    return 5\n")["L2: return -> None"], "def f():\n    return None\n")
        self.assertFalse([m for m in mutate.generate("def f():\n    return\n") if "return" in m.label])

    def test_a_string_gets_a_character_appended_unless_it_is_a_docstring_or_empty(self):
        self.assertEqual(variants('x = "ab"\n')["L1: str 'ab' + X"], 'x = "abX"\n')
        self.assertEqual(variants("x = 'ab'\n")["L1: str 'ab' + X"], "x = 'abX'\n")
        docs = 'def f():\n    """doc"""\n    return "ab"\n'
        self.assertEqual([m.label for m in mutate.generate(docs) if "str" in m.label], ["L3: str 'ab' + X"])
        self.assertFalse([m for m in mutate.generate('x = ""\n') if "str" in m.label])
        self.assertFalse([m for m in mutate.generate('x = "ab"\n', strings=False) if "str" in m.label])


class SourceHandlingTests(unittest.TestCase):
    def test_columns_are_correct_after_non_ascii_text_on_the_same_line(self):
        self.assertEqual(variants('s = "é中"; x = 1 < 2\n')["L1: < -> <="], 's = "é中"; x = 1 <= 2\n')

    def test_every_mutant_of_a_realistic_module_is_valid_python_and_differs(self):
        source = (ROOT / "plugins" / "ci-perf" / "scripts" / "audit_runs_on.py").read_text(encoding="utf-8")
        found = mutate.generate(source)
        self.assertGreater(len(found), 100)
        for m in found:
            mutated = mutate.apply(source, m)
            self.assertNotEqual(mutated, source, m.label)
            ast.parse(mutated)

    def test_a_replacement_that_would_not_parse_is_not_offered(self):
        source = 'x = f"{a!r:>5}"\n'
        for m in mutate.generate(source):
            ast.parse(mutate.apply(source, m))

    def test_the_last_line_is_mutated_even_without_a_trailing_newline(self):
        self.assertEqual(variants("x = a < b")["L1: < -> <="], "x = a <= b")
        self.assertEqual(variants("y = 1\nx = a < b")["L2: < -> <="], "y = 1\nx = a <= b")

    def test_a_comparison_inside_the_left_operand_does_not_hide_the_outer_one(self):
        source = "x = (a < b) < c\n"
        got = {mutate.apply(source, m) for m in mutate.generate(source) if "< -> <=" in m.label}
        self.assertEqual(got, {"x = (a <= b) < c\n", "x = (a < b) <= c\n"})

    def test_nothing_is_offered_where_the_operator_cannot_be_found_or_there_is_nothing_to_change(self):
        with mock.patch.dict(mutate.COMPARE, {ast.Lt: ("NEVER", "<=")}):
            self.assertFalse([m for m in mutate.generate("x = a < b\n") if "<" in m.label])
        self.assertFalse([m for m in mutate.generate("def f():\n    return None\n") if "return" in m.label])

    def test_a_mutant_cannot_be_changed_after_it_was_made(self):
        mutant = mutate.generate("x = a < b\n")[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            mutant.text = "other"
        result = mutate.Result(mutant, "killed")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = "survived"

    def test_an_operator_inside_an_operand_does_not_hide_the_operator_of_the_outer_expression(self):
        sums = {mutate.apply("x = a + b + c\n", m) for m in mutate.generate("x = a + b + c\n") if "+ -> -" in m.label}
        self.assertEqual(sums, {"x = a - b + c\n", "x = a + b - c\n"})
        bools = {mutate.apply("x = (p or q) or r\n", m) for m in mutate.generate("x = (p or q) or r\n") if "or -> and" in m.label}
        self.assertEqual(bools, {"x = (p and q) or r\n", "x = (p or q) and r\n"})
        chain = "x = a < (b < c) < d\n"
        chains = {mutate.apply(chain, m) for m in mutate.generate(chain) if "< -> <=" in m.label}
        self.assertEqual(chains, {"x = a <= (b < c) < d\n", "x = a < (b <= c) < d\n", "x = a < (b < c) <= d\n"})

    def test_one_goes_to_zero_and_triple_quoted_strings_are_left_alone(self):
        self.assertEqual(variants("x = 1\n")["L1: 1 -> 0"], "x = 0\n")
        self.assertFalse([m for m in mutate.generate('x = """ab"""\n') if "str" in m.label])
        self.assertFalse([m for m in mutate.generate("x = '''ab'''\n") if "str" in m.label])

    def test_a_label_shows_at_most_20_characters_of_a_string(self):
        self.assertIn(f"L1: str {'a' * 20!r} + X", variants(f'x = "{"a" * 30}"\n'))

    def test_a_replacement_that_does_not_parse_or_changes_nothing_is_dropped_and_the_rest_kept(self):
        source = "x = a < b\ny = c > d\n"
        for replacement in ("<<<", "<"):
            with self.subTest(replacement=replacement), mock.patch.dict(mutate.COMPARE, {ast.Lt: (r"<(?!=)", replacement)}):
                labels = [m.label for m in mutate.generate(source)]
                self.assertNotIn(f"L1: < -> {replacement}", labels)
                self.assertIn("L2: > -> >=", labels)

    def test_labels_carry_the_one_based_line_number(self):
        labels = [m.label for m in mutate.generate("\n\nx = a < b\n")]
        self.assertIn("L3: < -> <=", labels)


class RunnerTests(unittest.TestCase):
    def project(self, module, test):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "pkg").mkdir()
        (root / "pkg" / "calc.py").write_text(textwrap.dedent(module))
        (root / "tests").mkdir()
        (root / "tests" / "test_calc.py").write_text(textwrap.dedent(test))
        return root

    WEAK = """
        import sys, unittest
        sys.path.insert(0, "pkg")
        import calc

        class T(unittest.TestCase):
            def test_positive(self):
                self.assertTrue(calc.sign(5))
                self.assertFalse(calc.sign(-5))
        """

    def test_a_mutant_the_tests_cannot_see_survives_and_one_they_can_is_killed(self):
        root = self.project("def sign(x):\n    return x > 0\n", self.WEAK)
        results = collections.defaultdict(lambda: None)
        results.update({r.mutant.label: r.status for r in mutate.run_mutants(root, "pkg/calc.py", ["tests.test_calc"], workers=2, timeout=30)})
        self.assertEqual(results["L2: > -> >="], "survived")  # sign(0) is never asked
        self.assertEqual(results["L2: return -> None"], "killed")
        self.assertEqual(results["L2: 0 -> 1"], "survived")

    def test_a_mutant_that_never_finishes_is_reported_as_a_timeout(self):
        module = "def count(n):\n    i = 0\n    while i < n:\n        i = i + 1\n    return i\n"
        test = """
            import sys, unittest
            sys.path.insert(0, "pkg")
            import calc

            class T(unittest.TestCase):
                def test_count(self):
                    self.assertEqual(calc.count(3), 3)
            """
        root = self.project(module, test)
        results = collections.defaultdict(lambda: None)
        results.update({r.mutant.label: r.status for r in mutate.run_mutants(root, "pkg/calc.py", ["tests.test_calc"], workers=2, timeout=3)})
        self.assertEqual(results["L4: + -> -"], "timeout")

    def test_the_real_repository_is_never_modified(self):
        root = self.project("def sign(x):\n    return x > 0\n", self.WEAK)
        before = (root / "pkg" / "calc.py").read_text()
        mutate.run_mutants(root, "pkg/calc.py", ["tests.test_calc"], workers=2, timeout=30)
        self.assertEqual((root / "pkg" / "calc.py").read_text(), before)
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["pkg", "tests"])


class RunTestsTests(unittest.TestCase):
    def project(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "tests").mkdir()
        (root / "tests" / "test_x.py").write_text("import os, sys, time, unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n" + body)
        return root

    def test_the_three_outcomes(self):
        self.assertEqual(mutate.run_tests(self.project("        pass\n"), ["tests.test_x"], 30), "passed")
        self.assertEqual(mutate.run_tests(self.project("        self.fail()\n"), ["tests.test_x"], 30), "failed")
        self.assertEqual(mutate.run_tests(self.project("        time.sleep(30)\n"), ["tests.test_x"], 1), "timeout")

    def test_bytecode_caching_is_off_in_the_test_run(self):
        root = self.project("        self.assertTrue(sys.dont_write_bytecode)\n")
        self.assertEqual(mutate.run_tests(root, ["tests.test_x"], 30), "passed")

    def test_version_control_caches_and_environments_are_not_copied_for_the_mutants(self):
        root = self.project("        for name in ('.git', '__pycache__', 'node_modules', '.venv', 'venv', '.coverage'):\n"
                            "            self.assertFalse(os.path.exists(name), name)\n")
        for name in (".git", "__pycache__", "node_modules", ".venv", "venv"):
            (root / name).mkdir()
            (root / name / "marker").write_text("x")
        (root / ".coverage").write_text("x")
        (root / "pkg.py").write_text("def f(a, b):\n    return a < b\n")
        results = mutate.run_mutants(root, "pkg.py", ["tests.test_x"], workers=2, timeout=30)
        self.assertTrue(results)
        self.assertEqual({r.status for r in results}, {"survived"})  # the test only looks at the copy

    def test_strings_are_mutated_unless_asked_otherwise(self):
        root = self.project("        pass\n")
        (root / "pkg.py").write_text("def f():\n    return 'ab'\n")
        labels = lambda **kw: [r.mutant.label for r in mutate.run_mutants(root, "pkg.py", ["tests.test_x"], workers=1, timeout=30, **kw)]  # noqa: E731
        self.assertIn("L2: str 'ab' + X", labels())
        self.assertNotIn("L2: str 'ab' + X", labels(strings=False))

    def test_a_script_without_any_mutant_gives_no_results(self):
        root = self.project("        pass\n")
        (root / "pkg.py").write_text("def f():\n    pass\n")
        self.assertEqual(mutate.run_mutants(root, "pkg.py", ["tests.test_x"], workers=4, timeout=30), [])


class CommandLineTests(unittest.TestCase):
    def project(self, test_body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "pkg").mkdir()
        (root / "pkg" / "calc.py").write_text("def sign(x):\n    return x > 0\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_calc.py").write_text(
            "import sys, unittest\nsys.path.insert(0, 'pkg')\nimport calc\n\nclass T(unittest.TestCase):\n    def test_a(self):\n" + test_body)
        return root

    def run_main(self, root, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mutate.main(["pkg/calc.py", "--tests", "tests.test_calc", "--root", str(root), "--workers", "2", "--timeout", "30", *args])
        return code, out.getvalue(), err.getvalue()

    def test_list_prints_the_mutants_without_running_anything(self):
        root = self.project("        self.assertTrue(False)\n")  # a failing baseline would stop a real run
        code, out, _ = self.run_main(root, "--list")
        self.assertEqual(code, 0)
        self.assertIn("L2: > -> >=", out)
        self.assertIn("mutants", out)

    def test_a_failing_baseline_stops_before_any_mutant_runs(self):
        code, out, err = self.run_main(self.project("        self.assertTrue(False)\n"))
        self.assertEqual(code, 2)
        self.assertIn("tests fail without any mutation", err)
        self.assertNotIn("killed", out)

    def test_survivors_are_printed_with_their_source_line_and_decide_the_exit_code(self):
        root = self.project("        self.assertTrue(calc.sign(5))\n        self.assertFalse(calc.sign(-5))\n")
        code, out, _ = self.run_main(root)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"killed \d+ of \d+ mutants; \d+ survived")
        self.assertIn("SURVIVED L2: > -> >=", out)
        self.assertIn("return x > 0", out)

    def test_allow_accepts_a_known_number_of_equivalent_survivors(self):
        root = self.project("        self.assertTrue(calc.sign(5))\n        self.assertFalse(calc.sign(-5))\n")
        _, out, _ = self.run_main(root)
        survivors = out.count("SURVIVED")
        self.assertEqual(self.run_main(root, "--allow", str(survivors))[0], 0)
        self.assertEqual(self.run_main(root, "--allow", str(survivors - 1))[0], 1)

    def test_a_missing_script_names_the_file_and_the_system_reason(self):
        root = self.project("        pass\n")
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            mutate.main(["pkg/missing.py", "--tests", "tests.test_calc", "--root", str(root)])
        self.assertEqual(err.getvalue().strip(), f"cannot read pkg/missing.py: {os.strerror(errno.ENOENT)}")

    def test_the_defaults_are_4_workers_60_seconds_a_four_times_longer_baseline_and_no_survivor_allowed(self):
        root = self.project("        pass\n")
        old = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, old)
        survivor = mutate.Result(mutate.Mutant(0, 0, "", 2, "L2: x"), "survived")
        with mock.patch.object(mutate, "run_tests", return_value="passed") as run_tests, \
                mock.patch.object(mutate, "run_mutants", return_value=[survivor]) as run_mutants, redirect_stdout(io.StringIO()):
            code = mutate.main(["pkg/calc.py", "--tests", "a,b", "c"])
        self.assertEqual(code, 1)
        run_tests.assert_called_once_with(root.resolve(), ["a", "b", "c"], 240)
        run_mutants.assert_called_once_with(root.resolve(), "pkg/calc.py", ["a", "b", "c"], 4, 60, strings=True)

    def test_no_strings_reaches_both_listing_and_running(self):
        root = self.project("        self.assertTrue(calc.sign(5))\n")
        (root / "pkg" / "calc.py").write_text("def sign(x):\n    return 'a' if x > 0 else 'b'\n")
        (root / "tests" / "test_calc.py").write_text(
            "import sys, unittest\nsys.path.insert(0, 'pkg')\nimport calc\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(calc.sign(5), 'a')\n")
        counts = {}
        for flags in ((), ("--no-strings",)):
            _, listed, _ = self.run_main(root, "--list", *flags)
            _, ran, _ = self.run_main(root, "--allow", "99", *flags)
            counts[flags] = (int(re.search(r"(\d+) mutants", listed).group(1)), int(re.search(r"of (\d+) mutants", ran).group(1)))
        self.assertEqual(counts[()][0], counts[()][1])
        self.assertEqual(counts[("--no-strings",)][0], counts[("--no-strings",)][1])
        self.assertLess(counts[("--no-strings",)][0], counts[()][0])

    def test_the_summary_counts_are_consistent_and_timeouts_are_named(self):
        root = self.project("        pass\n")
        (root / "pkg" / "calc.py").write_text("def count(n):\n    i = 0\n    while i < n:\n        i = i + 1\n    return i\n")
        (root / "tests" / "test_calc.py").write_text(
            "import sys, unittest\nsys.path.insert(0, 'pkg')\nimport calc\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(calc.count(3), 3)\n")
        code, out, _ = self.run_main(root, "--allow", "99", "--timeout", "3")
        match = re.search(r"killed (\d+) of (\d+) mutants \((\d+) timed out\); (\d+) survived", out)
        self.assertIsNotNone(match, out)
        killed, total, timed_out, survived = map(int, match.groups())
        self.assertEqual(killed + survived, total)
        self.assertGreaterEqual(timed_out, 1)
        self.assertEqual(code, 0)

    def test_a_failing_baseline_names_the_modules_to_run(self):
        root = self.project("        self.assertTrue(False)\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            mutate.main(["pkg/calc.py", "--tests", "tests.test_calc", "tests.other", "--root", str(root)])
        self.assertIn("fix them first: python3 -m unittest tests.test_calc tests.other", err.getvalue())

    def test_help_describes_every_option_and_tests_are_required(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            mutate.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        text = " ".join(out.getvalue().split())
        for phrase in ("--tests MODULE [MODULE ...]", "the file to mutate, relative to --root",
                       "unittest modules that must fail for every mutant (comma lists are fine)",
                       "repository root the tests run from (default: the current directory)",
                       "mutants tested in parallel (default 4)",
                       "seconds a test run may take before the mutant counts as timed out",
                       "only list the mutants, do not run any test",
                       "do not mutate string constants (messages, help text)",
                       "number of surviving mutants that are accepted (known equivalents)"):
            self.assertRegex(text, re.escape(phrase) + r"(?!\S)")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as missing:
            mutate.main(["pkg/calc.py"])
        self.assertEqual(missing.exception.code, 2)

    def test_the_file_runs_as_a_script(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tools" / "mutate.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stdout)

    def test_a_missing_script_is_a_usage_error(self):
        root = self.project("        pass\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mutate.main(["pkg/missing.py", "--tests", "tests.test_calc", "--root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("pkg/missing.py", err.getvalue())


if __name__ == "__main__":
    unittest.main()
