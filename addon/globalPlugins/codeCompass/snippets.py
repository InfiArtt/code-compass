# -*- coding: UTF-8 -*-
# Code Compass - snippet storage and text handling.
# Pure Python (no NVDA imports) so it can be unit-tested outside NVDA.
#
# Each snippet is a plain file in one folder: the file name is the snippet
# name, the extension is the language (e.g. "fetchJson.js"). Users can add,
# edit, rename or delete snippets with Explorer and Notepad as well.

import codecs
import locale
import os
import re
import stat

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_LEADING_WS = re.compile(r"^[ \t]*")
_NEWLINES = re.compile(r"\r\n|\r|\n")
#: Names Windows reserves for devices, even with an extension ("nul.py").
_DEVICE_NAMES = (
	{"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
	| {"COM" + d for d in "123456789¹²³"}
	| {"LPT" + d for d in "123456789¹²³"}
)
#: Files in the snippets folder that are not snippets.
_NOT_SNIPPETS = {"desktop.ini", "thumbs.db"}
_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)


class Snippet(object):
	__slots__ = ("name", "ext", "path")

	def __init__(self, name, ext, path):
		self.name = name
		self.ext = ext
		self.path = path

	def read(self):
		"""The snippet's code. Files saved by Code Compass are UTF-8; Notepad
		can also save UTF-16 (with a byte order mark) or ANSI, the Windows code
		page. Raises ValueError for a file that is not text."""
		with open(self.path, "rb") as f:
			data = f.read()
		if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
			return data.decode("utf-16")
		try:
			text = data.decode("utf-8-sig")
		except UnicodeDecodeError:
			# The ANSI code page, even in Python's UTF-8 mode.
			encoding = locale.getencoding() if hasattr(locale, "getencoding") else locale.getpreferredencoding(False)
			text = data.decode(encoding, errors="replace")
		if "\x00" in text:
			raise ValueError("%s is not a text file" % self.path)
		return text

	def label(self):
		return "%s (%s)" % (self.name, self.ext) if self.ext else self.name


def safe_name(name):
	"""A file-system safe version of a snippet name, or "" if nothing is left.
	Cleaning a cleaned name changes nothing."""
	name = _INVALID.sub("", name).strip(" .")
	while name.startswith("~$"):
		# Office lock-file names are hidden from the snippet list.
		name = name[2:].strip(" .")
	if name.split(".")[0].strip().upper() in _DEVICE_NAMES:
		# "nul" would write to the NUL device and vanish.
		name = "_" + name
	return name[:100].rstrip(" .")


def snippet_path(folder, name, ext):
	filename = safe_name(name)
	if ext:
		filename += "." + ext
	if filename.lower() in _NOT_SNIPPETS:
		# "desktop.ini" would be hidden from the snippet list.
		filename = "_" + filename
	return os.path.join(folder, filename)


def list_snippets(folder, preferExt=None):
	"""Snippets in folder, those with preferExt first, then by name."""
	if not os.path.isdir(folder):
		return []
	items = []
	for fn in os.listdir(folder):
		path = os.path.join(folder, fn)
		if fn.startswith((".", "~$")) or fn.lower() in _NOT_SNIPPETS or not os.path.isfile(path):
			continue
		try:
			if getattr(os.stat(path), "st_file_attributes", 0) & _HIDDEN:
				continue
		except OSError:
			continue
		name, dot, ext = fn.rpartition(".")
		if not dot:
			name, ext = fn, ""
		items.append(Snippet(name, ext.lower(), path))
	items.sort(key=lambda s: (s.ext != preferExt, s.name.lower(), s.ext))
	return items


def save_snippet(folder, name, ext, text):
	"""Write a snippet file and return its path. Line breaks become "\\n";
	inserting converts them back to the editor's style."""
	os.makedirs(folder, exist_ok=True)
	path = snippet_path(folder, name, ext)
	with open(path, "w", encoding="utf-8", newline="\n") as f:
		f.write(_NEWLINES.sub("\n", text))
	return path


def dedent(text, firstLinePrefix=""):
	"""Remove the indentation the lines share, so a method copied from deep
	inside a class is stored starting at column 0. firstLinePrefix is the
	whitespace before the selection on its first line, which belongs to it
	for the purpose of measuring indentation."""
	lines = _NEWLINES.split(text)
	lines[0] = firstLinePrefix + lines[0]
	widths = [len(_LEADING_WS.match(l).group(0)) for l in lines if l.strip()]
	cut = min(widths) if widths else 0
	out = []
	for line in lines:
		ws = len(_LEADING_WS.match(line).group(0))
		out.append(line[min(cut, ws):])
	# Drop trailing blank lines but keep a final line break.
	while len(out) > 1 and not out[-1].strip():
		out.pop()
	return "\n".join(out) + "\n"


def prepare_insert(text, linePrefix, newline="\r\n"):
	"""Text to paste at the caret. linePrefix is what precedes the caret on
	its line. When that is only whitespace (the caret sits at the line's
	indentation), every following line gets the same indentation, so the
	snippet lines up with the code around it."""
	lines = _NEWLINES.split(text)
	while len(lines) > 1 and lines[-1] == "":
		lines.pop()
	indent = linePrefix if not linePrefix.strip() else _LEADING_WS.match(linePrefix).group(0)
	result = [lines[0]] + [(indent + l if l.strip() else l) for l in lines[1:]]
	return newline.join(result)
