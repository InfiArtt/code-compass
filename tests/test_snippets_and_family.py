# -*- coding: UTF-8 -*-
# Tests for snippet text handling and declaration hierarchy (no NVDA needed).

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))

import analyzer  # noqa: E402
import snippets  # noqa: E402
from analyzer import Analysis  # noqa: E402

PYTHON = (
	"import os\n"
	"\n"
	"class Shop:\n"
	"    def __init__(self):\n"
	"        self.items = []\n"
	"\n"
	"    def add(self, item):\n"
	"        def check(x):\n"
	"            return x\n"
	"        self.items.append(check(item))\n"
	"\n"
	"def main():\n"
	"    Shop().add(1)\n"
)

ALLMAN = (
	"class App\n"
	"{\n"
	"    void Run()\n"
	"    {\n"
	"        Go();\n"
	"    }\n"
	"}\n"
)


class FamilyTests(unittest.TestCase):
	def test_python_chain_and_children(self):
		a = Analysis(PYTHON, "python")
		chain = a.declaration_chain(PYTHON.index("return x"))
		self.assertEqual([i.name for i in chain], ["Shop", "add", "check"])
		shop = chain[0]
		self.assertEqual([c.name for c in shop.children], ["__init__", "add"])
		self.assertEqual([p.name for p in chain[-1].ancestors()], ["add", "Shop"])

	def test_caret_on_declaration_line(self):
		a = Analysis(PYTHON, "python")
		chain = a.declaration_chain(PYTHON.index("def add"))
		self.assertEqual([i.name for i in chain], ["Shop", "add"])

	def test_outside_everything(self):
		a = Analysis(PYTHON, "python")
		self.assertEqual(a.declaration_chain(0), [])

	def test_allman_braces(self):
		a = Analysis(ALLMAN, "clike")
		chain = a.declaration_chain(ALLMAN.index("Go()"))
		self.assertEqual([i.name for i in chain], ["App", "Run"])

	def test_declaration_range_python(self):
		a = Analysis(PYTHON, "python")
		add = [i for i in a.outline() if i.name == "add"][0]
		start, end = a.declaration_range(add)
		self.assertTrue(PYTHON[start:end].startswith("    def add"))
		self.assertTrue(PYTHON[start:end].endswith("self.items.append(check(item))\n"))

	def test_declaration_range_allman(self):
		a = Analysis(ALLMAN, "clike")
		run = [i for i in a.outline() if i.name == "Run"][0]
		start, end = a.declaration_range(run)
		self.assertEqual(ALLMAN[start:end], "    void Run()\n    {\n        Go();\n    }\n")

	def test_extension_from_title(self):
		self.assertEqual(analyzer.extension_from_title("main.py - Notepad"), "py")
		self.assertEqual(analyzer.extension_from_title("notes.txt - Notepad"), "txt")
		self.assertIsNone(analyzer.extension_from_title("Untitled - Notepad"))


class SnippetTextTests(unittest.TestCase):
	def test_dedent_method(self):
		text = "    def add(self):\r\n        return 1\r\n\r\n"
		self.assertEqual(snippets.dedent(text), "def add(self):\n    return 1\n")

	def test_dedent_selection_starting_after_indentation(self):
		# The selection began after the 8 spaces of its first line.
		text = "if x:\n            y()\n"
		self.assertEqual(snippets.dedent(text, "        "), "if x:\n    y()\n")

	def test_prepare_insert_at_indented_caret(self):
		out = snippets.prepare_insert("if a:\n    b()\n", "    ", "\r\n")
		self.assertEqual(out, "if a:\r\n        b()")

	def test_prepare_insert_after_code(self):
		out = snippets.prepare_insert("[\n  1,\n]\n", "    x = ", "\n")
		self.assertEqual(out, "[\n      1,\n    ]")

	def test_blank_lines_stay_blank(self):
		out = snippets.prepare_insert("a\n\nb\n", "  ", "\n")
		self.assertEqual(out, "a\n\n  b")


class SnippetStorageTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.folder)

	def test_save_and_list_prefers_language(self):
		snippets.save_snippet(self.folder, "zeta", "py", "z\r\n")
		snippets.save_snippet(self.folder, "alpha", "js", "a\n")
		snippets.save_snippet(self.folder, "beta", "py", "b\n")
		names = [s.label() for s in snippets.list_snippets(self.folder, "py")]
		self.assertEqual(names, ["beta (py)", "zeta (py)", "alpha (js)"])
		zeta = snippets.list_snippets(self.folder, "py")[1]
		self.assertEqual(zeta.read(), "z\n")

	def test_unsafe_names_are_cleaned(self):
		self.assertEqual(snippets.safe_name('a/b:c*?"d'), "abcd")
		self.assertEqual(snippets.safe_name("  ..  "), "")

	def test_missing_folder_lists_nothing(self):
		self.assertEqual(snippets.list_snippets(os.path.join(self.folder, "nope")), [])


if __name__ == "__main__":
	unittest.main()
