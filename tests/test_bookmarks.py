# -*- coding: UTF-8 -*-
# Bookmarks: following lines through edits, saving per file, and the
# commands in the plugin.

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF
Gesture = v040.Gesture

import bookmarks  # noqa: E402
from bookmarks import Bookmark  # noqa: E402


def lines_of(text):
	return text.split("\n")


class ReanchorTests(unittest.TestCase):
	def test_unchanged(self):
		marks = [Bookmark(1, "b()")]
		self.assertFalse(bookmarks.reanchor(marks, ["a()", "b()", "c()"]))
		self.assertEqual(marks[0].line, 1)

	def test_lines_added_above(self):
		marks = [Bookmark(1, "b()")]
		self.assertTrue(bookmarks.reanchor(marks, ["x", "y", "a()", "b()", "c()"]))
		self.assertEqual((marks[0].line, marks[0].text), (3, "b()"))

	def test_lines_removed_above(self):
		marks = [Bookmark(3, "b()")]
		bookmarks.reanchor(marks, ["a()", "b()", "c()"])
		self.assertEqual(marks[0].line, 1)

	def test_line_edited_keeps_its_number(self):
		marks = [Bookmark(1, "b()")]
		bookmarks.reanchor(marks, ["a()", "b(1)", "c()"])
		self.assertEqual((marks[0].line, marks[0].text), (1, "b(1)"))

	def test_nearest_of_equal_lines(self):
		marks = [Bookmark(5, "}")]
		bookmarks.reanchor(marks, ["{", "}", "x", "y", "z", "w", "}", "q"])
		self.assertEqual(marks[0].line, 6)

	def test_clamped_marks_are_detached_not_merged(self):
		marks = [Bookmark(1, "b()"), Bookmark(9, "b()")]
		bookmarks.reanchor(marks, ["a()", "b()"])
		self.assertEqual([m.line for m in bookmarks.visible(marks)], [1])
		self.assertEqual(len(marks), 2)
		marks = [Bookmark(9, "gone")]
		bookmarks.reanchor(marks, ["a()", "b()"])
		self.assertEqual(marks[0].line, 1)

	def test_toggle_and_neighbour(self):
		marks = []
		self.assertTrue(bookmarks.toggle(marks, 4, "  d()  "))
		self.assertTrue(bookmarks.toggle(marks, 1, "b()"))
		self.assertEqual([(m.line, m.text) for m in marks], [(1, "b()"), (4, "d()")])
		self.assertEqual(bookmarks.neighbour(marks, 1, 1), (marks[1], False))
		self.assertEqual(bookmarks.neighbour(marks, 4, 1), (marks[0], True))
		self.assertEqual(bookmarks.neighbour(marks, 1, -1), (marks[1], True))
		self.assertEqual(bookmarks.neighbour(marks, 3, -1), (marks[0], False))
		self.assertFalse(bookmarks.toggle(marks, 4, "d()"))
		self.assertEqual(bookmarks.neighbour([], 0, 1), (None, False))


class StoreTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.path = os.path.join(self.folder, "sub", "bookmarks.json")

	def test_save_and_load(self):
		store = bookmarks.Store(self.path)
		store.get("c:\\p\\main.py").append(Bookmark(3, "def f():"))
		store.get(("window", 7)).append(Bookmark(0, "x"))
		store.touch("c:\\p\\main.py")
		self.assertTrue(store.save())
		with open(self.path, encoding="utf-8") as f:
			self.assertEqual(json.load(f), {"c:\\p\\main.py": [[3, "def f():"]]})
		again = bookmarks.Store(self.path)
		self.assertEqual([(m.line, m.text) for m in again.get("c:\\p\\main.py")], [(3, "def f():")])
		self.assertFalse(again.has(("window", 7)))

	def test_broken_file_is_ignored(self):
		os.makedirs(os.path.dirname(self.path))
		with open(self.path, "w", encoding="utf-8") as f:
			f.write('{"a": [[1, "x"], ["bad"], [-1, "y"]], "b": 5')
		self.assertEqual(bookmarks.Store(self.path).files, {})
		with open(self.path, "w", encoding="utf-8") as f:
			f.write('{"a": [[1, "x"], ["bad"], [-1, "y"]], "b": 5}')
		store = bookmarks.Store(self.path)
		self.assertEqual([(m.line, m.text) for m in store.get("a")], [(1, "x")])
		self.assertFalse(store.has("b"))

	def test_oldest_files_dropped(self):
		store = bookmarks.Store(self.path)
		for i in range(bookmarks.MAX_FILES + 5):
			store.get("f%d" % i).append(Bookmark(0, "x"))
		store.touch("f0")
		store.save()
		with open(self.path, encoding="utf-8") as f:
			data = json.load(f)
		self.assertEqual(len(data), bookmarks.MAX_FILES)
		self.assertIn("f0", data)
		self.assertNotIn("f1", data)

	def test_move_window_bookmarks_to_file(self):
		store = bookmarks.Store(self.path)
		store.get(("window", 7)).append(Bookmark(2, "x"))
		store.move(("window", 7), "c:\\p\\a.py")
		self.assertEqual(len(store.get("c:\\p\\a.py")), 1)
		self.assertFalse(store.has(("window", 7)))


PY = "def a():\r\n    pass\r\n\r\ndef b():\r\n    x = 1\r\n    return x\r\n\r\ndef c():\r\n    pass\r\n"


class BookmarkCommandTests(v040.V040Tests):
	def setUp(self):
		super(BookmarkCommandTests, self).setUp()
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.file = os.path.join(self.folder, "main.py")
		with open(self.file, "w", encoding="utf-8", newline="") as f:
			f.write(PY)
		codeCompass._bookmarkStore = bookmarks.Store(os.path.join(self.folder, "bookmarks.json"))
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		self.addCleanup(setattr, codeCompass, "_bookmarkStore", None)
		find = mock.patch.object(codeCompass.filepath, "find_file", return_value=self.file)
		self.find = find.start()
		self.addCleanup(find.stop)
		self.use(PY)

	def line(self):
		return self.ed.text.count("\n", 0, self.ed.caret)

	def test_toggle_next_previous(self):
		self.at("    x = 1")
		self.plugin.script_toggleBookmark(None)
		self.assertEqual(self.message(), "Bookmark added, line 5")
		self.at("def c")
		self.plugin.script_toggleBookmark(None)
		self.at("def a")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 4)
		self.assertIn("line 5, in function b", self.spoken())
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 7)
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 4)
		self.assertIn("back to the top, line 5, in function b", self.spoken())
		self.plugin.script_previousBookmark(None)
		self.assertEqual(self.line(), 7)
		self.assertIn("back to the bottom, line 8, in function c", self.spoken())
		self.plugin.script_toggleBookmark(None)
		self.assertEqual(self.message(), "Bookmark removed, line 8")

	def test_follows_lines_and_is_saved(self):
		self.at("    x = 1")
		self.plugin.script_toggleBookmark(None)
		with open(os.path.join(self.folder, "bookmarks.json"), encoding="utf-8") as f:
			self.assertEqual(json.load(f), {os.path.normcase(os.path.abspath(self.file)): [[4, "x = 1"]]})
		self.use("import os\r\nimport sys\r\n" + PY)
		self.at("def a")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 6)
		# A new NVDA session reads them back.
		codeCompass._bookmarkStore = None
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		with mock.patch.object(codeCompass.globalVars.appArgs, "configPath", self.folder):
			os.makedirs(os.path.join(self.folder, "codeCompass"))
			shutil.copy(os.path.join(self.folder, "bookmarks.json"), os.path.join(self.folder, "codeCompass", "bookmarks.json"))
			self.at("def a")
			self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 6)

	def test_only_bookmark_and_none(self):
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "No bookmarks in this file")
		self.at("def b")
		self.plugin.script_toggleBookmark(None)
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "This is the only bookmark")

	def test_tone_on_bookmarked_line(self):
		CONF["codeCompass"]["soundStyle"] = "beeps"
		self.at("def b")
		self.plugin.script_toggleBookmark(None)
		MODS["core"].callLater.reset_mock()
		self.ed._codeCompassLineReports()
		self.assertIn(codeCompass.BOOKMARK_TONE, [tuple(c[0][2:]) for c in MODS["core"].callLater.call_args_list])
		MODS["core"].callLater.reset_mock()
		self.at("def c")
		self.ed._codeCompassLineReports()
		self.assertNotIn(codeCompass.BOOKMARK_TONE, [tuple(c[0][2:]) for c in MODS["core"].callLater.call_args_list])
		CONF["codeCompass"]["bookmarkSound"] = False
		self.at("def b")
		self.ed._codeCompassLineReports()
		self.assertNotIn(codeCompass.BOOKMARK_TONE, [tuple(c[0][2:]) for c in MODS["core"].callLater.call_args_list])

	def test_moving_without_bookmarks_never_looks_for_the_file(self):
		self.find.reset_mock()
		self.at("def b")
		self.ed._codeCompassLineReports()
		self.find.assert_not_called()

	def test_list_delete_and_jump(self):
		for needle in ("def a", "    x = 1", "def c"):
			self.at(needle)
			self.plugin.script_toggleBookmark(None)
		seen = {}

		def create(parent, title, label, labels, selection=0, onDelete=None):
			seen.update(title=title, labels=list(labels), selection=selection)
			onDelete(0)
			dlg = mock.MagicMock(choice=1)
			return dlg

		def run_dialog(make, onClose):
			dlg = make()
			onClose(dlg, MODS["wx"].ID_OK)

		self.at("def b")
		with mock.patch.object(codeCompass, "ListDialog", create), \
			mock.patch.object(codeCompass, "_run_dialog", run_dialog):
			self.plugin.script_bookmarksList(None)
		self.assertEqual(seen["title"], "Bookmarks: 3")
		self.assertEqual(seen["labels"], ["line 1: def a():, in function a", "line 5: x = 1, in function b", "line 8: def c():, in function c"])
		self.assertEqual(seen["selection"], 1)
		self.run_later()
		self.assertEqual(self.line(), 7)
		self.assertEqual([m.line for m in codeCompass._bookmarkStore.get(os.path.normcase(os.path.abspath(self.file)))], [4, 7])

	def test_clear(self):
		self.at("def b")
		self.plugin.script_toggleBookmark(None)
		self.plugin.script_clearBookmarks(None)
		self.assertEqual(self.message(), "Removed 1 bookmark")
		self.plugin.script_clearBookmarks(None)
		self.assertEqual(self.message(), "No bookmarks in this file")

	def test_untitled_document_keeps_bookmarks_when_saved(self):
		self.find.return_value = None
		self.use(PY, "Untitled - Notepad")
		self.at("def b")
		self.plugin.script_toggleBookmark(None)
		self.find.return_value = self.file
		self.use(PY, "main.py - Notepad")
		self.at("def a")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 3)
		self.assertTrue(codeCompass._bookmarkStore.has(os.path.normcase(os.path.abspath(self.file))))

	def test_palette_lists_bookmark_commands(self):
		seen = {}

		def create(parent, commands):
			seen["commands"] = commands
			return mock.MagicMock()

		with mock.patch.object(codeCompass, "PaletteDialog", create), \
			mock.patch.object(codeCompass, "_run_dialog", lambda make, onClose: make()):
			self.plugin.script_palette(None)
		labels = dict((name, label) for label, name in seen["commands"])
		self.assertEqual(labels["nextBookmark"], "Moves to the next bookmark: control+alt+L")
		self.assertEqual(labels["clearBookmarks"], "Removes every bookmark in the file")

	def test_quick_keys(self):
		gestures = codeCompass.CodeEditor._CodeEditor__gestures
		self.assertEqual(gestures["kb:control+alt+k"], "ccToggleBookmark")
		self.assertEqual(codeCompass.LAYER_GESTURES["kb:shift+b"], "bookmarksList")
		self.at("def b")
		self.ed.script_ccToggleBookmark(Gesture("kb:control+alt+k"))
		self.assertEqual(self.message(), "Bookmark added, line 4")


# Keep the inherited V040 tests from running twice.
for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(BookmarkCommandTests):
		setattr(BookmarkCommandTests, _name, None)


if __name__ == "__main__":
	unittest.main()
