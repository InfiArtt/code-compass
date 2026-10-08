# -*- coding: UTF-8 -*-
# Undo and redo of many steps in Windows 10's Notepad.

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF
Gesture = v040.Gesture

import undo  # noqa: E402


def apply(text, change):
	start, end, replacement = change
	return text[:start] + replacement + text[end:]


class HistoryTests(unittest.TestCase):
	def test_undo_and_redo_steps(self):
		h = undo.History("a\r\n")
		for text in ("ab\r\n", "abc\r\n", "x\r\nabc\r\n"):
			h.record(text)
		text = "x\r\nabc\r\n"
		seen = []
		while True:
			change = h.undo(text)
			if change is None:
				break
			text = apply(text, change)
			seen.append(text)
		self.assertEqual(seen, ["abc\r\n", "ab\r\n", "a\r\n"])
		for want in ("ab\r\n", "abc\r\n", "x\r\nabc\r\n"):
			text = apply(text, h.redo(text))
			self.assertEqual(text, want)
		self.assertIsNone(h.redo(text))

	def test_typing_since_the_last_stop_is_a_step(self):
		h = undo.History("a")
		h.record("ab")
		# "c" was typed with no stop yet: undo takes it back first.
		self.assertEqual(apply("abc", h.undo("abc")), "ab")
		self.assertEqual(apply("ab", h.undo("ab")), "a")

	def test_new_typing_ends_redo(self):
		h = undo.History("a")
		h.record("ab")
		text = apply("ab", h.undo("ab"))
		self.assertIsNone(h.redo(text + "z"))
		self.assertFalse(h.can_redo())
		self.assertEqual(apply("az", h.undo("az")), "a")

	def test_limits(self):
		h = undo.History("")
		for i in range(undo.MAX_STEPS + 50):
			h.record("x" * (i + 1))
		self.assertEqual(len(h.steps), undo.MAX_STEPS)
		self.assertEqual(h.index, undo.MAX_STEPS)

	def test_crlf_stays_whole(self):
		step = undo.diff("a\r\nb", "a\r\n\r\nb")
		self.assertEqual("a\r\nb"[:step.start] + step.new + "a\r\nb"[step.start + len(step.old):], "a\r\n\r\nb")
		self.assertNotEqual("a\r\n\r\nb"[step.start - 1:step.start + 1], "\r\n"[0:1] + "\n")


PY = "def a():\r\n    pass\r\n"


class NotepadTests(v040.V040Tests):
	def setUp(self):
		super(NotepadTests, self).setUp()
		codeCompass._undoHistories.clear()
		codeCompass._undoStops.clear()
		codeCompass._disk.clear()
		patcher = mock.patch.object(codeCompass.edit_control, "is_modified", return_value=True)
		self.modified = patcher.start()
		self.addCleanup(patcher.stop)
		mark = mock.patch.object(codeCompass.edit_control, "mark_unmodified")
		self.mark = mark.start()
		self.addCleanup(mark.stop)
		self.use(PY, "main.py - Notepad")
		codeCompass._undo_record(self.ed)

	def type(self, chars, pause=True):
		for ch in chars:
			self.ed.text = self.ed.text[:self.ed.caret] + ch + self.ed.text[self.ed.caret:]
			self.ed.caret += 1
			self.ed.selection = (self.ed.caret, self.ed.caret)
			codeCompass._after_typed_character(self.ed, ch)
		if pause:
			codeCompass._undo_record(self.ed)

	def undo(self):
		gesture = Gesture("kb:control+z")
		self.ed.script_ccUndo(gesture)
		return gesture

	def redo(self):
		gesture = Gesture("kb:control+y")
		self.ed.script_ccRedo(gesture)
		return gesture

	def test_many_steps_back_and_forward(self):
		self.ed.caret = len(PY)
		self.type("x = 1")
		self.type("\r\ny = 2")
		self.type("\r\nz = 3", pause=False)
		self.undo()
		self.assertEqual(self.ed.text, PY + "x = 1\r\ny = 2")
		self.undo()
		self.assertEqual(self.ed.text, PY + "x = 1")
		self.undo()
		self.assertEqual(self.ed.text, PY)
		self.redo()
		self.redo()
		self.assertEqual(self.ed.text, PY + "x = 1\r\ny = 2")
		self.assertEqual(self.ed.caret, len(self.ed.text))

	def test_command_is_one_step(self):
		self.at("    pass")
		self.plugin.script_deleteLine(None)
		self.assertEqual(self.ed.text, "def a():\r\n")
		self.undo()
		self.assertEqual(self.ed.text, PY)

	def test_auto_close_joins_the_typing(self):
		CONF["codeCompass"]["autoClose"] = True
		self.ed.caret = len(PY)
		self.type("print(")
		self.assertEqual(self.ed.text, PY + "print()")
		self.undo()
		self.assertEqual(self.ed.text, PY)

	def test_nothing_recorded_leaves_it_to_notepad(self):
		gesture = self.undo()
		gesture.send.assert_called_once()

	def test_nothing_more_to_undo_or_redo(self):
		self.ed.caret = len(PY)
		self.type("x")
		self.undo()
		gesture = self.undo()
		gesture.send.assert_not_called()
		self.assertEqual(self.message(), "Nothing to undo")
		self.redo()
		self.redo()
		self.assertEqual(self.message(), "Nothing to redo")

	def test_back_to_the_saved_text_clears_the_star(self):
		codeCompass._disk[7] = {"title": "main.py - Notepad", "path": "x", "stamp": None, "text": PY}
		self.ed.caret = len(PY)
		self.type("x")
		self.undo()
		self.mark.assert_called_once_with(7)

	def test_another_document_starts_a_new_history(self):
		self.ed.caret = len(PY)
		self.type("x")
		self.use("other\r\n", "other.py - Notepad")
		gesture = self.undo()
		gesture.send.assert_called_once()
		self.assertEqual(self.ed.text, "other\r\n")

	def test_file_open_of_a_same_named_file(self):
		self.ed.caret = len(PY)
		self.type("x")
		# File > Open of another main.py: Notepad calls it unchanged.
		self.modified.return_value = False
		self.use("print('B')\r\n", "main.py - Notepad")
		self.ed.caret = 0
		self.ed._caretScriptPostMovedHelper(v040.base.UNIT_LINE, None, None)
		self.modified.return_value = True
		gesture = self.undo()
		self.assertEqual(self.ed.text, "print('B')\r\n")
		gesture.send.assert_called_once()

	def test_turned_off(self):
		CONF["codeCompass"]["multiUndo"] = False
		self.ed.caret = len(PY)
		self.type("x")
		gesture = self.undo()
		gesture.send.assert_called_once()
		self.assertEqual(self.ed.text, PY + "x")

	def test_not_in_other_editors(self):
		with mock.patch.object(codeCompass, "_writable_notepad", return_value=False):
			gesture = self.undo()
		gesture.send.assert_called_once()

	# Review round.

	def focus(self):
		with mock.patch.object(v040.base.FakeEditableText, "event_gainFocus", create=True):
			self.ed.event_gainFocus()

	def test_file_open_after_save_never_brings_back_the_old_text(self):
		self.ed.caret = len(PY)
		self.type("x")
		codeCompass._before_save(self.ed)
		# File > Open other.py: Notepad calls the new document unchanged.
		self.modified.return_value = False
		self.use("other\r\n", "other.py - Notepad")
		self.ed.caret = 0
		self.focus()
		self.modified.return_value = True
		gesture = self.undo()
		gesture.send.assert_called_once()
		self.assertEqual(self.ed.text, "other\r\n")
		# Typing at the top, then undo: only that typing goes.
		self.type("# ")
		self.undo()
		self.assertEqual(self.ed.text, "other\r\n")

	def test_file_new_in_an_untitled_document(self):
		self.use("", "Untitled - Notepad")
		self.focus()
		self.ed.caret = 0
		self.type("secret draft")
		self.modified.return_value = False
		self.use("", "Untitled - Notepad")
		self.ed.caret = 0
		self.focus()
		self.modified.return_value = True
		gesture = self.undo()
		gesture.send.assert_called_once()
		self.assertEqual(self.ed.text, "")

	def test_first_typing_after_opening_can_be_undone(self):
		self.use("x = 1\r\n", "fresh.py - Notepad")
		self.ed.caret = 0
		self.focus()
		self.type("# a\r\n", pause=False)
		self.type("# b\r\n")
		self.undo()
		self.undo()
		self.assertEqual(self.ed.text, "x = 1\r\n")

	def test_a_pause_with_another_window_in_front_keeps_the_steps(self):
		with mock.patch.object(codeCompass.edit_control, "top_window", return_value=(100, "main.py - Notepad")):
			codeCompass._undoHistories.clear()
			codeCompass._undo_record(self.ed)
			self.ed.caret = len(PY)
			self.type("x = 1")
			self.type("\r\ny = 2", pause=False)
			# The Find dialog is in front when the typing pause ends.
			MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name="Find")
			codeCompass._undo_record(self.ed)
			MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name="*main.py - Notepad")
			self.undo()
			self.undo()
		self.assertEqual(self.ed.text, PY)

	def test_history_belongs_to_notepads_own_window(self):
		with mock.patch.object(codeCompass.edit_control, "top_window", return_value=(100, "*main.py - Notepad")):
			self.assertEqual(codeCompass._undo_key(self.ed), (100, "main.py - Notepad"))

	def test_large_file_steps_are_quick(self):
		import time
		big = "x = 1\r\n" * 700000
		h = undo.History(big)
		start = time.perf_counter()
		h.record(big[:2000000] + "y" + big[2000000:])
		self.assertLess(time.perf_counter() - start, 0.2)
		self.assertEqual(h.steps[-1].start, 2000000)

	def test_keys(self):
		gestures = codeCompass.CodeEditor._CodeEditor__gestures
		self.assertEqual(gestures["kb:control+z"], "ccUndo")
		self.assertEqual(gestures["kb:control+y"], "ccRedo")
		self.assertEqual(gestures["kb:control+shift+z"], "ccRedo")


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(NotepadTests):
		setattr(NotepadTests, _name, None)


if __name__ == "__main__":
	unittest.main()
