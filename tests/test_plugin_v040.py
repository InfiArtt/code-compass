# -*- coding: UTF-8 -*-
# Smoke tests for the 0.4.0 commands, against the stubbed NVDA modules of
# test_plugin_smoke. Text changes go to a fake Notepad edit control.

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import test_plugin_smoke as base  # noqa: E402

codeCompass = base.codeCompass
MODS = base.MODS
CONF = base.CONF
Gesture = base.Gesture

SWIFT = (
	"class Shop {\r\n"
	"    func bar() {\r\n"
	"        call(1,\r\n"
	"             2)\r\n"
	"    }\r\n"
	"    func baz() {\r\n"
	"        bar()\r\n"
	"    }\r\n"
	"}\r\n"
)

EDITORS = {}


class Editor(base.Editor):
	windowClassName = "Edit"

	def __init__(self, text, caret=0, handle=7):
		super(Editor, self).__init__(text, caret)
		self.windowHandle = handle
		self.newLines = 0
		EDITORS[handle] = self

	def script_caret_newLine(self, gesture):
		self.newLines += 1


def fake_replace(hwnd, text, start, end, newText, selStart=None, selEnd=None, timeout=None):
	ed = EDITORS[hwnd]
	assert ed.text == text, "edit made against stale text"
	ed.text = text[:start] + newText + text[end:]
	if selStart is None:
		ed.caret = start + len(newText)
		ed.selection = (ed.caret, ed.caret)
	else:
		selEnd = selStart if selEnd is None else selEnd
		ed.selection = (selStart, selEnd)
		ed.caret = selEnd
	return True


class V040Tests(unittest.TestCase):
	def setUp(self):
		for m in ("tones", "ui", "speech", "core", "api", "keyboardHandler"):
			for v in vars(MODS[m]).values():
				if isinstance(v, mock.MagicMock):
					v.reset_mock()
		CONF["codeCompass"] = base.default_config()
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name="Shop.swift - Notepad")
		codeCompass._cache = codeCompass._DocCache()
		codeCompass._runErrors.clear()
		codeCompass._runErrorPending.clear()
		self.plugin = codeCompass.GlobalPlugin()
		self.ed = Editor(SWIFT)
		MODS["api"].getFocusObject.return_value = self.ed
		patches = [
			mock.patch.object(codeCompass.edit_control, "replace", side_effect=fake_replace),
			mock.patch.object(codeCompass, "_writable_notepad", return_value=True),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def at(self, needle, extra=0):
		self.ed.caret = self.ed.text.index(needle) + extra
		self.ed.selection = (self.ed.caret, self.ed.caret)

	def use(self, text, title="main.py - Notepad"):
		self.ed.text = text
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name=title)

	def message(self):
		return MODS["ui"].message.call_args[0][0]

	def spoken(self):
		return [c[0][0][0] for c in MODS["speech"].speak.call_args_list]

	def run_later(self):
		"""Run the last core.callLater call."""
		args = MODS["core"].callLater.call_args[0]
		args[1](*args[2:])

	# Enter, Tab, comments -------------------------------------------------------------

	def test_enter_indents_after_brace(self):
		self.at("    func bar() {", len("    func bar() {"))
		self.ed.script_ccEnter(Gesture("kb:enter"))
		self.assertIn("    func bar() {\r\n        \r\n        call", self.ed.text)
		self.assertTrue(self.ed.spokeLine)

	def test_enter_splits_braces(self):
		self.use("func f() {}\r\n", "f.swift - Notepad")
		self.at("{}", 1)
		self.ed.script_ccEnter(Gesture("kb:enter"))
		self.assertEqual(self.ed.text, "func f() {\r\n    \r\n}\r\n")
		self.assertEqual(self.ed.caret, len("func f() {\r\n    "))

	def test_enter_falls_back_when_off(self):
		CONF["codeCompass"]["autoIndent"] = False
		self.ed.script_ccEnter(Gesture("kb:enter"))
		self.assertEqual(self.ed.newLines, 1)
		self.assertEqual(self.ed.text, SWIFT)

	def test_tab_indents_selected_lines(self):
		start = self.ed.text.index("    func baz")
		end = self.ed.text.index("    }\r\n}")
		self.ed.selection = (start, end)
		gesture = Gesture("kb:tab")
		self.ed.script_ccTab(gesture)
		gesture.send.assert_not_called()
		self.assertIn("        func baz() {\r\n            bar()\r\n    }", self.ed.text)
		self.assertEqual(self.message(), "Indented 2 lines")

	def test_plain_tab_passes_through(self):
		gesture = Gesture("kb:tab")
		self.ed.script_ccTab(gesture)
		gesture.send.assert_called_once()

	def test_shift_tab_outdents_caret_line(self):
		self.at("        bar()", 10)
		self.ed.script_ccShiftTab(Gesture("kb:shift+tab"))
		self.assertIn("\r\n    bar()\r\n", self.ed.text)
		self.assertEqual(self.ed.text[self.ed.caret - 2:self.ed.caret], "ba")

	def test_toggle_comment(self):
		self.at("        bar()")
		self.ed.script_ccToggleComment(Gesture("kb:control+/"))
		self.assertIn("        // bar()\r\n", self.ed.text)
		self.assertEqual(self.message(), "Commented")
		self.ed.script_ccToggleComment(Gesture("kb:control+/"))
		self.assertEqual(self.ed.text, SWIFT)

	def test_edit_keys_pass_through_elsewhere(self):
		with mock.patch.object(codeCompass, "_writable_notepad", return_value=False):
			gesture = Gesture("kb:control+/")
			self.ed.script_ccToggleComment(gesture)
			gesture.send.assert_called_once()
			self.plugin.script_toggleComment(None)
		self.assertEqual(self.message(), "This command changes text only in Windows 10 Notepad")

	# Completion and hints ----------------------------------------------------------------

	def test_completion_cycles_and_returns(self):
		self.use("currentUser = 1\ncurrency = 2\ncur\n")
		self.ed.caret = len(self.ed.text) - 1
		self.ed.selection = (self.ed.caret, self.ed.caret)
		self.plugin.script_complete(None)
		first = self.message()
		self.assertTrue(first.endswith("1 of 2"), first)
		self.plugin.script_complete(None)
		self.assertTrue(self.message().endswith("2 of 2"))
		self.plugin.script_complete(None)
		self.assertEqual(self.message(), "cur, as typed")
		self.assertTrue(self.ed.text.endswith("\ncur\n"))

	def test_no_suggestions(self):
		self.use("x = 1\nzz\n")
		self.ed.caret = len(self.ed.text) - 1
		self.plugin.script_complete(None)
		self.assertEqual(self.message(), "No suggestions")

	def test_parameter_hint(self):
		self.use("def load(user, animated=True):\n    pass\n\nload(me, ")
		self.ed.caret = len(self.ed.text)
		self.plugin.script_parameterHint(None)
		self.assertEqual(self.message(), "load(user, animated=True), argument 2")

	# Lines -----------------------------------------------------------------------------------

	def test_delete_line(self):
		self.at("        bar()")
		self.ed.script_ccDeleteLine(Gesture("kb:control+shift+k"))
		self.assertNotIn("bar()\r\n", self.ed.text.split("func baz")[1])
		self.assertEqual(self.spoken()[0], "Deleted")

	def test_move_line_up_and_down(self):
		self.use("a\r\nb\r\nc\r\n", "x.js - Notepad")
		self.at("b", 0)
		self.plugin.script_moveLineUp(None)
		self.assertEqual(self.ed.text, "b\r\na\r\nc\r\n")
		self.assertEqual(self.ed.caret, 0)
		self.plugin.script_moveLineDown(None)
		self.plugin.script_moveLineDown(None)
		self.assertEqual(self.ed.text, "a\r\nc\r\nb\r\n")
		self.assertEqual(self.ed.text[self.ed.caret], "b")

	def test_duplicate_line(self):
		self.use("a\r\nb\r\n", "x.js - Notepad")
		self.at("a")
		self.plugin.script_duplicateLine(None)
		self.assertEqual(self.ed.text, "a\r\na\r\nb\r\n")
		self.assertEqual(self.ed.caret, 3)

	# Problems ----------------------------------------------------------------------------------

	def test_next_problem_python(self):
		self.use("def f():\n    x = 1\n    return (x\n")
		self.plugin.script_nextProblem(None)
		self.assertTrue(self.spoken()[0].startswith("line 3:") or "line 3" in self.spoken()[0], self.spoken())
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 2)

	def test_no_problems(self):
		self.use("x = 1\n")
		self.plugin.script_nextProblem(None)
		self.assertEqual(self.message(), "No problems found")

	def test_error_sound_on_problem_line(self):
		CONF["codeCompass"]["soundStyle"] = "beeps"
		self.use("def f():\n    return (x\n")
		self.ed.caret = self.ed.text.index("return")
		self.ed._caretScriptPostMovedHelper(base.UNIT_LINE, None, None)
		calls = [c[0] for c in MODS["core"].callLater.call_args_list]
		self.assertTrue(any(c[1] is MODS["tones"].beep and c[2:] == codeCompass.ERROR_TONE for c in calls), calls)

	def test_problems_list(self):
		self.use("def f(:\n    pass\n")

		def showModal(dlg):
			dlg.choice = 0
			return 5100

		with mock.patch.object(codeCompass.ListDialog, "ShowModal", showModal, create=True):
			self.plugin.script_problemsList(None)
		self.run_later()
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 0)

	def test_save_reports_syntax_error(self):
		self.use("def f(:\n    pass\n")
		self.ed.script_ccSave(Gesture("kb:control+s"))
		self.run_later()
		self.assertEqual(self.message(), "Saved, but: 1 problem: line 1: invalid syntax")

	# Breadcrumbs ---------------------------------------------------------------------------------

	def test_breadcrumb_on_entering_a_function(self):
		self.at("        call")
		self.ed._caretScriptPostMovedHelper(base.UNIT_LINE, None, None)
		self.at("        bar()")
		MODS["speech"].speak.reset_mock()
		self.ed._caretScriptPostMovedHelper(base.UNIT_LINE, None, None)
		self.assertIn("in function baz", self.spoken())
		MODS["speech"].speak.reset_mock()
		self.at("        bar()", 2)
		self.ed._caretScriptPostMovedHelper(base.UNIT_LINE, None, None)
		self.assertNotIn("in function baz", self.spoken())

	# Names --------------------------------------------------------------------------------------

	def test_definition(self):
		self.at("        bar()", 9)
		self.plugin.script_definition(None)
		self.assertEqual(self.ed.caret, self.ed.text.index("bar() {"))

	def test_references(self):
		self.at("        bar()", 9)
		seen = {}

		def create(parent, title, label, labels, selection=0):
			seen.update(title=title, labels=labels)
			return mock.MagicMock(ShowModal=mock.MagicMock(return_value=5101))

		with mock.patch.object(codeCompass, "ListDialog", create):
			self.plugin.script_references(None)
		self.assertEqual(seen["title"], "Uses of bar: 2")

	def test_rename(self):
		self.at("        bar()", 9)

		class NameDialog(object):
			def __init__(self, *args):
				pass

			def Bind(self, *a, **k):
				pass

			def ShowModal(self):
				return 5100

			def GetValue(self):
				return "checkout"

			def Destroy(self):
				pass

		with mock.patch.object(MODS["wx"], "TextEntryDialog", NameDialog, create=True):
			self.plugin.script_rename(None)
		self.run_later()
		self.assertEqual(self.ed.text.count("checkout"), 2)
		self.assertNotIn("bar", self.ed.text)
		self.assertTrue(self.message().startswith("Renamed 2 places to checkout"))

	def test_todo_list(self):
		self.use("x = 1  # TODO: rename\n")
		seen = {}

		def create(parent, title, label, labels, selection=0):
			seen.update(labels=labels)
			return mock.MagicMock(ShowModal=mock.MagicMock(return_value=5101))

		with mock.patch.object(codeCompass, "ListDialog", create):
			self.plugin.script_todoList(None)
		self.assertEqual(seen["labels"], ["line 1, TODO: rename"])

	# Typing --------------------------------------------------------------------------------------

	def test_auto_close_and_type_over(self):
		CONF["codeCompass"]["autoClose"] = True
		self.use("f(\n", "x.js - Notepad")
		self.ed.caret = 2
		codeCompass._after_typed_character(self.ed, "(")
		self.assertEqual(self.ed.text, "f()\n")
		self.assertEqual(self.ed.caret, 2)
		self.use("f())\n", "x.js - Notepad")
		self.ed.caret = 3
		codeCompass._after_typed_character(self.ed, ")")
		self.assertEqual(self.ed.text, "f()\n")

	def test_closing_brace_lines_up(self):
		self.use("if x {\n    y()\n    }\n", "x.js - Notepad")
		self.ed.caret = self.ed.text.rindex("}") + 1
		codeCompass._after_typed_character(self.ed, "}")
		self.assertEqual(self.ed.text, "if x {\n    y()\n}\n")
		self.assertIn("closes if x", self.spoken())

	# Run, terminal, explorer, palette ---------------------------------------------------------------

	def test_run_and_f8_to_runtime_error(self):
		folder = tempfile.mkdtemp()
		path = os.path.join(folder, "main.py")
		self.use("print(1)\nx = 1 / 0\n")
		with mock.patch.object(codeCompass.subprocess, "Popen") as popen, \
			mock.patch.object(codeCompass.threading, "Thread") as thread, \
			mock.patch.object(codeCompass, "_python_command", return_value=["py", "-3"]):
			self.plugin._launch(self.ed, path)
		command = popen.call_args[0][0]
		self.addCleanup(lambda: os.path.exists(command[4]) and os.remove(command[4]))
		self.assertEqual(command[:2], ["py", "-3"])
		self.assertTrue(command[2].endswith("run_python.py"))
		self.assertEqual(command[3], path)
		self.assertEqual(popen.call_args[1]["cwd"], folder)
		thread.return_value.start.assert_called_once()
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError: division by zero"}}, 7)
		self.assertIn("line 2", self.message())
		self.plugin.script_nextProblem(None)
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 1)

	def test_run_needs_python_file(self):
		self.plugin.script_runFile(None)
		self.assertEqual(self.message(), "Running works for Python files")

	def test_run_untitled(self):
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name="Untitled - Notepad")
		self.plugin.script_runFile(None)
		self.assertEqual(self.message(), "Save the file first")

	def test_terminal_in_file_folder(self):
		folder = tempfile.mkdtemp()
		path = os.path.join(folder, "Shop.swift")
		open(path, "w").close()
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name=path + " - Notepad++")
		with mock.patch.object(codeCompass.subprocess, "Popen") as popen:
			self.plugin.script_terminal(None)
		self.assertEqual(popen.call_args[1]["cwd"], folder)

	def test_explorer_opens_project_root(self):
		root = tempfile.mkdtemp()
		os.mkdir(os.path.join(root, ".git"))
		os.mkdir(os.path.join(root, "src"))
		path = os.path.join(root, "src", "Shop.swift")
		other = os.path.join(root, "src", "Cart.swift")
		for p in (path, other):
			open(p, "w").close()
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name=path + " - Notepad++")
		seen = {}
		chosen = {"file": other}

		def create(parent, rootArg, current, openFile):
			seen.update(root=rootArg, current=current)
			return mock.MagicMock(ShowModal=mock.MagicMock(return_value=5100), choice=chosen["file"])

		with mock.patch.object(codeCompass, "ExplorerDialog", create), \
			mock.patch.object(codeCompass, "_open_in_editor") as opener:
			self.plugin.script_explorer(None)
			self.assertEqual(seen, {"root": root, "current": path})
			opener.assert_called_once_with(self.ed, other)
			# The file that is already open is not opened a second time.
			chosen["file"] = path
			self.plugin.script_explorer(None)
			self.assertEqual(opener.call_count, 1)
		self.run_later()
		self.assertEqual(self.message(), "Shop.swift is already open")

	# Review fixes ----------------------------------------------------------------------------

	def test_tab_with_one_whole_line_selected(self):
		start = self.ed.text.index("        bar()")
		self.ed.selection = (start, self.ed.text.index("    }\r\n}"))
		gesture = Gesture("kb:tab")
		self.ed.script_ccTab(gesture)
		gesture.send.assert_not_called()
		self.assertIn("\r\n            bar()\r\n", self.ed.text)

	def test_run_error_belongs_to_its_file(self):
		self.use("x = 1\ny = 2\nz = 3\n", "a.py - Notepad")
		self.plugin._run_finished({"status": 1, "error": {"line": 3, "message": "NameError: name 'q' is not defined"}}, 7, "a.py")
		a = codeCompass._cache.get(self.ed)
		self.assertEqual(len(codeCompass._problems(self.ed, a)), 1)
		self.use("x = 1\ny = 2\nz = 3\n", "b.py - Notepad")
		codeCompass._cache = codeCompass._DocCache()
		a = codeCompass._cache.get(self.ed)
		self.assertEqual(codeCompass._problems(self.ed, a), [])
		self.plugin.script_nextProblem(None)
		self.assertEqual(self.message(), "No problems found")

	def test_rename_keeps_caret_in_shorter_name(self):
		self.use("longname = 1\nprint(longname)\n", "x.py - Notepad")
		self.ed.caret = self.ed.text.index("longname)") + 6
		self.plugin._apply_rename(self.ed, self.ed.text, "longname", "ln")
		self.assertEqual(self.ed.text, "ln = 1\nprint(ln)\n")
		self.assertEqual(self.ed.caret, self.ed.text.index("ln)") + 2)

	def test_comment_with_caret_in_indentation(self):
		self.use("if x:\n    go()\n", "x.py - Notepad")
		self.ed.caret = self.ed.text.index("    go") + 1
		self.ed.selection = (self.ed.caret, self.ed.caret)
		self.plugin.script_toggleComment(None)
		self.assertEqual(self.ed.text, "if x:\n    # go()\n")
		self.assertEqual(self.ed.caret, self.ed.text.index("    #") + 1)

	def test_line_operation_without_gesture_reads_line(self):
		self.use("a\r\nb\r\n", "x.js - Notepad")
		self.at("a")
		with mock.patch.object(base.FakeEditableText, "_caretScriptPostMovedHelper", side_effect=AssertionError("needs a gesture")):
			self.plugin.script_duplicateLine(None)
		MODS["speech"].speakTextInfo.assert_called()

	def test_enter_says_the_typed_word(self):
		self.at("    func bar() {", len("    func bar() {"))
		self.ed.script_ccEnter(Gesture("kb:enter"))
		MODS["speech"].speakTypedCharacters.assert_called_with("\r")

	def test_explorer_entries(self):
		root = tempfile.mkdtemp()
		for name in ("b.py", "A.txt", "__pycache__", "zdir", ".git"):
			p = os.path.join(root, name)
			if "." in name and not name.startswith((".", "_")):
				open(p, "w").close()
			else:
				os.mkdir(p)
		folders, files = codeCompass._explorer_entries(root)
		self.assertEqual((folders, files), (["zdir"], ["A.txt", "b.py"]))

	def test_palette_lists_and_runs(self):
		seen = {}

		def create(parent, commands):
			seen["commands"] = commands
			dlg = mock.MagicMock(ShowModal=mock.MagicMock(return_value=5100))
			dlg.choice = "nextProblem"
			return dlg

		with mock.patch.object(codeCompass, "PaletteDialog", create):
			self.plugin.script_palette(None)
		labels = [label for label, name in seen["commands"]]
		self.assertTrue(any(label.endswith(": F8") for label in labels), labels[:5])
		self.assertEqual(len(seen["commands"]), len(codeCompass.PALETTE))
		self.use("x = 1\n")
		self.run_later()
		self.assertEqual(self.message(), "No problems found")


if __name__ == "__main__":
	unittest.main()
