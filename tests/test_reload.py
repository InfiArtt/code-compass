# -*- coding: UTF-8 -*-
# Reloading a file changed on disk: by command, and automatically when the
# editor comes back with no unsaved changes.

import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS

import filepath  # noqa: E402

OLD = "def a():\r\n    return 1\r\n\r\ndef b():\r\n    return 2\r\n"
NEW = "import os\n\ndef a():\n    return 10\n\ndef b():\n    return 2\n"


class ReloadTests(v040.V040Tests):
	def setUp(self):
		super(ReloadTests, self).setUp()
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.path = os.path.join(self.folder, "latihan.py")
		self.write(OLD)
		codeCompass._disk.clear()
		find = mock.patch.object(codeCompass.filepath, "find_file", return_value=self.path)
		find.start()
		self.addCleanup(find.stop)
		mark = mock.patch.object(codeCompass.edit_control, "mark_unmodified")
		self.mark = mark.start()
		self.addCleanup(mark.stop)
		MODS["api"].getFocusObject.return_value = self.ed
		self.ed.appModule = types.SimpleNamespace(appName="notepad")
		self.use(OLD, "latihan.py - Notepad")

	def write(self, text):
		with open(self.path, "w", encoding="utf-8", newline="") as f:
			f.write(text)
		# A different time stamp even on fast file systems.
		st = os.stat(self.path)
		os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

	def line(self):
		return self.ed.text.count("\n", 0, self.ed.caret)

	def test_reload_command(self):
		self.at("    return 2")
		self.write(NEW)
		self.plugin.script_reloadFile(None)
		self.assertEqual(self.ed.text, NEW.replace("\n", "\r\n"))
		self.assertEqual(self.message(), "Reloaded latihan.py: 1 line changed, 2 lines added")
		# The caret stays on its line, now two lines further down.
		self.assertEqual(self.line(), 6)
		self.mark.assert_called_once_with(7)

	def test_same_as_disk(self):
		self.plugin.script_reloadFile(None)
		self.assertEqual(self.message(), "latihan.py is the same as on disk")

	def test_unsaved_changes_ask_first(self):
		self.use(OLD + "x = 1\r\n", "*latihan.py - Notepad")
		self.write(NEW)
		seen = {}

		def run_dialog(make, onClose):
			seen["asked"] = True
			onClose(None, MODS["wx"].ID_YES)

		with mock.patch.object(codeCompass, "_run_dialog", run_dialog):
			self.plugin.script_reloadFile(None)
		self.assertTrue(seen.get("asked"))
		self.run_later()
		self.assertEqual(self.ed.text, NEW.replace("\n", "\r\n"))

	def test_notepad_plus_plus(self):
		self.ed.appModule = types.SimpleNamespace(appName="notepad++")
		self.plugin.script_reloadFile(None)
		self.assertEqual(self.message(), "Notepad++ reloads files itself: File, Reload from Disk")

	def test_automatic_reload_without_unsaved_changes(self):
		codeCompass._check_disk(self.ed)
		self.write(NEW)
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.ed.text, NEW.replace("\n", "\r\n"))
		self.assertEqual(self.message(), "latihan.py changed on disk and was reloaded: 1 line changed, 2 lines added")
		# Nothing new on disk: nothing more happens.
		MODS["ui"].message.reset_mock()
		codeCompass._check_disk(self.ed)
		MODS["ui"].message.assert_not_called()

	def test_unsaved_changes_are_never_replaced(self):
		codeCompass._check_disk(self.ed)
		self.use(OLD + "x = 1\r\n", "*latihan.py - Notepad")
		self.write(NEW)
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.ed.text, OLD + "x = 1\r\n")
		self.assertIn("you have unsaved changes", self.message())

	def test_own_save_is_not_a_change(self):
		codeCompass._check_disk(self.ed)
		self.use(OLD + "x = 1\r\n", "latihan.py - Notepad")
		self.write(OLD + "x = 1\r\n")
		MODS["ui"].message.reset_mock()
		codeCompass._check_disk(self.ed)
		MODS["ui"].message.assert_not_called()

	def test_deleted_file(self):
		codeCompass._check_disk(self.ed)
		os.remove(self.path)
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.message(), "latihan.py is no longer on disk")


	# Review round: safety and speed.

	def test_editor_not_showing_the_last_version_is_never_replaced(self):
		codeCompass._check_disk(self.ed)
		# The editor now shows something else under the same title (and
		# without "*"), and the remembered file changes.
		self.use("print('other')\r\n", "latihan.py - Notepad")
		self.write(NEW)
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.ed.text, "print('other')\r\n")
		self.assertNotIn("reloaded", self.message() if MODS["ui"].message.called else "")

	def test_lossy_ansi_save_is_our_own(self):
		codeCompass._check_disk(self.ed)
		self.use(OLD + "# harga → rupiah\r\n", "latihan.py - Notepad")
		with open(self.path, "w", encoding="cp1252", errors="replace", newline="") as f:
			f.write(OLD + "# harga → rupiah\r\n")
		st = os.stat(self.path)
		os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
		MODS["ui"].message.reset_mock()
		with mock.patch.object(filepath.locale, "getencoding", return_value="cp1252", create=True):
			codeCompass._check_disk(self.ed)
		MODS["ui"].message.assert_not_called()
		self.assertIn("→", self.ed.text)

	def test_file_changed_while_the_question_is_open(self):
		self.use(OLD + "x = 1\r\n", "*latihan.py - Notepad")
		self.write(NEW)
		newer = NEW + "\nprint('newer')\n"

		def run_dialog(make, onClose):
			self.write(newer)
			onClose(None, MODS["wx"].ID_YES)

		with mock.patch.object(codeCompass, "_run_dialog", run_dialog):
			self.plugin.script_reloadFile(None)
		self.run_later()
		self.assertEqual(self.ed.text, newer.replace("\n", "\r\n"))

	def test_failed_reload_is_reported(self):
		self.write(NEW)
		with mock.patch.object(codeCompass.edit_control, "replace", return_value=False):
			self.plugin.script_reloadFile(None)
		self.assertEqual(self.message(), "Could not reload latihan.py")

	def test_editor_that_cannot_be_changed(self):
		codeCompass._check_disk(self.ed)
		self.write(NEW)
		with mock.patch.object(codeCompass, "_writable_notepad", return_value=False):
			codeCompass._check_disk(self.ed)
		self.assertEqual(self.message(), "latihan.py changed on disk")

	def test_large_change_summary_is_quick(self):
		import time
		old = ["function f%d() {" % i if i % 3 == 0 else ("  return %d;" % i if i % 3 == 1 else "}") for i in range(5000)]
		new = ["  " + line for line in old]
		start = time.perf_counter()
		words = codeCompass._change_words(old, new)
		self.assertLess(time.perf_counter() - start, 0.5)
		self.assertEqual(words, "5000 lines changed")


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(ReloadTests):
		setattr(ReloadTests, _name, None)


class SameNameTests(v040.V040Tests):
	"""Two main.py files in different folders, one window (classic Notepad
	shows only the name)."""

	def setUp(self):
		super(SameNameTests, self).setUp()
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.a = self.write("a", "print('A')\r\n")
		self.b = self.write("b", "print('B')\r\n")
		codeCompass._disk.clear()

		def find(title, pid=None, remembered=None, text=None):
			for path in (self.a, self.b):
				if text is not None and filepath.file_holds(path, text):
					return path
			return self.a if text is None else None

		patcher = mock.patch.object(codeCompass.filepath, "find_file", side_effect=find)
		self.find = patcher.start()
		self.addCleanup(patcher.stop)
		mark = mock.patch.object(codeCompass.edit_control, "mark_unmodified")
		mark.start()
		self.addCleanup(mark.stop)
		MODS["api"].getFocusObject.return_value = self.ed
		self.ed.appModule = types.SimpleNamespace(appName="notepad")

	def write(self, folder, text):
		os.makedirs(os.path.join(self.folder, folder), exist_ok=True)
		path = os.path.join(self.folder, folder, "main.py")
		with open(path, "w", encoding="utf-8", newline="") as f:
			f.write(text)
		st = os.stat(path)
		os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
		return path

	def test_file_open_of_a_same_named_file(self):
		self.use("print('A')\r\n", "main.py - Notepad")
		codeCompass._check_disk(self.ed)
		# File > Open b\main.py in the same window.
		self.use("print('B')\r\n", "main.py - Notepad")
		codeCompass._check_disk(self.ed)
		self.write("a", "print('A, edited elsewhere')\r\n")
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.ed.text, "print('B')\r\n")
		# A change to the file actually shown is reloaded.
		self.write("b", "print('B, edited elsewhere')\r\n")
		codeCompass._check_disk(self.ed)
		self.assertEqual(self.ed.text, "print('B, edited elsewhere')\r\n")

	def test_no_guess_for_a_clean_document(self):
		# The editor holds text no candidate has, and no "*": no file is
		# guessed, so nothing can be reloaded into it.
		self.use("print('C')\r\n", "main.py - Notepad")
		codeCompass._check_disk(self.ed)
		self.assertNotIn(7, codeCompass._disk)


for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(SameNameTests):
		setattr(SameNameTests, _name, None)


class ReadTextTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)

	def file(self, data):
		path = os.path.join(self.folder, "f.txt")
		with open(path, "wb") as f:
			f.write(data)
		return path

	def test_encodings(self):
		self.assertEqual(filepath.read_text(self.file("café\r\n".encode("utf-8-sig"))), "café\r\n")
		self.assertEqual(filepath.read_text(self.file("xé".encode("utf-16"))), "xé")
		self.assertEqual(filepath.read_text(self.file("print(1)\r\n".encode("utf-16-le"))), "print(1)\r\n")
		self.assertIsNone(filepath.read_text(os.path.join(self.folder, "missing.txt")))
		# Notepad shows a NUL as a space.
		self.assertEqual(filepath.read_text(self.file(b"a = 1\x00b = 2\r\n")), "a = 1 b = 2\r\n")
		self.assertFalse(codeCompass_edit_control().replace(0, "", 0, 0, "a\x00b"))
		self.assertTrue(filepath.same_text("a\nb\n", "a\r\nb"))


if __name__ == "__main__":
	unittest.main()


def codeCompass_edit_control():
	return codeCompass.edit_control
