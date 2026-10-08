# -*- coding: UTF-8 -*-
# Regression tests for the problems found in the 0.4.0 review.

import gettext
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PKG = os.path.join(ROOT, "addon", "globalPlugins", "codeCompass")
sys.path.insert(0, PKG)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import analyzer  # noqa: E402
import build  # noqa: E402
import editing  # noqa: E402
import filepath  # noqa: E402
from analyzer import Analysis  # noqa: E402

RUNNER = os.path.join(ROOT, "addon", "runner", "run_python.py")


def names(src, lang):
	return [i.name for i in Analysis(src, lang).outline()]


def chain_at(src, lang, needle):
	a = Analysis(src, lang)
	return [i.name for i in a.declaration_chain(src.index(needle))]


def lines_of(src, lang, name):
	item = [i for i in Analysis(src, lang).outline() if i.name == name][0]
	return item.startLine, item.endLine


# --- Analyzer --------------------------------------------------------------------------

class AnalyzerTests(unittest.TestCase):
	def test_wrapped_calls_stay_fast(self):
		body = "".join("  doThing(\n    %d,\n  );\n" % i for i in range(5000))
		src = "function main() {\n" + body + "}\n"
		start = time.perf_counter()
		self.assertEqual(names(src, "js"), ["main"])
		self.assertLess(time.perf_counter() - start, 2.0)

	def test_wrapped_call_in_first_method_is_not_a_method(self):
		src = "class A {\n  run() {\n    go(\n      1,\n    );\n  }\n}\n"
		self.assertEqual(names(src, "js"), ["A", "run"])

	def test_go_func_literals_are_not_declarations(self):
		src = "func main() {\n\tgo func() {\n\t\tx()\n\t}()\n\tvar cb func(int) error\n}\n"
		self.assertEqual(names(src, "clike"), ["main"])

	def test_declaration_names_that_are_control_words(self):
		self.assertEqual(names("impl Foo {\n    fn new() -> Self {\n        Foo\n    }\n}\n", "clike"), ["Foo", "new"])
		self.assertEqual(names("fun delete(id: Int) {\n}\n", "clike"), ["delete"])

	def test_enum_class_and_template_parameters(self):
		self.assertEqual(names("enum class Color { Red, Green };\n", "clike"), ["Color"])
		self.assertNotIn("T", names("template <class T>\nT max(T a, T b) {\n    return a;\n}\n", "clike"))

	def test_php_closure(self):
		self.assertNotIn("use", names("$f = function ($x) use ($y) {\n    return $x;\n};\n", "php"))

	def test_csharp_attribute_list(self):
		src = "class M {\n    [Required, StringLength(50)]\n    public string Name { get; set; }\n}\n"
		self.assertNotIn("StringLength", names(src, "clike"))

	def test_wrapped_arrow_with_object_return_type(self):
		src = "const make = (\n  a: number,\n): { ok: boolean } => {\n  return { ok: true };\n};\n"
		self.assertEqual(names(src, "js"), ["make"])

	def test_swift_throwing_requirement(self):
		src = "protocol Store {\n    func load() async throws\n    var count: Int { get }\n}\n"
		self.assertEqual(chain_at(src, "swift", "var count"), ["Store"])

	def test_compact_comparison_in_expression_body(self):
		src = "class U {\n    fun isMinor() = age<18\n    init {\n        check()\n    }\n}\n"
		self.assertEqual(chain_at(src, "clike", "check()"), ["U"])

	def test_semicolon_in_generic_object_type(self):
		src = "async function get(): Promise<{ ok: boolean; data: T }> {\n  return run();\n}\n"
		self.assertEqual(chain_at(src, "js", "return run"), ["get"])

	def test_decorated_field_with_call(self):
		src = "class C {\n  @Output() change = new EventEmitter()\n  @HostListener('x')\n  onX() {\n    go()\n  }\n}\n"
		self.assertEqual(lines_of(src, "js", "onX")[0], 2)

	def test_backslash_crlf_continues_string(self):
		src = 'char *s = "abc\\\r\ndef";\r\nint x;\r\n'
		a = Analysis(src, "clike")
		self.assertIn(1, a._continuation)

	def test_comment_spans(self):
		src = "x = 1  # note\ny = '# not a comment'\n"
		a = Analysis(src, "python")
		self.assertTrue(a.in_comment(src.index("note")))
		self.assertFalse(a.in_comment(src.index("not a comment")))

	def test_interpolations_are_code(self):
		a = Analysis('total = 1\nprint(f"{total} and {total:>5}")\ns = "total"\n', "python")
		self.assertEqual(len(editing.occurrences(a, "total")), 3)
		b = Analysis("const n = 1;\nconst s = `${n + 1} \\${n}`;\n", "js")
		self.assertEqual(len(editing.occurrences(b, "n")), 2)
		c = Analysis('let name = "a"\nprint("hi \\(name)")\n', "swift")
		self.assertEqual(len(editing.occurrences(c, "name")), 2)


# --- Editing ---------------------------------------------------------------------------

class EditingTests(unittest.TestCase):
	def test_nested_auto_closed_brackets_type_over(self):
		a = Analysis("print(len(x)))\n", "js")
		self.assertTrue(editing.autoclose_skip(a, len("print(len(x)"), ")"))

	def test_no_auto_close_inside_strings_or_comments(self):
		a = Analysis("s = '(\n", "python")
		self.assertFalse(editing.should_autoclose(a, 6, "("))
		b = Analysis('s = f"{\n', "python")
		self.assertFalse(editing.should_autoclose(b, 7, "{"))

	def test_quote_counting_ignores_comments_and_escapes(self):
		a = Analysis("x = '|'  # don't\n".replace("|", ""), "python")
		# After typing the second quote of '' the skip/close logic uses code only.
		self.assertFalse(editing.should_autoclose(a, 6, "'"))
		b = Analysis('p = "C:\\\\"\n', "python")
		self.assertFalse(editing.should_autoclose(b, len('p = "C:\\\\"'), '"'))

	def test_parameter_hint_from_own_header(self):
		src = "const add = (a, b) => a + b;\nadd(1, \n"
		a = Analysis(src, "js")
		self.assertEqual(editing.parameter_hint(a, len(src) - 1), ("add(a, b)", 2))
		src2 = "class Shop:\n    def __init__(self, name, price):\n        pass\n\nShop('x', \n"
		a2 = Analysis(src2, "python")
		self.assertEqual(editing.parameter_hint(a2, len(src2) - 1), ("Shop(name, price)", 2))
		src3 = "class Point {\n}\nPoint(1, \n"
		self.assertIsNone(editing.parameter_hint(Analysis(src3, "js"), len(src3) - 1))

	def test_parameter_hint_lambda_commas(self):
		src = "def f(key, items):\n    pass\n\nf(lambda a, b: a, \n"
		a = Analysis(src, "python")
		self.assertEqual(editing.parameter_hint(a, len(src) - 1)[1], 2)

	def test_member_completion_stays_on_its_line(self):
		src = "class A:\n    def f(self):\n        self.count = 1\n        self.\n        print(x)\n"
		a = Analysis(src, "python")
		caret = src.index("self.\n") + len("self.")
		start, prefix, words = editing.completions(a, caret)
		self.assertEqual(words, ["count"])

	def test_completion_after_spread_and_relative_import(self):
		src = "const items = [];\nconst all = [...ite\n"
		a = Analysis(src, "js")
		self.assertIn("items", editing.completions(a, len(src) - 1)[2])

	def test_unicode_identifiers(self):
		src = "\u00fcber = 1\nber = 2\nprint(\u00fcber)\n"
		a = Analysis(src, "python")
		self.assertEqual(editing.identifier_at(a, src.rindex("ber") + 1)[2], "\u00fcber")
		self.assertIsNone(editing.identifier_at(Analysis("x = 1e5\n", "python"), 6))

	def test_comment_at_shared_indentation(self):
		src = "if x:\n\t  a()\n\t  b()\n"
		a = Analysis(src, "python")
		text, commented = editing.toggle_comment(a, 1, 2)
		self.assertEqual(text, "\t  # a()\n\t  # b()")

	def test_enter_with_selection_between_braces(self):
		src = "f() {xyz}\n"
		a = Analysis(src, "js")
		text, caretIn = editing.enter_text(a, src.index("x"), "  ", src.index("}"))
		self.assertEqual(text, "\r\n  \r\n".replace("\r\n", "\n"))

	def test_cr_only_documents(self):
		self.assertEqual(editing.newline_style("a\rb\r"), "\r")
		self.assertEqual(editing.newline_style(""), "\r\n")


# --- Files and the runner -------------------------------------------------------------

class FilePathTests(unittest.TestCase):
	def setUp(self):
		self.root = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.root)

	def write(self, rel, text):
		path = os.path.join(self.root, rel)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w", encoding="utf-8", newline="") as f:
			f.write(text)
		return path

	def test_titles(self):
		self.assertEqual(filepath.title_file("main - Copy.py - Notepad"), "main - Copy.py")
		self.assertEqual(analyzer.extension_from_title("main - Copy.py - Notepad"), "py")
		self.assertEqual(filepath.title_file("untitled_game.py - Notepad"), "untitled_game.py")
		self.assertIsNone(filepath.title_file("Untitled - Notepad"))
		self.assertIsNone(filepath.title_file("new 1 - Notepad++"))

	def test_same_name_in_two_projects(self):
		one = self.write("p1/main.py", "print('one')\r\n")
		two = self.write("p2/main.py", "print('two')\r\n")
		with mock.patch.object(filepath, "recent_item_target", return_value=two), \
			mock.patch.object(filepath, "process_command_line", return_value='notepad.exe "%s"' % one):
			self.assertEqual(filepath.find_file("main.py - Notepad", pid=1, text="print('two')\r\n"), two)
			self.assertEqual(filepath.find_file("main.py - Notepad", pid=1, text="print('one')\r\n"), one)
			# Neither file holds what the editor shows: ask instead of guessing.
			self.assertIsNone(filepath.find_file("main.py - Notepad", pid=1, text="print('three')\r\n"))

	def test_unquoted_path_with_spaces(self):
		args = filepath.split_command_line("NOTEPAD.EXE C:\\My Files\\main.py")
		self.assertIn("C:\\My Files\\main.py", args)

	def test_project_root_skips_home(self):
		home = os.path.join(self.root, "home")
		self.write("home/.vscode/extensions/x.json", "{}")
		path = self.write("home/Documents/latihan/hello.py", "")
		with mock.patch.object(filepath.os.path, "expanduser", return_value=home):
			self.assertEqual(filepath.project_root(path), os.path.dirname(path))

	def test_parent_folder_stops_at_root(self):
		drive = os.path.splitdrive(os.path.abspath(self.root))[0] or "/"
		top = drive + os.sep if drive != "/" else "/"
		self.assertIsNone(filepath.parent_folder(top))
		self.assertEqual(filepath.parent_folder(os.path.join(self.root, "a")), self.root)


class RunnerTests(unittest.TestCase):
	def run_program(self, files):
		folder = tempfile.mkdtemp(prefix="cc run ")
		self.addCleanup(shutil.rmtree, folder, True)
		for name, body in files.items():
			with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
				f.write(body)
		report = os.path.join(folder, "report.json")
		subprocess.run([sys.executable, RUNNER, os.path.join(folder, "main.py"), report],
			stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
		with open(report, encoding="utf-8") as f:
			return json.load(f)

	def test_exit_true_is_one(self):
		self.assertEqual(self.run_program({"main.py": "import sys\nsys.exit(True)\n"})["status"], 1)

	def test_error_in_module_names_it(self):
		data = self.run_program({"main.py": "import helper\nhelper.f()\n", "helper.py": "def f():\n    return 1 / 0\n"})
		self.assertEqual(data["error"]["line"], 2)
		self.assertTrue(data["error"]["message"].startswith("helper.py line 2: ZeroDivisionError"))

	def test_shadowing_token_module_still_reports(self):
		data = self.run_program({"main.py": "raise ValueError('boom')\n", "token.py": "raise ImportError('x')\n"})
		self.assertEqual(data["error"], {"line": 1, "message": "ValueError: boom"})

	def test_multi_line_message(self):
		data = self.run_program({"main.py": "raise RuntimeError('first\\nsecond')\n"})
		self.assertEqual(data["error"]["message"], "RuntimeError: first")


# --- Access keys -------------------------------------------------------------------------

#: The labels of each dialog, as written in the code.
DIALOG_LABELS = {
	"settings": [
		"Report bracket &level when moving by line:", "&Only report when the level changes",
		"Shorter tone insi&de parentheses and square brackets", "Sa&y what closing brackets close",
		"Check for problems &when saving", "Play a sound on lines with a p&roblem",
		"Play a sound on bookmarked li&nes", "Sound styl&e:", "E&xamine code while typing:",
		"Say the &function or class the caret moves into",
		"Automatic &indentation on Enter and closing brackets (Windows 10 Notepad)",
		"Add closing brackets and &quotes automatically (Windows 10 Notepad)",
		"Undo and redo many steps with control+Z and control+Y (Windows &10 Notepad)",
		"Tone pitc&h for level 1 (Hz):", "Semi&tones higher per level:",
		"Applications with level tones and quick keys (co&mma separated):",
		"Lan&guage of Code Compass messages:",
	],
	"explorer": [
		"&Files and folders:", "New fi&le", "New fol&der", "&Rename", "Dele&te", "Copy &path",
		"&Up one folder", "&Choose folder...", "Show in &Windows Explorer", "Command pro&mpt here", "&Open",
	],
	"snippets": ["&Snippets:", "&Preview:", "De&lete", "Open snippets &folder", "&Insert"],
	"palette": ["&Search commands:", "&Commands:"],
}
#: Letters NVDA's settings dialog already uses (a survey of NVDA 2026.2's
#: own labels in every language it ships): &Categories, &Apply and more in
#: English, &Kategori and Ter&apkan in Indonesian.
RESERVED = {
	("settings", "en"): {"a", "c", "k", "p", "b", "s", "u", "v", "z"},
	("settings", "id"): {"k", "a"},
}


def access_key(label):
	m = re.search(r"&([^&])", label)
	return m.group(1).lower() if m else None


class AccessKeyTests(unittest.TestCase):
	def test_labels_exist_in_code(self):
		with open(os.path.join(PKG, "__init__.py"), encoding="utf-8") as f:
			source = f.read()
		for labels in DIALOG_LABELS.values():
			for label in labels:
				self.assertIn('"%s"' % label, source, label)

	def test_unique_in_english_and_indonesian(self):
		build.build_translations()
		catalog = gettext.translation("nvda", localedir=os.path.join(ROOT, "addon", "locale"), languages=["id"])
		for lang, translate in (("en", lambda s: s), ("id", catalog.gettext)):
			for dialog, labels in DIALOG_LABELS.items():
				keys = [access_key(translate(l)) for l in labels]
				self.assertNotIn(None, keys, (lang, dialog))
				self.assertEqual(len(keys), len(set(keys)), (lang, dialog, keys))
				self.assertFalse(set(keys) & RESERVED.get((dialog, lang), set()), (lang, dialog, keys))


if __name__ == "__main__":
	unittest.main()
