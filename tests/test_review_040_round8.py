# -*- coding: UTF-8 -*-
# Regression tests for the review of the sounds round: problems while
# typing (repeats, Indonesian, other files), line sounds of a line already
# left, saving and Save As, bookmarks through cut and paste and deletes,
# history of new documents, auto-close with the caret moved and Backspace,
# go/try calls, and the environment for programs.

import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_sounds  # noqa: E402

v040 = test_sounds.v040
codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF
played = test_sounds.played

import bookmarks  # noqa: E402
import problems  # noqa: E402
from analyzer import Analysis  # noqa: E402
from bookmarks import Bookmark  # noqa: E402


class LiveTests(test_sounds.SoundTests):
	def setUp(self):
		super(LiveTests, self).setUp()
		MODS["api"].getFocusObject.return_value = self.ed
		codeCompass._catalogs.clear()
		self.addCleanup(codeCompass._catalogs.clear)

	def pause(self, text, title="main.py - Notepad"):
		"""Type until text, then pause: return the sounds of that check."""
		MODS["nvwave"].playWaveFile.reset_mock()
		MODS["core"].callLater.reset_mock()
		self.use(text, title)
		codeCompass._schedule_live_check(self.ed)
		self.live()
		return played()

	def test_an_old_problem_never_sounds_again(self):
		self.use("x = 1\n")
		codeCompass._schedule_live_check(self.ed)
		sounds = [self.pause(t) for t in ("x = foo(\n", "x = foo(a\n", "x = foo(a,\n", "x = foo(a, b\n", "x = foo(a, b, c\n")]
		self.assertEqual(sounds, [["error"], [], [], [], []])

	def test_indonesian_messages(self):
		CONF["codeCompass"]["language"] = "id"
		self.use("const a = 1;\n", "x.js - Notepad")
		codeCompass._schedule_live_check(self.ed)
		texts = ("const a = f(1;\n", "const a = f(12;\n", "const a = f(123, b;\n", "// c\nconst a = f(123, b;\n")
		sounds = [self.pause(t, "x.js - Notepad") for t in texts]
		self.assertEqual(sounds, [["error"], [], [], []])

	def test_another_document_starts_fresh(self):
		self.use("x = 1\n", "C:\\p\\a.py - Notepad++")
		codeCompass._schedule_live_check(self.ed)
		self.pause("x = 12\n", "C:\\p\\a.py - Notepad++")
		dup = "def load():\n    pass\n\ndef load():\n    pass\nz\n"
		self.assertEqual(self.pause(dup, "C:\\p\\b.py - Notepad++"), [])
		self.assertEqual(self.pause(dup + "zz\n", "C:\\p\\b.py - Notepad++"), [])

	def test_beeps_style_on_save(self):
		CONF["codeCompass"]["soundStyle"] = "beeps"
		self.use("def f():\n    return (1\n", "main.py - Notepad")
		codeCompass._after_save(self.ed)
		MODS["tones"].beep.assert_called_with(*codeCompass.ERROR_TONE)

	def test_line_sounds_stop_when_the_caret_moves_on(self):
		self.use("def f():\n    return (x\n")
		self.ed.caret = self.ed.text.index("return")
		timer = MODS["core"].callLater.return_value
		timer.Stop.reset_mock()
		self.ed._codeCompassLineReports()
		self.ed.caret = 0
		self.ed._codeCompassLineReports()
		timer.Stop.assert_called()

	def test_cancelled_save_as_says_nothing(self):
		self.use("x = 1\n", "main.py - Notepad")
		codeCompass._before_save(self.ed)
		MODS["ui"].message.reset_mock()
		codeCompass._after_save(self.ed, True)
		MODS["ui"].message.assert_not_called()
		self.assertNotIn(7, codeCompass._saveSnapshots)

	def test_go_and_try_calls_are_not_declarations(self):
		go = "func walk(n *Node, ch chan int) {\n\tif n == nil {\n\t\treturn\n\t}\n\tgo walk(n.Left, ch)\n\tgo walk(n.Right, ch)\n}\n"
		self.assertEqual(problems.find_problems(Analysis(go, "clike")), [])
		swift = "func fetch(_ n: Int) throws -> Int {\n    try fetch(n - 1)\n    return 0\n}\n"
		self.assertEqual(problems.find_problems(Analysis(swift, "swift")), [])


for _name in list(vars(test_sounds.SoundTests)) + list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(LiveTests):
		setattr(LiveTests, _name, None)


def follow(marks, old, new):
	bookmarks.reanchor(marks, new, old)
	return [(m.line, m.text, m.detached) for m in marks]


class BookmarkTests(unittest.TestCase):
	def test_cut_move_then_paste(self):
		lines = ["def a():", "    x = 1", "    y = 2", "    return x", "", "def b():", "    pass"]
		marks = [Bookmark(1, "x = 1")]
		cut = lines[:1] + lines[3:]
		follow(marks, lines, cut)
		pasted = cut + ["    x = 1", "    y = 2"]
		self.assertEqual(follow(marks, cut, pasted), [(5, "x = 1", False)])

	def test_deleted_line_does_not_jump_to_its_twin(self):
		lines = ["function f() {", "  if (x) {", "    go();", "  }", "}", "", "g();"]
		new = lines[:3] + lines[4:]
		self.assertEqual(follow([Bookmark(3, "}")], lines, new), [(3, "}", True)])

	def test_out_of_range_mapping(self):
		self.assertEqual(follow([Bookmark(20, "x")], ["a", "b", "c"], ["x"] * 30 + ["a", "b", "c"]), [(20, "x", True)])

	def test_many_identical_lines_are_quick(self):
		old = (["    }", "}", "return x;", "item"] * 2000)
		new = ["changed"] + old[1:-1] + ["changed too"]
		marks = [Bookmark(i, old[i].strip()) for i in range(5, 8000, 400)]
		start = time.perf_counter()
		bookmarks.reanchor(marks, new, old)
		self.assertLess(time.perf_counter() - start, 1.0)
		self.assertEqual([m.line for m in bookmarks.visible(marks)], list(range(5, 8000, 400)))


PY = "def a():\r\n    pass\r\n\r\ndef b():\r\n    x = 1\r\n    return x\r\n"


class EditorTests(v040.V040Tests):
	def setUp(self):
		super(EditorTests, self).setUp()
		codeCompass._autoClosed.clear()
		codeCompass._history.clear()
		codeCompass._historyTitles.clear()
		codeCompass._saveSnapshots.clear()
		CONF["codeCompass"]["autoClose"] = True

	def type(self, chars):
		for ch in chars:
			self.ed.text = self.ed.text[:self.ed.caret] + ch + self.ed.text[self.ed.caret:]
			self.ed.caret += 1
			self.ed.selection = (self.ed.caret, self.ed.caret)
			codeCompass._after_typed_character(self.ed, ch)

	def move(self, offset):
		self.ed.caret = offset
		self.ed.selection = (offset, offset)
		self.ed._caretScriptPostMovedHelper(v040.base.UNIT_LINE, None, None)

	def test_a_closer_typed_after_coming_back_stays(self):
		self.use("\r\n", "x.py - Notepad")
		self.ed.caret = 0
		self.type("print(")
		self.type("x")
		self.move(self.ed.text.index("x"))
		self.type("abs(")
		self.move(self.ed.text.index("x") + 1)
		self.type(")")
		self.assertEqual(self.ed.text, "print(abs(x))\r\n")

	def test_backspace_removes_the_pair(self):
		self.use("\r\n", "x.py - Notepad")
		self.ed.caret = 0
		self.type("f(")
		self.assertEqual(self.ed.text, "f()\r\n")
		self.ed.script_ccBackspace(v040.Gesture("kb:backspace"))
		self.assertEqual(self.ed.text, "f\r\n")
		MODS["speech"].speakSpelling.assert_called_with("(")
		# Elsewhere Backspace is Notepad's own.
		self.ed.script_ccBackspace(v040.Gesture("kb:backspace"))
		self.assertEqual(self.ed.text, "\r\n")

	def test_fresh_untitled_drops_old_places(self):
		self.ed.appModule = types.SimpleNamespace(appName="notepad")
		self.use(PY, "*Untitled - Notepad")
		self.at("return x")
		self.plugin.script_toggleBookmark = None
		self.at("x = 1")
		self.plugin.script_goBack(None)  # nothing yet
		codeCompass._remember_place(self.ed, codeCompass._cache.get(self.ed), self.ed.text.index("return x"))
		self.use("", "Untitled - Notepad")
		self.use("print(1)\r\n" * 10, "*Untitled - Notepad")
		self.ed.caret = 0
		self.plugin.script_goBack(None)
		self.assertEqual(self.message(), "No earlier place to go back to")

	def test_notepad_plus_plus_new_tab_saved(self):
		self.ed.appModule = types.SimpleNamespace(appName="notepad++")
		self.use(PY, "*new 1 - Notepad++")
		codeCompass._remember_place(self.ed, codeCompass._cache.get(self.ed), self.ed.text.index("return x"))
		codeCompass._before_save(self.ed)
		self.use(PY, "C:\\x\\a.py - Notepad++")
		self.ed.caret = 0
		self.plugin.script_goBack(None)
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 5)


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(EditorTests):
		setattr(EditorTests, _name, None)


class SaveOverSeenFileTests(v040.V040Tests):
	def test_untitled_saved_over_a_file_seen_before(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		path = os.path.join(folder, "main.py")
		with open(path, "w", encoding="utf-8", newline="") as f:
			f.write("a\r\nb\r\nc\r\n")
		codeCompass._bookmarkStore = bookmarks.Store(os.path.join(folder, "bookmarks.json"))
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		codeCompass._saveSnapshots.clear()
		self.addCleanup(setattr, codeCompass, "_bookmarkStore", None)
		MODS["api"].getFocusObject.return_value = self.ed
		with mock.patch.object(codeCompass.filepath, "find_file", return_value=path) as find:
			self.use("a\r\nb\r\nc\r\n", "main.py - Notepad")
			self.at("b")
			self.plugin.script_toggleBookmark(None)
			find.return_value = None
			text = "".join("line %d\r\n" % i for i in range(30))
			self.use(text, "*Untitled - Notepad")
			self.at("line 20")
			self.plugin.script_toggleBookmark(None)
			codeCompass._before_save(self.ed)
			with open(path, "w", encoding="utf-8", newline="") as f:
				f.write(text)
			find.return_value = path
			self.use(text, "main.py - Notepad")
			codeCompass._after_save(self.ed, True)
			self.at("line 0")
			self.plugin.script_nextBookmark(None)
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 20)


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(SaveOverSeenFileTests):
		setattr(SaveOverSeenFileTests, _name, None)


if __name__ == "__main__":
	unittest.main()
