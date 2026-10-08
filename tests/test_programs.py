# -*- coding: UTF-8 -*-
# Starting Python and the Command Prompt with the user's current
# environment, not the one NVDA started with.

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import programs  # noqa: E402


class FakeRegistry(object):
	"""The winreg calls programs.py makes, over a dict of keys."""

	HKEY_LOCAL_MACHINE = "HKLM"
	HKEY_CURRENT_USER = "HKCU"
	KEY_READ = 1
	KEY_WOW64_64KEY = 0
	KEY_WOW64_32KEY = 0
	REG_SZ = 1
	REG_EXPAND_SZ = 2

	def __init__(self, keys):
		#: (root, path) -> {"values": {name: (value, kind)}, "subkeys": [names]}
		self.keys = keys

	class Key(object):
		def __init__(self, root, path):
			self.root, self.path = root, path

		def __enter__(self):
			return self

		def __exit__(self, *exc):
			return False

	def OpenKey(self, root, path, reserved=0, access=0):
		if isinstance(root, FakeRegistry.Key):
			root, path = root.root, root.path + "\\" + path
		if (root, path) not in self.keys:
			raise OSError(path)
		return FakeRegistry.Key(root, path)

	def EnumValue(self, key, index):
		values = list(self.keys[(key.root, key.path)].get("values", {}).items())
		if index >= len(values):
			raise OSError()
		name, (value, kind) = values[index]
		return name, value, kind

	def EnumKey(self, key, index):
		subkeys = self.keys[(key.root, key.path)].get("subkeys", [])
		if index >= len(subkeys):
			raise OSError()
		return subkeys[index]

	def QueryValueEx(self, key, name):
		values = self.keys[(key.root, key.path)].get("values", {})
		if name not in values:
			raise OSError(name)
		return values[name]

	@staticmethod
	def ExpandEnvironmentStrings(value):
		return value.replace("%USERPROFILE%", "C:\\Users\\me")


class ProgramsTests(unittest.TestCase):
	def registry(self, pythons=()):
		keys = {
			("HKLM", programs._SYSTEM_ENVIRONMENT): {"values": {
				"Path": ("C:\\Windows\\system32;C:\\Windows", 2),
				"TEMP": ("C:\\Windows\\TEMP", 2),
				# Windows' own value for the SYSTEM account.
				"USERNAME": ("SYSTEM", 1),
			}},
			("HKCU", "Volatile Environment"): {"values": {
				"USERNAME": ("me", 1),
				"USERPROFILE": ("C:\\Users\\me", 1),
			}},
			("HKCU", "Environment"): {"values": {
				# Uses a variable set after NVDA started.
				"Path": ("%USERPROFILE%\\AppData\\Local\\Programs\\Python\\Python313\\;%TOOLS%\\bin", 2),
				"TOOLS": ("C:\\Tools", 1),
				"TEMP": ("C:\\Users\\me\\Temp", 1),
			}},
			("HKCU", programs._PYTHON_CORE): {"subkeys": [tag for tag, _exe in pythons]},
		}
		for tag, exe in pythons:
			keys[("HKCU", programs._PYTHON_CORE + "\\" + tag)] = {}
			keys[("HKCU", programs._PYTHON_CORE + "\\" + tag + "\\InstallPath")] = {"values": {"ExecutablePath": (exe, 1)}}
		return mock.patch.object(programs, "winreg", FakeRegistry(keys))

	def test_fresh_environment(self):
		with self.registry():
			env = programs.fresh_environment({"PATH": "C:\\Windows\\system32", "TEMP": "C:\\old", "NVDA": "1"})
		self.assertEqual(env["PATH"], "C:\\Windows\\system32;C:\\Windows;C:\\Users\\me\\AppData\\Local\\Programs\\Python\\Python313\\;C:\\Tools\\bin")
		self.assertEqual(env["TEMP"], "C:\\Users\\me\\Temp")
		self.assertEqual(env["USERNAME"], "me")
		self.assertEqual(env["NVDA"], "1")

	def test_newest_registered_python(self):
		exes = {"3.10": "C:\\py310\\python.exe", "3.13": "C:\\py313\\python.exe", "2.7": "C:\\py27\\python.exe"}
		with self.registry(sorted(exes.items())), mock.patch.object(programs.os.path, "isfile", return_value=True):
			self.assertEqual(programs.registered_pythons(), ["C:\\py313\\python.exe", "C:\\py310\\python.exe"])
			self.assertEqual(programs.python_command({"PATH": ""}), ["C:\\py313\\python.exe"])

	def test_launcher_and_path_fallbacks(self):
		with self.registry():
			with mock.patch.object(programs.shutil, "which", side_effect=lambda name, path=None: "C:\\x\\py.exe" if name == "py" else None):
				self.assertEqual(programs.python_command({"PATH": "C:\\x"}), ["C:\\x\\py.exe", "-3"])
			store = "C:\\Users\\me\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"
			with mock.patch.object(programs.shutil, "which", side_effect=lambda name, path=None: store if name == "python" else None):
				self.assertIsNone(programs.python_command({"PATH": ""}))


if __name__ == "__main__":
	unittest.main()
