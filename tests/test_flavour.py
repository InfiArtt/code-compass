# -*- coding: UTF-8 -*-
# Small touches: tabs and spaces, names declared twice, going back after a
# jump, control+G, the save message, declaration lengths and run times.

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_smoke as smoke  # noqa: E402
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
Gesture = v040.Gesture

import problems  # noqa: E402
from analyzer import Analysis  # noqa: E402

RUNNER = os.path.join(os.path.dirname(__file__), "..", "addon", "runner", "run_python.py")


def indent_lines(src):
	return [(p.line, p.message) for p in problems.indentation_problems(Analysis(src, "python"))]


def duplicates(src, lang):
	return [(p.line, p.message) for p in problems.duplicate_problems(Analysis(src, lang))]


class IndentationTests(unittest.TestCase):
	def test_tab_in_a_spaces_file(self):
		src = "def f():\n    a = 1\n\tb = 2\n    return a\n"
		self.assertEqual(indent_lines(src), [(2, "indented with tabs, the rest of the file uses spaces")])

	def test_spaces_in_a_tabs_file(self):
		src = "def f():\n\ta = 1\n\tb = 2\n    return a\n"
		self.assertEqual(indent_lines(src), [(3, "indented with spaces, the rest of the file uses tabs")])

	def test_mixed_on_one_line(self):
		self.assertEqual(indent_lines("def f():\n \tpass\n"), [(1, "tabs and spaces mixed in the indentation")])

	def test_brackets_strings_and_clean_files(self):
		src = 'def f():\n    x = g(1,\n\t2)\n    s = """\n\tkept\n    """\n    return x\n'
		self.assertEqual(indent_lines(src), [])
		self.assertEqual(indent_lines("def f():\n\tif x:\n\t\treturn 1\n"), [])
		self.assertEqual(problems.indentation_problems(Analysis("{\n\ta;\n    b;\n}\n", "js")), [])

	def test_listed_with_other_problems(self):
		found = problems.find_problems(Analysis("def f():\n    a = 1\n\tb = 2\n", "python"))
		self.assertEqual([p.kind for p in found], ["syntax"])


class DuplicateTests(unittest.TestCase):
	def test_python(self):
		src = "def load():\n    pass\n\ndef save():\n    pass\n\ndef load():\n    pass\n"
		self.assertEqual(duplicates(src, "python"), [(6, "load is declared again; the one on line 1 no longer counts")])
		src = "class A:\n    def go(self):\n        pass\n\n    def go(self):\n        pass\n"
		self.assertEqual([line for line, _m in duplicates(src, "python")], [4])

	def test_python_alternatives_and_decorators(self):
		src = "if fast:\n    def f():\n        pass\nelse:\n    def f():\n        pass\n"
		self.assertEqual(duplicates(src, "python"), [])
		src = "class A:\n    @property\n    def x(self):\n        return 1\n\n    @x.setter\n    def x(self, v):\n        pass\n"
		self.assertEqual(duplicates(src, "python"), [])
		src = "class A:\n    def go(self):\n        pass\nclass B:\n    def go(self):\n        pass\n"
		self.assertEqual(duplicates(src, "python"), [])

	def test_javascript(self):
		src = "function load() {\n}\nfunction load() {\n}\n"
		self.assertEqual([line for line, _m in duplicates(src, "js")], [2])
		src = "class A {\n  get value() { return 1; }\n  set value(v) { this.v = v; }\n}\n"
		self.assertEqual(duplicates(src, "js"), [])
		src = "function f(a: string): void;\nfunction f(a: number): void;\nfunction f(a) {\n}\n"
		self.assertEqual(duplicates(src, "js"), [])
		src = "if (a) {\n  function f() {\n  }\n} else {\n  function f() {\n  }\n}\n"
		self.assertEqual(duplicates(src, "js"), [])

	def test_other_languages_allow_overloads(self):
		src = "class A {\n    void f(int a) {\n    }\n    void f(String a) {\n    }\n}\n"
		self.assertEqual(duplicates(src, "clike"), [])


class DurationTests(unittest.TestCase):
	def setUp(self):
		v040.CONF["codeCompass"] = smoke.default_config()

	def test_duration(self):
		self.assertEqual(codeCompass._duration(0.04), "under 0.1 seconds")
		self.assertEqual(codeCompass._duration(1.26), "1.3 seconds")
		self.assertEqual(codeCompass._duration(9.97), "10 seconds")
		self.assertEqual(codeCompass._duration(12.6), "13 seconds")
		self.assertEqual(codeCompass._duration(59.6), "1 minute")
		self.assertEqual(codeCompass._duration(61), "1 minute 1 second")
		self.assertEqual(codeCompass._duration(125), "2 minutes 5 seconds")

	def test_runner_reports_seconds(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		with open(os.path.join(folder, "main.py"), "w", encoding="utf-8") as f:
			f.write("import time\ntime.sleep(0.2)\n")
		report = os.path.join(folder, "report.json")
		subprocess.run([sys.executable, RUNNER, os.path.join(folder, "main.py"), report],
			stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
		with open(report, encoding="utf-8") as f:
			data = json.load(f)
		self.assertGreaterEqual(data["seconds"], 0.2)
		self.assertLess(data["seconds"], 10)


PY = (
	"def helper(x):\r\n"
	"    return x * 2\r\n"
	"\r\n"
	"def main():\r\n"
	"    a = 1\r\n"
	"    b = helper(a)\r\n"
	"    return b\r\n"
)


class FlavourCommandTests(v040.V040Tests):
	def setUp(self):
		super(FlavourCommandTests, self).setUp()
		codeCompass._history.clear()
		codeCompass._goToPending.clear()
		self.use(PY)

	def line(self):
		return self.ed.text.count("\n", 0, self.ed.caret)

	def test_back_and_forward_after_a_jump(self):
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		self.assertEqual(self.line(), 0)
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 5)
		self.assertEqual(self.ed.caret, self.ed.text.index("helper(a)") + 2)
		self.assertIn("line 6, in function main", self.spoken())
		self.plugin.script_goForward(None)
		self.assertEqual(self.line(), 0)
		self.plugin.script_goForward(None)
		self.assertEqual(self.message(), "No later place to go forward to")

	def test_back_follows_edits(self):
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		self.use("import os\r\n\r\n" + PY)
		self.at("def helper")
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 7)

	def test_small_steps_are_not_remembered(self):
		self.at("def helper")
		self.ed.script_ccNextDeclaration(Gesture("kb:alt+pageDown"))
		self.assertEqual(self.line(), 3)
		self.plugin.script_goBack(None)
		self.assertEqual(self.message(), "No earlier place to go back to")

	def test_back_skips_other_files_in_the_window(self):
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		self.use(PY, "other.py - Notepad")
		self.plugin.script_goBack(None)
		self.assertEqual(self.message(), "No earlier place to go back to")
		self.use(PY, "main.py - Notepad")
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 5)

	def test_control_g(self):
		self.at("def helper")
		gesture = Gesture("kb:control+g")
		self.ed.script_ccGoToLine(gesture)
		gesture.send.assert_called_once()
		# Notepad's dialog moved the caret to line 6.
		self.at("    b = helper")
		with mock.patch.object(smoke.FakeEditableText, "event_gainFocus", create=True):
			self.ed.event_gainFocus()
		self.run_later()
		self.assertIn("line 6, in function main", self.spoken())
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 0)

	def test_control_g_cancelled(self):
		self.at("def main")
		self.ed.script_ccGoToLine(Gesture("kb:control+g"))
		with mock.patch.object(smoke.FakeEditableText, "event_gainFocus", create=True):
			self.ed.event_gainFocus()
		MODS["speech"].speak.reset_mock()
		self.run_later()
		self.assertEqual(self.spoken(), [])
		self.plugin.script_goBack(None)
		self.assertEqual(self.message(), "No earlier place to go back to")

	def test_keys(self):
		gestures = codeCompass.CodeEditor._CodeEditor__gestures
		self.assertEqual(gestures["kb:control+alt+backspace"], "ccGoBack")
		self.assertEqual(gestures["kb:control+alt+shift+backspace"], "ccGoForward")
		self.assertEqual(gestures["kb:control+g"], "ccGoToLine")
		self.assertEqual(codeCompass.LAYER_GESTURES["kb:backspace"], "goBack")

	def test_run_time_message(self):
		self.plugin._run_finished({"status": 0, "error": None, "seconds": 1.26}, 7, "main.py")
		self.assertEqual(self.message(), "The program finished in 1.3 seconds, exit code 0")
		self.plugin._run_finished({"status": 0, "error": None}, 7, "main.py")
		self.assertEqual(self.message(), "The program finished, exit code 0")

	def test_where_am_i_and_family_lengths(self):
		self.at("    b = helper")
		self.plugin.script_family(None)
		self.assertEqual(self.message(), "function main, 4 lines, top level")
		self.use("def f():\r\n    pass\r\n")
		self.at("    pass")
		self.plugin.script_family(None)
		self.assertEqual(self.message(), "function f, 2 lines, top level")


# Keep the inherited V040 tests from running twice.
for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(FlavourCommandTests):
		setattr(FlavourCommandTests, _name, None)


if __name__ == "__main__":
	unittest.main()
