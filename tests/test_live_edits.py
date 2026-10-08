# -*- coding: UTF-8 -*-
# Problems found after any edit, not only typing: deleting indentation,
# Delete and Backspace, pasting, and Code Compass's own commands.

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_sounds  # noqa: E402

v040 = test_sounds.v040
codeCompass = v040.codeCompass
MODS = v040.MODS
Gesture = v040.Gesture
played = test_sounds.played

import problems  # noqa: E402


class PythonCompileTests(unittest.TestCase):
	def test_dedented_return_and_break(self):
		self.assertEqual([p.message for p in problems.python_problems("def f():\n    x = 1\nreturn x\n")], ["'return' outside function"])
		self.assertEqual([p.message for p in problems.python_problems("for i in r:\n    pass\nbreak\n")], ["'break' outside loop"])
		self.assertEqual(problems.python_problems("def f():\n    x = 1\n    return x\n"), [])


PY = "def f():\r\n    x = 1\r\n    return x\r\n"


class EditTests(test_sounds.SoundTests):
	def setUp(self):
		super(EditTests, self).setUp()
		MODS["api"].getFocusObject.return_value = self.ed
		self.use(PY, "main.py - Notepad")

	def checks(self):
		return [c[0] for c in MODS["core"].callLater.call_args_list if c[0][1] is codeCompass._live_check]

	def run_check(self):
		calls = self.checks()
		calls[-1][1](*calls[-1][2:])

	def test_deleting_indentation_with_delete(self):
		# The caret at the start of "    return x"; Delete removes 4 spaces.
		self.ed.caret = PY.index("    return")

		def delete(gesture):
			for _ in range(4):
				self.ed.text = self.ed.text[:self.ed.caret] + self.ed.text[self.ed.caret + 1:]

		with mock.patch.object(type(self.ed), "script_caret_deleteCharacter", create=True, side_effect=delete):
			self.ed.script_ccDelete(Gesture("kb:delete"))
		self.assertTrue(self.checks())
		self.run_check()
		self.assertEqual(played(), ["error"])

	def test_backspace_schedules_a_check(self):
		self.ed.caret = PY.index("return")
		self.ed.script_ccBackspace(Gesture("kb:backspace"))
		self.assertTrue(self.checks())

	def test_paste_schedules_a_check(self):
		gesture = Gesture("kb:control+v")
		self.ed.script_ccPasteOrCut(gesture)
		gesture.send.assert_called_once()
		self.assertTrue(self.checks())

	def test_commands_schedule_a_check(self):
		# shift+tab on the return line: "return x" leaves the function.
		self.ed.caret = PY.index("    return") + 6
		self.ed.selection = (self.ed.caret, self.ed.caret)
		self.ed.script_ccShiftTab(Gesture("kb:shift+tab"))
		self.assertIn("\r\nreturn x", self.ed.text)
		self.run_check()
		self.assertEqual(played(), ["error"])

	def test_keys(self):
		gestures = codeCompass.CodeEditor._CodeEditor__gestures
		self.assertEqual(gestures["kb:delete"], "ccDelete")
		self.assertEqual(gestures["kb:control+v"], "ccPasteOrCut")
		self.assertEqual(gestures["kb:control+backspace"], "ccBackspaceWord")


for _name in list(vars(test_sounds.SoundTests)) + list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(EditTests):
		setattr(EditTests, _name, None)


if __name__ == "__main__":
	unittest.main()
