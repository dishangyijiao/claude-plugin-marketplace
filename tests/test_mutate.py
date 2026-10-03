"""Tests for tools/mutate.py: the mutation runner that checks how well the suite guards the scripts."""

import ast
import collections
import io
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

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

    def test_a_missing_script_is_a_usage_error(self):
        root = self.project("        pass\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mutate.main(["pkg/missing.py", "--tests", "tests.test_calc", "--root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("pkg/missing.py", err.getvalue())


if __name__ == "__main__":
    unittest.main()
