# -*- coding: UTF-8 -*-
# Code Compass - changing text in a Win32 edit control (classic Notepad).
# Windows copies strings across processes for these system messages, so NVDA
# can edit Notepad's text directly: no clipboard, no simulated typing, and each
# change is one step that control+Z undoes. No NVDA imports.

import ctypes

EM_GETSEL = 0x00B0
EM_SETSEL = 0x00B1
EM_SCROLLCARET = 0x00B7
EM_REPLACESEL = 0x00C2
SMTO_ABORTIFHUNG = 0x0002
GWL_STYLE = -16
ES_MULTILINE = 0x0004
ES_READONLY = 0x0800
#: Give up rather than freeze NVDA on a hung editor.
TIMEOUT_MS = 2000


def is_writable_edit(windowClassName, hwnd):
	"""True for a multi-line Win32 edit control (classic Notepad's) that is
	not read-only, which is the kind this module can change. Single-line
	fields (Find, Run, passwords) are left alone."""
	if windowClassName != "Edit" or not hwnd:
		return False
	try:
		getStyle = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int)(
			("GetWindowLongW", ctypes.windll.user32))
		style = getStyle(hwnd, GWL_STYLE)
		return bool(style & ES_MULTILINE) and not (style & ES_READONLY)
	except (AttributeError, OSError):
		return False


def is_single_line(windowClassName, hwnd):
	"""True for a one-line Win32 edit or rich edit field, such as a dialog's
	file name or "Find what" box, as opposed to a document editor."""
	if not hwnd or not (windowClassName == "Edit" or windowClassName.lower().startswith("richedit")):
		return False
	try:
		getStyle = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int)(
			("GetWindowLongW", ctypes.windll.user32))
		return not getStyle(hwnd, GWL_STYLE) & ES_MULTILINE
	except (AttributeError, OSError):
		return False


EM_GETMODIFY = 0x00B8
EM_SETMODIFY = 0x00B9


GA_ROOT = 2


def top_window(hwnd):
	"""(handle, title) of the top-level window holding hwnd (Notepad's own
	window, whatever window is in front), or (None, None)."""
	try:
		user32 = ctypes.windll.user32
		user32.GetAncestor.restype = ctypes.c_void_p
		user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
		user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
		root = user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
		if not root:
			return None, None
		buf = ctypes.create_unicode_buffer(1024)
		user32.GetWindowTextW(root, buf, 1024)
		return root, buf.value
	except (AttributeError, OSError):
		return None, None


def is_modified(hwnd):
	"""The edit control's own "changed since saved" flag: True, False, or
	None when it cannot be read."""
	result = _send(hwnd, EM_GETMODIFY, 0, 0)
	return None if result is None else bool(result)
WM_COMMAND = 0x0111
EN_CHANGE = 0x0300


def mark_unmodified(hwnd):
	"""Tell the edit control, and Notepad through the change notification
	it listens to, that the text is as saved: the "*" leaves the title."""
	_send(hwnd, EM_SETMODIFY, 0, 0)
	try:
		user32 = ctypes.windll.user32
		user32.GetParent.restype = ctypes.c_void_p
		user32.GetParent.argtypes = [ctypes.c_void_p]
		user32.GetDlgCtrlID.argtypes = [ctypes.c_void_p]
		parent = user32.GetParent(hwnd)
		control = user32.GetDlgCtrlID(hwnd)
	except (AttributeError, OSError):
		return False
	if not parent:
		return False
	return _send(parent, WM_COMMAND, (EN_CHANGE << 16) | (control & 0xFFFF), hwnd) is not None


def insert(hwnd, text):
	"""Replace the selection (or insert at the caret) with text. True on
	success."""
	return _send(hwnd, EM_REPLACESEL, 1, text) is not None


def _send(hwnd, msg, wParam, lParam, timeout=None):
	"""SendMessageTimeoutW; lParam may be an int or a str. Returns the result,
	or None when the message failed or timed out (after timeout ms)."""
	text = isinstance(lParam, str)
	proto = ctypes.WINFUNCTYPE(
		ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t,
		ctypes.c_wchar_p if text else ctypes.c_ssize_t,
		ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
	)
	send = proto(("SendMessageTimeoutW", ctypes.windll.user32))
	result = ctypes.c_size_t()
	if not send(hwnd, msg, wParam, lParam, SMTO_ABORTIFHUNG, timeout or TIMEOUT_MS, ctypes.byref(result)):
		return None
	return result.value


def utf16_offset(text, offset):
	"""Python str offset -> UTF-16 code units, which edit controls count."""
	return len(text[:offset].encode("utf-16-le")) // 2


def replace(hwnd, text, start, end, newText, selStart=None, selEnd=None, timeout=None):
	"""Replace text[start:end] (Python offsets into the control's current
	text) with newText, then select selStart..selEnd (offsets into the new
	text; caret at selEnd) or leave the caret after newText. True on success.
	timeout (ms) is for the replacement itself: a whole large file with word
	wrap on takes Notepad seconds."""
	if "\x00" in newText:
		# The message carries a C string: it would end at the NUL.
		return False
	if _send(hwnd, EM_SETSEL, utf16_offset(text, start), utf16_offset(text, end)) is None:
		return False
	if _send(hwnd, EM_REPLACESEL, 1, newText, timeout) is None:
		return False
	if selStart is not None:
		newFull = text[:start] + newText + text[end:]
		if selEnd is None:
			selEnd = selStart
		_send(hwnd, EM_SETSEL, utf16_offset(newFull, selStart), utf16_offset(newFull, selEnd))
	_send(hwnd, EM_SCROLLCARET, 0, 0)
	return True
