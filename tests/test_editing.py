# -*- coding: UTF-8 -*-
# Tests for editing helpers and problem detection (no NVDA needed).

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))

import editing  # noqa: E402
import problems  # noqa: E402
from analyzer import Analysis  # noqa: E402


def at(src, needle, extra=0):
	return src.index(needle) + extra


class IndentUnitTests(unittest.TestCase):
	def test_spaces(self):
		self.assertEqual(editing.indent_unit("a:\n  b\n  c:\n    d\n"), "  ")
		self.assertEqual(editing.indent_unit("x {\n    y\n}\n"), "    ")

	def test_tabs(self):
		self.assertEqual(editing.indent_unit("x {\n\ty\n\tz {\n\t\tw\n\t}\n}\n"), "\t")

	def test_default(self):
		self.assertEqual(editing.indent_unit("flat\ntext\n"), "    ")


class EnterTests(unittest.TestCase):
	def test_keeps_indentation(self):
		src = "def f():\r\n    x = 1\r\n"
		a = Analysis(src, "python")
		self.assertEqual(editing.enter_text(a, at(src, "x = 1", 5), "    "), ("\r\n    ", None))

	def test_indents_after_colon_in_python(self):
		src = "def f():\r\n"
		a = Analysis(src, "python")
		self.assertEqual(editing.enter_text(a, at(src, ":", 1), "    "), ("\r\n    ", None))

	def test_dedents_after_return(self):
		src = "def f():\n    return 1\n"
		a = Analysis(src, "python")
		self.assertEqual(editing.enter_text(a, at(src, "1", 1), "    "), ("\n", None))

	def test_indents_after_brace(self):
		src = "func f() {\r\n}\r\n"
		a = Analysis(src, "swift")
		self.assertEqual(editing.enter_text(a, at(src, "{", 1), "    ")[0], "\r\n    ")

	def test_splits_bracket_pair(self):
		src = "    if x {}\r\n"
		a = Analysis(src, "swift")
		text, caretIn = editing.enter_text(a, at(src, "{", 1), "    ")
		self.assertEqual(text, "\r\n        \r\n    ")
		self.assertEqual(caretIn, len("\r\n        "))

	def test_colon_in_swift_is_not_a_block(self):
		src = "    case .a:\r\n"
		a = Analysis(src, "swift")
		self.assertEqual(editing.enter_text(a, at(src, ":", 1), "    ")[0], "\r\n    ")

	def test_brace_in_comment_does_not_indent(self):
		src = "x = 1 // {\r\n"
		a = Analysis(src, "js")
		self.assertEqual(editing.enter_text(a, len("x = 1 // {"), "  ")[0], "\r\n")

	def test_caret_inside_leading_whitespace(self):
		src = "        x\r\n"
		a = Analysis(src, "js")
		self.assertEqual(editing.enter_text(a, 4, "    ")[0], "\r\n    ")


class CloserReindentTests(unittest.TestCase):
	def test_lines_up_with_opener(self):
		src = "    if x {\n        y()\n        }\n"
		a = Analysis(src, "swift")
		closer = src.rindex("}")
		start, end, indent = editing.closer_reindent(a, closer)
		self.assertEqual((src[start:end], indent), ("        ", "    "))

	def test_already_right(self):
		src = "if x {\n    y()\n}\n"
		a = Analysis(src, "swift")
		self.assertIsNone(editing.closer_reindent(a, src.rindex("}")))

	def test_not_first_on_line(self):
		src = "if x { y() }\n"
		a = Analysis(src, "swift")
		self.assertIsNone(editing.closer_reindent(a, src.rindex("}")))


class CommentTests(unittest.TestCase):
	def test_comment_and_uncomment_python(self):
		src = "def f():\n    x = 1\n\n    return x\n"
		a = Analysis(src, "python")
		text, commented = editing.toggle_comment(a, 1, 3)
		self.assertTrue(commented)
		self.assertEqual(text, "    # x = 1\n\n    # return x")
		src2 = "def f():\n" + text + "\n"
		a2 = Analysis(src2, "python")
		text2, commented2 = editing.toggle_comment(a2, 1, 3)
		self.assertFalse(commented2)
		self.assertEqual(text2, "    x = 1\n\n    return x")

	def test_mixed_lines_get_commented(self):
		src = "// a\nb\n"
		a = Analysis(src, "js")
		self.assertEqual(editing.toggle_comment(a, 0, 1), ("// // a\r\n// b".replace("\r\n", "\n"), True))

	def test_css_block_comments(self):
		src = "a { color: red; }\n"
		a = Analysis(src, "css")
		text, commented = editing.toggle_comment(a, 0, 0)
		self.assertEqual(text, "/* a { color: red; } */")
		a2 = Analysis(text + "\n", "css")
		self.assertEqual(editing.toggle_comment(a2, 0, 0), ("a { color: red; }", False))


class ShiftTests(unittest.TestCase):
	def test_indent_and_outdent(self):
		src = "a\n\n  b\n"
		a = Analysis(src, "js")
		self.assertEqual(editing.shift_lines(a, 0, 2, "  "), "  a\n\n    b")
		self.assertEqual(editing.shift_lines(a, 0, 2, "  ", outward=True), "a\n\nb")

	def test_selection_ending_at_line_start(self):
		src = "a\nb\nc\n"
		a = Analysis(src, "js")
		self.assertEqual(editing.line_block(a, 0, src.index("c")), (0, 1))


class CompletionTests(unittest.TestCase):
	SRC = (
		"class Shop:\n"
		"    def __init__(self):\n"
		"        self.items = []\n"
		"        self.itemCount = 0\n"
		"    def add(self, item):\n"
		"        currentUser = 1\n"
		"        # currency in a comment\n"
		"        s = 'curtain'\n"
		"        cur\n"
		"        self.it\n"
	)

	def test_names_from_file_nearest_first(self):
		a = Analysis(self.SRC, "python")
		start, prefix, words = editing.completions(a, at(self.SRC, "        cur\n", 11))
		self.assertEqual(prefix, "cur")
		self.assertEqual(words[0], "currentUser")
		self.assertNotIn("currency", words)
		self.assertNotIn("curtain", words)

	def test_members_after_dot(self):
		a = Analysis(self.SRC, "python")
		start, prefix, words = editing.completions(a, at(self.SRC, "self.it\n", 7))
		self.assertEqual(prefix, "it")
		self.assertEqual(sorted(words), ["itemCount", "items"])

	def test_keywords(self):
		src = "def f():\n    ret\n"
		a = Analysis(src, "python")
		self.assertIn("return", editing.completions(a, at(src, "ret", 3))[2])

	def test_nothing_without_prefix(self):
		a = Analysis("x = \n", "python")
		self.assertEqual(editing.completions(a, 4)[2], [])


class ParameterHintTests(unittest.TestCase):
	def test_signature_and_argument(self):
		src = "def load(user,\n         animated=True):\n    pass\n\nload(me, \n"
		a = Analysis(src, "python")
		self.assertEqual(editing.parameter_hint(a, len(src) - 1), ("load(user, animated=True)", 2))

	def test_unknown_function(self):
		src = "print(1, \n"
		a = Analysis(src, "python")
		self.assertIsNone(editing.parameter_hint(a, len(src) - 1))


class ProblemTests(unittest.TestCase):
	def test_python_syntax_error(self):
		src = "def f():\n    x = (1,\n    return x\n"
		found = problems.python_problems(src)
		self.assertEqual(len(found), 1)
		self.assertIn(found[0].line, (1, 2))

	def test_python_ok(self):
		self.assertEqual(problems.python_problems("x = 1\r\nprint(x)\r\n"), [])

	def test_python_indentation_error(self):
		found = problems.python_problems("def f():\nreturn 1\n")
		self.assertEqual(found[0].line, 1)

	def test_json(self):
		found = problems.json_problems('{\n  "a": 1\n  "b": 2\n}\n')
		self.assertEqual(found[0].line, 2)

	def test_combined_and_next(self):
		src = "def f():\n    x = [1\n\nprint('a'\n"
		a = Analysis(src, "python")
		found = problems.find_problems(a)
		self.assertTrue(found)
		first = problems.next_problem(found, -1, 1)
		self.assertEqual(problems.next_problem(found, found[-1].line, 1), first)
		self.assertEqual(problems.next_problem(found, first.line, -1), found[-1])
		self.assertIsNone(problems.next_problem([], 0, 1))

	def test_running_nothing(self):
		# Parsing must not execute the code.
		src = "import os\nos.remove('should-not-be-deleted')\n"
		self.assertEqual(problems.python_problems(src), [])


if __name__ == "__main__":
	unittest.main()


class NameTests(unittest.TestCase):
	SRC = (
		"def total(items):\n"
		"    # total is the sum\n"
		"    s = 'total'\n"
		"    return sum(items)\n"
		"\n"
		"print(total([1]))\n"
		"subtotal = total([2])\n"
	)

	def test_identifier_and_occurrences(self):
		a = Analysis(self.SRC, "python")
		start, end, name = editing.identifier_at(a, self.SRC.index("total([1])") + 2)
		self.assertEqual(name, "total")
		spots = editing.occurrences(a, "total")
		self.assertEqual(len(spots), 3)  # def, print(...), subtotal = total(...)
		self.assertEqual(editing.definition_of(a, "total").line, 0)

	def test_rename_skips_comments_strings_and_longer_names(self):
		a = Analysis(self.SRC, "python")
		text, count = editing.renamed_text(a, "total", "grand")
		self.assertEqual(count, 3)
		self.assertIn("def grand(items)", text)
		self.assertIn("# total is the sum", text)
		self.assertIn("'total'", text)
		self.assertIn("subtotal = grand([2])", text)

	def test_no_identifier_in_comment(self):
		a = Analysis(self.SRC, "python")
		self.assertIsNone(editing.identifier_at(a, self.SRC.index("is the sum")))


class TodoTests(unittest.TestCase):
	def test_todos_in_comments_only(self):
		src = "x = 1  # TODO: rename x\ny = 'TODO in a string'\n/* FIXME later */\nTODO_COUNT = 3\n"
		a = Analysis(src, "generic")
		found = editing.todos(a)
		kinds = [(li, kind) for li, kind, text in found]
		self.assertIn((2, "FIXME"), kinds)
		self.assertNotIn((3, "TODO"), kinds)
		fixme = [t for li, k, t in found if k == "FIXME"][0]
		self.assertEqual(fixme, "later")

	def test_python_todo(self):
		src = "def f():\n    pass  # TODO: handle errors\n"
		a = Analysis(src, "python")
		self.assertEqual(editing.todos(a), [(1, "TODO", "handle errors")])


class LineTests(unittest.TestCase):
	def test_move_down_and_up(self):
		src = "a\r\nb\r\nc\r\n"
		a = Analysis(src, "js")
		start, end, text, first = editing.move_lines(a, 0, 0, 1)
		self.assertEqual((src[start:end], text, first), ("a\r\nb", "b\r\na", 1))
		start, end, text, first = editing.move_lines(a, 2, 2, -1)
		self.assertEqual((text, first), ("c\r\nb", 1))
		self.assertIsNone(editing.move_lines(a, 0, 0, -1))
		self.assertIsNone(editing.move_lines(a, 3, 3, 1))

	def test_duplicate(self):
		src = "a\nb\n"
		a = Analysis(src, "js")
		at_, text = editing.duplicate_lines(a, 0, 1)
		self.assertEqual(src[:at_] + text + src[at_:], "a\nb\na\nb\n")

	def test_full_lines_for_delete(self):
		src = "a\nb\nc"
		a = Analysis(src, "js")
		self.assertEqual(src[slice(*editing.full_lines(a, 1, 1))], "b\n")
		self.assertEqual(src[slice(*editing.full_lines(a, 2, 2))], "\nc")


class AutoCloseTests(unittest.TestCase):
	def check(self, src, caret, ch):
		return editing.should_autoclose(Analysis(src, "js"), caret, ch)

	def test_brackets(self):
		self.assertTrue(self.check("f(\n", 2, "("))
		self.assertTrue(self.check("f()\n", 2, "("))
		self.assertFalse(self.check("f(x\n", 2, "("))

	def test_quotes(self):
		self.assertTrue(self.check('s = "\n', 5, '"'))
		self.assertFalse(self.check("don't\n", 4, "'"))
		self.assertFalse(self.check('s = "abc"\n', 9, '"'))

	def test_type_over(self):
		src = "f(x))\n"
		a = Analysis(src, "js")
		self.assertTrue(editing.autoclose_skip(a, 4, ")"))
		src2 = 'print("abc"")\n'
		self.assertTrue(editing.autoclose_skip(Analysis(src2, "js"), 11, '"'))
		self.assertFalse(editing.autoclose_skip(Analysis("f(x)\n", "js"), 3, ")"))
