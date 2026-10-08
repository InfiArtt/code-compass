# -*- coding: UTF-8 -*-
# Code Compass - finding the file an editor window has open.
# Notepad's title only names the file ("main.py - Notepad"), so the full path
# is looked for in the title (Notepad++ shows it), in the editor's command
# line (a file opened from Explorer), and in Windows' Recent items (a file
# opened through the Open dialog). No NVDA imports: the Windows calls are made
# with ctypes, and only when asked.

import codecs
import ctypes
import locale
import os
import re

#: "name - Application": the application's name follows the last spaced
#: separator and may contain hyphens itself ("main.py - Bloc-notes").
_TITLE_TAIL = re.compile(r"\s+[-\u2013\u2014]\s+(?:(?!\s[-\u2013\u2014]\s).)*$")
#: Names editors give documents that were never saved.
_UNTITLED = re.compile(r"^(untitled|new \d+)$", re.IGNORECASE)


def title_file(title):
	"""The file part of an editor title: "*C:\\x\\main.py - Notepad++" gives
	"C:\\x\\main.py", "main - Copy.py - Notepad" gives "main - Copy.py".
	None for a document that was never saved ("Untitled", Notepad++'s "new 1")."""
	if not title:
		return None
	head = _TITLE_TAIL.sub("", title.strip()).strip().lstrip("*").strip()
	if not head or _UNTITLED.match(head):
		return None
	return head

def is_unsaved(title):
	"""Notepad and Notepad++ start the title with "*" when there are unsaved
	changes."""
	return bool(title) and title.lstrip().startswith("*")


def process_command_line(pid):
	"""The command line of another process (Windows 8.1 and later), or None."""
	try:
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		ntdll = ctypes.WinDLL("ntdll")
	except (AttributeError, OSError):
		return None
	PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
	ProcessCommandLineInformation = 60
	kernel32.OpenProcess.restype = ctypes.c_void_p
	kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
	kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
	ntdll.NtQueryInformationProcess.restype = ctypes.c_long
	ntdll.NtQueryInformationProcess.argtypes = [
		ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
	handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
	if not handle:
		return None
	try:
		size = ctypes.c_ulong(0)
		ntdll.NtQueryInformationProcess(handle, ProcessCommandLineInformation, None, 0, ctypes.byref(size))
		if not size.value:
			return None
		buf = ctypes.create_string_buffer(size.value)
		if ntdll.NtQueryInformationProcess(handle, ProcessCommandLineInformation, buf, size, ctypes.byref(size)) != 0:
			return None

		class UNICODE_STRING(ctypes.Structure):
			_fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]

		us = UNICODE_STRING.from_buffer(buf)
		if not us.Buffer:
			return None
		return ctypes.wstring_at(us.Buffer, us.Length // 2)
	finally:
		kernel32.CloseHandle(handle)


def split_command_line(cmdline):
	"""Arguments of a Windows command line, as CommandLineToArgvW splits them,
	followed by everything after the program name as one path: Explorer
	starts Notepad with an unquoted path that may contain spaces."""
	args = _argv(cmdline)
	if args:
		rest = cmdline.strip()
		if rest.startswith('"'):
			rest = rest[rest.find('"', 1) + 1:]
		else:
			rest = rest[len(rest.split(None, 1)[0]):]
		rest = rest.strip().strip('"')
		if rest and rest not in args:
			args.append(rest)
	return args


def _argv(cmdline):
	try:
		shell32 = ctypes.WinDLL("shell32")
		kernel32 = ctypes.WinDLL("kernel32")
	except (AttributeError, OSError):
		return [a or b for a, b in re.findall(r'"([^"]*)"|(\S+)', cmdline)]
	shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
	shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
	kernel32.LocalFree.argtypes = [ctypes.c_void_p]
	count = ctypes.c_int(0)
	argv = shell32.CommandLineToArgvW(cmdline, ctypes.byref(count))
	if not argv:
		return []
	try:
		return [argv[i] for i in range(count.value)]
	finally:
		kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))

def recent_item_target(filename):
	"""Where the Recent items shortcut for filename points, or None.
	Windows adds one when a file is opened from Explorer or an Open dialog."""
	appdata = os.environ.get("APPDATA")
	if not appdata:
		return None
	link = os.path.join(appdata, "Microsoft", "Windows", "Recent", filename + ".lnk")
	if not os.path.isfile(link):
		return None
	try:
		import comtypes.client
		shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
		return shell.CreateShortcut(link).TargetPath or None
	except Exception:
		return None


def find_file(title, pid=None, remembered=None, text=None):
	"""Full path of the file named in an editor title, or None.

	Candidates: the title itself (Notepad++ shows the path), a path the user
	pointed out for this window, the editor's command line and Recent items.
	A candidate must exist and have the title's file name. Notepad's title
	only has the name, so when several candidates exist, or when text (the
	editor's contents) is given, a candidate is only trusted if the file holds
	that text; another project's file with the same name is not picked.
	With unsaved changes (text given but no file matches) a single candidate
	is still accepted. A remembered path (the user's own choice) wins unless
	the saved text plainly belongs to another candidate."""
	name = title_file(title)
	if not name:
		return None
	if os.path.isabs(name) and os.path.isfile(name):
		return name
	base = os.path.basename(name).lower()
	candidates = []
	if remembered:
		candidates.append(remembered)
	if pid:
		cmdline = process_command_line(pid)
		if cmdline:
			candidates.extend(split_command_line(cmdline)[1:])
	candidates.append(recent_item_target(os.path.basename(name)))
	found = []
	keys = set()
	for path in candidates:
		if path and os.path.basename(path).lower() == base and os.path.isabs(path) and os.path.isfile(path):
			# realpath expands 8.3 short names and "..", so one file is one.
			key = os.path.normcase(os.path.realpath(path))
			if key not in keys:
				keys.add(key)
				found.append(path)
	if not found:
		return None
	if remembered and os.path.normcase(os.path.realpath(remembered)) in keys:
		# The remembered path came first, so it is found[0].
		chosen = found[0]
		# The user pointed this file out: keep it, unless the saved document
		# clearly is another candidate.
		if text is None or is_unsaved(title) or file_holds(chosen, text):
			return chosen
		others = [f for f in found if f is not chosen and file_holds(f, text)]
		return others[0] if len(others) == 1 else chosen
	if text is not None:
		matching = [f for f in found if file_holds(f, text)]
		if len(matching) == 1:
			return matching[0]
		if matching:
			return None
		if is_unsaved(title) and len(found) == 1:
			return found[0]
		return None
	return found[0] if len(found) == 1 else None


#: Files larger than this are not read to compare or reload them.
MAX_READ = 20 * 1024 * 1024


def read_text(path):
	"""The file's text decoded the way Notepad opens it (UTF-16 with a byte
	order mark, UTF-16 without one, UTF-8, else the ANSI code page), or None
	when it cannot be read."""
	data = _read_bytes(path)
	if data is None:
		return None
	for encoding, errors in _encodings(data):
		try:
			return data.decode(encoding, errors).replace("\x00", " ")
		except (UnicodeDecodeError, LookupError):
			continue
	return None


def same_text(a, b):
	"""True when two texts differ at most in their line breaks."""
	return _normalize(a) == _normalize(b)


def ansi_round_trip(text):
	"""text as Notepad writes it in the ANSI code page: characters the page
	lacks become "?"."""
	ansi = locale.getencoding() if hasattr(locale, "getencoding") else locale.getpreferredencoding(False)
	try:
		return text.encode(ansi, "replace").decode(ansi, _ANSI_ERRORS)
	except (LookupError, UnicodeError):
		return text


def _read_bytes(path):
	try:
		if os.path.getsize(path) > MAX_READ:
			return None
		with open(path, "rb") as f:
			return f.read()
	except OSError:
		return None


def file_holds(path, text):
	"""True when the file's contents are text (line breaks aside), read as
	UTF-8, UTF-16 or the ANSI code page like Notepad saves them."""
	data = _read_bytes(path)
	if data is None:
		return False
	want = _normalize(text.replace("\x00", " "))
	for encoding, errors in _encodings(data):
		try:
			if _normalize(data.decode(encoding, errors).replace("\x00", " ")) == want:
				return True
		except (UnicodeDecodeError, LookupError):
			continue
	return False


def _encodings(data):
	"""(encoding, errors) to try for a file's bytes, most likely first."""
	if data.startswith((b"\xff\xfe", b"\xfe\xff")):
		encodings = (("utf-16", "strict"),)
	else:
		ansi = locale.getencoding() if hasattr(locale, "getencoding") else locale.getpreferredencoding(False)
		encodings = [("utf-8-sig", "strict"), (ansi, _ANSI_ERRORS)]
		if data[1::2].count(0) > len(data) // 4:
			# Many NUL bytes: UTF-16 without a byte order mark.
			encodings.insert(0, ("utf-16-le", "strict"))
	return encodings


def _ansi_errors(exc):
	"""Map bytes the code page leaves undefined to the same code point, as
	Windows (and so Notepad) does: 0x81 becomes U+0081."""
	bad = exc.object[exc.start:exc.end]
	return "".join(chr(b) for b in bad), exc.end


_ANSI_ERRORS = "codeCompassAnsi"
codecs.register_error(_ANSI_ERRORS, _ansi_errors)


def _normalize(text):
	return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")

#: Files or folders that mark the top of a project.
PROJECT_MARKERS = (".git", ".hg", ".svn", ".vscode", "pyproject.toml", "setup.py", "package.json", "go.mod", "Cargo.toml", "Package.swift")


def project_root(path, levels=6):
	"""The project folder of a file: the nearest folder above it (up to
	levels up) holding a marker such as .git or package.json, else the
	file's own folder. The user's home folder and drive roots are never a
	project (VS Code keeps a .vscode folder in the home folder)."""
	folder = path if os.path.isdir(path) else os.path.dirname(path)
	home = os.path.normcase(os.path.expanduser("~"))
	current = folder
	for _i in range(levels):
		if os.path.normcase(current) == home or is_drive_root(current):
			break
		if any(os.path.exists(os.path.join(current, m)) for m in PROJECT_MARKERS):
			return current
		parent = os.path.dirname(current)
		if not parent or parent == current:
			break
		current = parent
	return folder


def is_drive_root(path):
	"""True for "C:\\", a UNC share root "\\\\server\\share\\", or "/"."""
	drive, rest = os.path.splitdrive(os.path.normpath(path))
	return rest in ("\\", "/", "")


def parent_folder(path):
	"""The folder above path, or None at a drive or share root."""
	if is_drive_root(path):
		return None
	parent = os.path.dirname(os.path.normpath(path))
	if not parent or os.path.normcase(parent) == os.path.normcase(os.path.normpath(path)):
		return None
	drive, rest = os.path.splitdrive(parent)
	if rest == "":
		# "C:" alone means the current folder on drive C; use its root.
		parent = drive + os.sep
	return parent

def process_image_path(pid):
	"""Full path of a process's program file, or None."""
	try:
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	except (AttributeError, OSError):
		return None
	kernel32.OpenProcess.restype = ctypes.c_void_p
	kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
	kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
	kernel32.QueryFullProcessImageNameW.argtypes = [
		ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
	handle = kernel32.OpenProcess(0x1000, 0, pid)
	if not handle:
		return None
	try:
		size = ctypes.c_uint32(1024)
		buf = ctypes.create_unicode_buffer(size.value)
		if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
			return None
		return buf.value
	finally:
		kernel32.CloseHandle(handle)


def can_recycle(path):
	"""True when path is on a local fixed drive, which has a Recycle Bin.
	Network shares, USB drives and other removable media do not."""
	drive = os.path.splitdrive(os.path.abspath(path))[0]
	if not drive or drive.startswith(("\\\\", "//")):
		return False
	try:
		kernel32 = ctypes.WinDLL("kernel32")
	except (AttributeError, OSError):
		return False
	kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
	DRIVE_FIXED = 3
	return kernel32.GetDriveTypeW(drive + "\\") == DRIVE_FIXED


def remove(path, permanently=False):
	"""Move a file or folder to the Recycle Bin, or delete it permanently
	when permanently is True (the caller asked the user about that first).
	Windows' own confirmation is turned off, except its warning when an item
	that was meant for the Recycle Bin would be destroyed instead (too big
	for the bin, for example). True when the item is gone."""
	try:
		shell32 = ctypes.WinDLL("shell32")
	except (AttributeError, OSError):
		return False

	class SHFILEOPSTRUCTW(ctypes.Structure):
		_fields_ = [
			("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
			("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
			("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
		]

	FO_DELETE = 3
	FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
	FOF_WANTNUKEWARNING = 0x4000
	flags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI
	if not permanently:
		flags |= FOF_ALLOWUNDO | FOF_WANTNUKEWARNING
	# pFrom is a list ending with an empty string: two NULs at the end.
	op = SHFILEOPSTRUCTW(None, FO_DELETE, os.path.abspath(path) + "\0", None, flags, 0, None, None)
	shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
	result = shell32.SHFileOperationW(ctypes.byref(op))
	return result == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)
