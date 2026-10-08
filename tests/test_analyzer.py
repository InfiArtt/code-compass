# -*- coding: UTF-8 -*-
# Unit tests for the analyzer. Run from the project root:
#     py -3.13 -m unittest discover -s tests -v

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))

import analyzer  # noqa: E402
from analyzer import Analysis  # noqa: E402

SWIFT = """\
import UIKit

class ProfileViewController: UIViewController {
    // comment with } brace
    override func viewDidLoad() {
        super.viewDidLoad()
        if let user = currentUser {
            label.text = "Hi {name}"
            load(user,
                 animated: true)
        }
    }
}
"""

PYTHON = '''\
class Greeter:
    """Doc with ( paren."""

    def hello(self, name):
        if name:
            print("hi",
                  name)

        return None


def main():
    pass
'''


def line_of(text, needle):
	return text.splitlines().index(next(l for l in text.splitlines() if needle in l))


def offset_in_line(text, needle, extra=0):
	return text.index(needle) + extra


class StripTests(unittest.TestCase):
	def test_comments_and_strings_blanked(self):
		code = analyzer.strip_code('a = "x{y}" // }\nb', "js")
		self.assertEqual(code, 'a = "    "     \nb')

	def test_length_preserved_with_crlf(self):
		text = "int a; /* {\r\n } */ x('(');\r\n"
		code = analyzer.strip_code(text, "clike")
		self.assertEqual(len(code), len(text))
		self.assertEqual(code.count("\r\n"), 2)
		self.assertNotIn("{", code)

	def test_rust_lifetime_is_not_a_string(self):
		a = Analysis("fn get<'a>(x: &'a str) -> &'a str {\n    x\n}\n", "clike")
		self.assertEqual(a.problems(), [])
		self.assertEqual(a.line_depth(1), 1)

	def test_unterminated_string_stops_at_line_end(self):
		a = Analysis('x = "oops (\ny = (1)\n', "js")
		self.assertEqual(a.problems(), [])

	def test_shell_hash_inside_word(self):
		a = Analysis('echo ${#arr[@]}  # count }\n', "hash")
		self.assertEqual(a.problems(), [])

	def test_python_triple_quotes(self):
		a = Analysis(PYTHON, "python")
		self.assertEqual(a.problems(), [])


class DepthTests(unittest.TestCase):
	def setUp(self):
		self.a = Analysis(SWIFT, "swift")

	def test_line_depths(self):
		depths = [self.a.line_depth(i) for i in range(self.a.lineCount)]
		# import, blank, class, comment, func, super, if, label, load(, animated, }, }, }, ""
		self.assertEqual(depths, [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 2, 1, 0, 0])

	def test_closing_line_is_outer_level(self):
		li = 10  # the "}" closing the if
		self.assertEqual(self.a.line_text(li).strip(), "}")
		self.assertEqual(self.a.line_depth(li), 2)

	def test_balanced(self):
		self.assertEqual(self.a.problems(), [])

	def test_scopes(self):
		off = SWIFT.index("animated")
		scopes = [t for _li, t in self.a.scopes(off)]
		self.assertEqual(scopes, [
			"class ProfileViewController: UIViewController",
			"override func viewDidLoad()",
			"if let user = currentUser",
			"load paren",
		])

	def test_top_level(self):
		self.assertEqual(self.a.scopes(0), [])

	def test_match(self):
		off = SWIFT.index("viewDidLoad() {") + len("viewDidLoad() ")
		b = self.a.bracket_at(off)
		self.assertEqual(b.char, "{")
		closer = self.a.bracket_at(b.partner)
		self.assertEqual(closer.char, "}")
		self.assertEqual(self.a.line_index(closer.offset), 11)


class ProblemTests(unittest.TestCase):
	def test_unclosed(self):
		a = Analysis("func a() {\n    if x {\n}\n", "swift")
		probs = a.problems()
		self.assertEqual(len(probs), 1)
		self.assertEqual(probs[0][0], 0)
		self.assertIn("unclosed brace on line 1", probs[0][1])

	def test_extra(self):
		a = Analysis("call(1))\n", "js")
		probs = a.problems()
		self.assertEqual(len(probs), 1)
		self.assertIn("extra closing paren on line 1", probs[0][1])

	def test_mismatch_recovers(self):
		# The ")" is missing; the "}" still closes the block.
		a = Analysis("func a() {\n    foo(1\n}\nlet b = 2\n", "swift")
		self.assertEqual(a.line_depth(3), 0)
		self.assertEqual(len(a.unclosed), 1)
		self.assertEqual(a.unclosed[0].char, "(")


class PythonTests(unittest.TestCase):
	def setUp(self):
		self.a = Analysis(PYTHON, "python")

	def test_scopes_inside_call(self):
		off = PYTHON.index("  name)") + 2
		scopes = [t for _li, t in self.a.scopes(off)]
		self.assertEqual(scopes, [
			"class Greeter:",
			"def hello(self, name):",
			"if name:",
			'print paren',
		])

	def test_blank_line_inside_function(self):
		lines = PYTHON.splitlines(True)
		blank = lines.index("\n", 6)  # blank line before "return None"
		off = sum(len(l) for l in lines[:blank])
		scopes = [t for _li, t in self.a.scopes(off)]
		self.assertEqual(scopes, ["class Greeter:", "def hello(self, name):", "if name:"])

	def test_blocks_follow_indentation(self):
		a = self.a
		off = PYTHON.index("  name)") + 2
		blocks = a.blocks(off)
		starts = [PYTHON[b.start:b.start + 6] for b in blocks[:3]]
		self.assertEqual(starts, ["class ", "def he", "if nam"])
		self.assertEqual(PYTHON[blocks[3].start], "(")
		# Moving to the start of the innermost indented block lands on "if".
		ifBlock = blocks[-2]
		self.assertEqual(a.line_text(a.line_index(ifBlock.start)).strip(), "if name:")
		# Its end is the last line of the block (the continuation line).
		self.assertEqual(a.line_text(ifBlock.endLine).strip(), "name)")
		# From the "if" line itself, the next block out is the def.
		outer = a.blocks(ifBlock.start)
		self.assertEqual(PYTHON[outer[-1].start:outer[-1].start + 9], "def hello")
		# The def block ends at "return None", not at the blank line.
		self.assertEqual(a.line_text(outer[-1].endLine).strip(), "return None")

	def test_blocks_at_top_level(self):
		self.assertEqual(self.a.blocks(PYTHON.index("def main")), [])

	def test_outline(self):
		labels = [i.label() for i in self.a.outline()]
		self.assertEqual(labels, [
			"Greeter, class, line 1",
			"hello, function in Greeter, line 4",
			"main, function, line 12",
		])


class OutlineTests(unittest.TestCase):
	def test_swift(self):
		labels = [i.label() for i in Analysis(SWIFT, "swift").outline()]
		self.assertEqual(labels, [
			"ProfileViewController, class, line 3",
			"viewDidLoad, function in ProfileViewController, line 5",
		])

	def test_java(self):
		src = (
			"public class App {\n"
			"    public static void main(String[] args) {\n"
			"        if (args.length > 0) {\n"
			"            return helper(args);\n"
			"        }\n"
			"    }\n"
			"    private int helper(String[] a) {\n"
			"        return 1;\n"
			"    }\n"
			"}\n"
		)
		labels = [i.label() for i in Analysis(src, "clike").outline()]
		self.assertEqual(labels, [
			"App, class, line 1",
			"main, function in App, line 2",
			"helper, function in App, line 7",
		])

	def test_js(self):
		src = (
			"function load(url) {\n"
			"  fetch(url);\n"
			"}\n"
			"const add = (a, b) => a + b;\n"
			"class Store {\n"
			"  async save(item) {\n"
			"  }\n"
			"}\n"
		)
		labels = [i.label() for i in Analysis(src, "js").outline()]
		self.assertEqual(labels, [
			"load, function, line 1",
			"add, function, line 4",
			"Store, class, line 5",
			"save, function in Store, line 6",
		])


class TitleTests(unittest.TestCase):
	def test_titles(self):
		self.assertEqual(analyzer.language_from_title("main.py - Notepad"), "python")
		self.assertEqual(analyzer.language_from_title("*app.swift - Notepad"), "swift")
		self.assertEqual(analyzer.language_from_title(r"*C:\me.dev\x.JS - Notepad++"), "js")
		self.assertEqual(analyzer.language_from_title("Untitled - Notepad"), "generic")
		self.assertEqual(analyzer.language_from_title("notes.txt - Notepad"), "generic")


class SpeedTests(unittest.TestCase):
	def test_large_file_is_fast(self):
		import time
		big = SWIFT * 400  # ~5000 lines
		t = time.perf_counter()
		a = Analysis(big, "swift")
		a.line_depth(a.lineCount - 1)
		a.scopes(len(big) // 2)
		elapsed = time.perf_counter() - t
		self.assertLess(elapsed, 0.5, "analysis took %.3fs" % elapsed)


if __name__ == "__main__":
	unittest.main()


class CloserTests(unittest.TestCase):
	def setUp(self):
		self.a = Analysis(SWIFT, "swift")

	def closer_on_line(self, index):
		return self.a.leading_closer(index)

	def test_line_closer_names_its_block(self):
		# Line 10 is the "}" closing "if let user".
		off = self.closer_on_line(10)
		self.assertEqual(self.a.describe_closer(off), "closes if let user = currentUser")

	def test_lines_without_leading_closer(self):
		self.assertIsNone(self.a.leading_closer(5))

	def test_mismatched_closer(self):
		src = "func a() {\n    foo(1\n}\n"
		a = Analysis(src, "swift")
		msg = a.describe_closer(src.index("}"))
		self.assertEqual(msg, "closes func a(), but paren from line 2 is still open")

	def test_stray_closer(self):
		a = Analysis("x)\n", "js")
		self.assertEqual(a.describe_closer(1), "nothing to close")

	def test_not_a_closer(self):
		self.assertIsNone(self.a.describe_closer(0))

	def test_inner_bracket_per_line(self):
		inner = [self.a.line_inner_bracket(i) for i in range(self.a.lineCount)]
		# "animated: true)" sits inside load( ... ).
		self.assertEqual(inner[9], "(")
		self.assertEqual(inner[7], "{")
		self.assertIsNone(inner[0])


class NavigationTests(unittest.TestCase):
	def test_same_level_skips_nested_blocks_swift(self):
		a = Analysis(SWIFT, "swift")
		# "super.viewDidLoad()" (5) -> "if let user" (6), then the block ends.
		self.assertEqual(a.same_level_line(5, 1), 6)
		self.assertIsNone(a.same_level_line(6, 1))
		self.assertEqual(a.same_level_line(6, -1), 5)
		self.assertIsNone(a.same_level_line(5, -1))

	def test_same_level_skips_closer_lines(self):
		src = "class A {\n    func a() {\n        x()\n    }\n    func b() {\n    }\n}\n"
		a = Analysis(src, "swift")
		self.assertEqual(a.same_level_line(1, 1), 4)
		self.assertEqual(a.same_level_line(4, -1), 1)

	def test_same_level_python(self):
		a = Analysis(PYTHON, "python")
		lines = PYTHON.splitlines()
		start = lines.index("    def hello(self, name):")
		self.assertIsNone(a.same_level_line(start, 1))  # last method in class
		top = lines.index("class Greeter:")
		self.assertEqual(lines[a.same_level_line(top, 1)], "def main():")

	def test_declaration_near(self):
		a = Analysis(PYTHON, "python")
		self.assertEqual(a.declaration_near(0, 1).name, "hello")
		self.assertEqual(a.declaration_near(5, -1).name, "hello")
		self.assertIsNone(a.declaration_near(0, -1))

	def test_block_range_whole_lines(self):
		a = Analysis(SWIFT, "swift")
		blocks = a.blocks(SWIFT.index("label.text"))
		start, end = a.block_range(blocks[-1])
		self.assertTrue(SWIFT[start:end].startswith("        if let user"))
		self.assertTrue(SWIFT[start:end].endswith("        }\n"))

	def test_block_range_python(self):
		a = Analysis(PYTHON, "python")
		blocks = a.blocks(PYTHON.index("print"))
		start, end = a.block_range(blocks[-1])
		self.assertEqual(PYTHON[start:end], '        if name:\n            print("hi",\n                  name)\n')
