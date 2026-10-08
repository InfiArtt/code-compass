# -*- coding: UTF-8 -*-
# Code Compass - starting other programs (Python, Command Prompt) with the
# user's current environment. NVDA keeps the environment it started with:
# started from the sign-in screen, or before Python was installed, its PATH
# lacks the user's own entries, so Python would not be found and a Command
# Prompt opened from NVDA could not run it either. No NVDA imports.

import os
import re
import shutil

try:
	import winreg
except ImportError:  # Not Windows (tests elsewhere).
	winreg = None

_SYSTEM_ENVIRONMENT = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
_PYTHON_CORE = r"Software\Python\PythonCore"


def _registry_values(root, subkey):
	"""Name -> (string value, expand) of a registry key's values; expand is
	True for REG_EXPAND_SZ values (with %NAME% references left in)."""
	values = {}
	if winreg is None:
		return values
	try:
		key = winreg.OpenKey(root, subkey)
	except OSError:
		return values
	with key:
		index = 0
		while True:
			try:
				name, value, kind = winreg.EnumValue(key, index)
			except OSError:
				break
			index += 1
			if isinstance(value, str):
				values[name] = (value, kind == winreg.REG_EXPAND_SZ)
	return values


def _subkeys(root, subkey):
	names = []
	if winreg is None:
		return names
	try:
		key = winreg.OpenKey(root, subkey)
	except OSError:
		return names
	with key:
		index = 0
		while True:
			try:
				names.append(winreg.EnumKey(key, index))
			except OSError:
				break
			index += 1
	return names


def _expand(value, env):
	"""Replace %NAME% with NAME's value in env (any case), as Windows does
	when it builds a new process's environment; unknown names stay."""
	upper = {k.upper(): v for k, v in env.items()}

	def one(m):
		found = upper.get(m.group(1).upper())
		return found if found is not None else m.group(0)
	return re.sub(r"%([^%\r\n]+)%", one, value)


#: Variables the system key holds for the SYSTEM account, never the user's.
_NOT_FROM_SYSTEM = frozenset(("USERNAME",))


def fresh_environment(base=None):
	"""The environment a Command Prompt started now from Explorer would get:
	base (NVDA's own, by default) with the system's, the user's and the
	session's variables as Windows has them now (%NAME% references expanded
	against the new values), and PATH made of the system's PATH followed by
	the user's."""
	env = dict(os.environ if base is None else base)
	if winreg is None:
		return env
	system = _registry_values(winreg.HKEY_LOCAL_MACHINE, _SYSTEM_ENVIRONMENT)
	user = _registry_values(winreg.HKEY_CURRENT_USER, "Environment")
	if not system and not user:
		return env
	# The logged-on user's own USERNAME, USERPROFILE, APPDATA...; numbered
	# subkeys hold per-session ones such as SESSIONNAME.
	volatile = _registry_values(winreg.HKEY_CURRENT_USER, "Volatile Environment")
	for sub in _subkeys(winreg.HKEY_CURRENT_USER, "Volatile Environment"):
		volatile.update(_registry_values(winreg.HKEY_CURRENT_USER, "Volatile Environment\\" + sub))
	byUpper = {k.upper(): k for k in env}

	def setVar(name, value):
		key = byUpper.setdefault(name.upper(), name)
		env[key] = value

	paths = []
	for values, skip in ((system, _NOT_FROM_SYSTEM), (volatile, ()), (user, ())):
		# Plain values first, then the ones that refer to others.
		for expand in (False, True):
			for name, (value, isExpand) in values.items():
				if isExpand != expand or name.upper() in skip:
					continue
				if expand:
					value = _expand(value, env)
				if name.upper() == "PATH":
					paths.append(value)
				else:
					setVar(name, value)
	if paths:
		setVar("PATH", ";".join(p.strip(";") for p in paths if p))
	return env


def _version_key(name):
	"""(3, 13) for "3.13" or "3.13-64"; None for anything else."""
	m = re.match(r"(\d+)\.(\d+)", name)
	return (int(m.group(1)), int(m.group(2))) if m else None


def registered_pythons():
	"""Python installations registered with Windows (python.org installers,
	the Python install manager), newest first, as executable paths."""
	found = []
	if winreg is None:
		return found
	views = [
		(winreg.HKEY_CURRENT_USER, 0),
		(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
		(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
	]
	for root, view in views:
		try:
			core = winreg.OpenKey(root, _PYTHON_CORE, 0, winreg.KEY_READ | view)
		except OSError:
			continue
		with core:
			index = 0
			while True:
				try:
					tag = winreg.EnumKey(core, index)
				except OSError:
					break
				index += 1
				version = _version_key(tag)
				if version is None or version[0] < 3:
					continue
				exe = None
				try:
					with winreg.OpenKey(core, tag + r"\InstallPath") as installKey:
						try:
							exe = winreg.QueryValueEx(installKey, "ExecutablePath")[0]
						except OSError:
							folder = winreg.QueryValueEx(installKey, "")[0]
							exe = os.path.join(folder, "python.exe")
				except OSError:
					continue
				if exe and os.path.isfile(exe):
					found.append((version, exe))
	found.sort(key=lambda item: item[0], reverse=True)
	seen = set()
	result = []
	for _version, exe in found:
		key = os.path.normcase(exe)
		if key not in seen:
			seen.add(key)
			result.append(exe)
	return result


def python_command(env=None):
	"""How to start Python 3, as a command list, or None: the newest
	registered Python, else the py launcher, else python on the PATH (not
	the Microsoft Store stub in WindowsApps, which only opens the Store)."""
	pythons = registered_pythons()
	if pythons:
		return [pythons[0]]
	path = (env or os.environ).get("PATH")
	launcher = shutil.which("py", path=path)
	if launcher:
		return [launcher, "-3"]
	python = shutil.which("python", path=path)
	if python and "WindowsApps" not in python:
		return [python]
	return None
