# -*- coding: UTF-8 -*-
# VS Code's sounds, and problems found while typing.

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF
base = v040.base


def played():
	"""Names of the VS Code sounds played, directly or later."""
	names = []
	for c in MODS["nvwave"].playWaveFile.call_args_list:
		names.append(os.path.basename(c[0][0])[:-4])
	for c in MODS["core"].callLater.call_args_list:
		if len(c[0]) > 1 and c[0][1] is MODS["nvwave"].playWaveFile:
			names.append(os.path.basename(c[0][2])[:-4])
	return names


class SoundTests(v040.V040Tests):
	def setUp(self):
		super(SoundTests, self).setUp()
		MODS["nvwave"].playWaveFile.reset_mock()
		codeCompass._liveProblems.clear()
		codeCompass._liveChecks.clear()

	def test_sound_files_exist(self):
		for name in ("error", "warning", "break", "save", "taskCompleted", "taskFailed", "codeActionApplied"):
			self.assertTrue(os.path.isfile(os.path.join(codeCompass.SOUNDS_DIR, name + ".wav")), name)
		self.assertTrue(os.path.isfile(os.path.join(codeCompass.SOUNDS_DIR, "LICENSE-vscode.txt")))

	def test_error_and_warning_lines(self):
		self.use("def f():\n    return (x\n")
		self.ed.caret = self.ed.text.index("return")
		self.ed._codeCompassLineReports()
		self.assertEqual(played(), ["error"])
		MODS["core"].callLater.reset_mock()
		self.use("def main():\n    def main():\n        pass\n")
		self.ed.caret = self.ed.text.index("    def main")
		self.ed._codeCompassLineReports()
		self.assertEqual(played(), ["warning"])

	def test_beeps_style(self):
		CONF["codeCompass"]["soundStyle"] = "beeps"
		self.use("def f():\n    return (x\n")
		self.ed.caret = self.ed.text.index("return")
		self.ed._codeCompassLineReports()
		self.assertEqual(played(), [])
		calls = [c[0] for c in MODS["core"].callLater.call_args_list]
		self.assertTrue(any(c[1] is MODS["tones"].beep for c in calls))

	def test_save_sounds(self):
		MODS["api"].getFocusObject.return_value = self.ed
		self.use("def f():\n    return 1\n", "main.py - Notepad")
		codeCompass._after_save(self.ed)
		self.assertEqual(played(), ["save"])
		self.assertEqual(self.message(), "Saved, no problems")
		MODS["nvwave"].playWaveFile.reset_mock()
		self.use("def f():\n    return (1\n", "main.py - Notepad")
		codeCompass._after_save(self.ed)
		self.assertEqual(played(), ["error"])

	def test_run_sounds(self):
		self.plugin._run_finished({"status": 0, "error": None, "seconds": 1}, 7, "main.py")
		self.assertEqual(played(), ["taskCompleted"])
		MODS["nvwave"].playWaveFile.reset_mock()
		self.use("print(1)\nx = 1 / 0\n")
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError"}}, 7, "main.py")
		self.assertEqual(played(), ["taskFailed"])

	def live(self):
		"""Run the latest scheduled check."""
		calls = [c[0] for c in MODS["core"].callLater.call_args_list if c[0][1] is codeCompass._live_check]
		calls[-1][1](*calls[-1][2:])

	def test_new_problem_while_typing(self):
		MODS["api"].getFocusObject.return_value = self.ed
		self.use("def f():\n    return 1\n", "main.py - Notepad")
		self.ed.caret = self.ed.text.index("1")
		codeCompass._schedule_live_check(self.ed)
		self.use("def f():\n    return (1\n", "main.py - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.live()
		self.assertEqual(played(), ["error"])
		# Still the same problem after more typing on that line: no new sound.
		MODS["nvwave"].playWaveFile.reset_mock()
		self.use("def f():\n    return (12\n", "main.py - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.live()
		self.assertEqual(played(), [])

	def test_say_new_problems(self):
		CONF["codeCompass"]["liveCheck"] = "speech"
		MODS["api"].getFocusObject.return_value = self.ed
		self.use("const a = 1;\n", "x.js - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.use("const a = f(1;\n", "x.js - Notepad")
		self.ed.caret = 5
		codeCompass._schedule_live_check(self.ed)
		self.live()
		self.assertEqual(played(), ["error"])
		self.assertTrue(any("unclosed paren" in s for s in self.spoken()))

	def test_off_and_plain_text(self):
		MODS["api"].getFocusObject.return_value = self.ed
		self.use("notes\n", "notes.txt - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.use("notes (see below\n", "notes.txt - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.live()
		self.assertEqual(played(), [])
		CONF["codeCompass"]["liveCheck"] = "off"
		MODS["core"].callLater.reset_mock()
		codeCompass._schedule_live_check(self.ed)
		self.assertEqual([c for c in MODS["core"].callLater.call_args_list if c[0][1] is codeCompass._live_check], [])

	def test_only_the_latest_check_runs(self):
		MODS["api"].getFocusObject.return_value = self.ed
		self.use("def f():\n    return 1\n", "main.py - Notepad")
		codeCompass._schedule_live_check(self.ed)
		self.use("def f():\n    return (1\n", "main.py - Notepad")
		codeCompass._schedule_live_check(self.ed)
		first = [c[0] for c in MODS["core"].callLater.call_args_list if c[0][1] is codeCompass._live_check][0]
		first[1](*first[2:])
		self.assertEqual(played(), [])


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(SoundTests):
		setattr(SoundTests, _name, None)


if __name__ == "__main__":
	unittest.main()
