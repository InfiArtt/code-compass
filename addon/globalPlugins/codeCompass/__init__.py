# -*- coding: UTF-8 -*-
# Code Compass - NVDA global plugin.
# Helps navigate source code structure: a tone (or spoken level) for bracket
# depth when moving by line, what closing brackets close, "where am I" for the
# enclosing scopes, quick moves by level, block and declaration, block
# selection, bracket checks (also on save) and an outline of declarations.

import ctypes
import gettext
import json
import os
import re
import subprocess
import tempfile
import threading

import addonHandler
import api
import braille
import config
import controlTypes
import core
import globalPluginHandler
import globalVars
import gui
import keyboardHandler
import queueHandler
import speech
import textInfos
import textUtils
import nvwave
import tones
import ui
import wx
from editableText import EditableText
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import SettingsPanel
from logHandler import log
from NVDAObjects import NVDAObject
from scriptHandler import isScriptWaiting, script
from textInfos.offsets import Offsets, OffsetsTextInfo

from . import analyzer, bookmarks, edit_control, editing, filepath, problems, programs, snippets

addonHandler.initTranslation()
#: Translator for NVDA's language, installed by initTranslation.
_nvdaTranslate = _

#: Configuration section name in config.conf.
CONFIG_SECTION = "codeCompass"

confspec = {
	"levelReport": "option('off', 'tone', 'speech', 'both', default='tone')",
	"onlyOnChange": "boolean(default=False)",
	"shortParenTone": "boolean(default=True)",
	"announceClosers": "boolean(default=True)",
	"checkOnSave": "boolean(default=True)",
	"autoIndent": "boolean(default=True)",
	"errorSound": "boolean(default=True)",
	"bookmarkSound": "boolean(default=True)",
	"soundStyle": "option('vscode', 'beeps', default='vscode')",
	"liveCheck": "option('off', 'sound', 'speech', default='sound')",
	"announceDeclarations": "boolean(default=True)",
	"autoClose": "boolean(default=False)",
	"basePitch": "integer(default=330, min=100, max=2000)",
	"semitonesPerLevel": "integer(default=3, min=1, max=12)",
	"toneLength": "integer(default=40, min=10, max=200)",
	"apps": "string(default='notepad, notepad++')",
	"language": "option('auto', 'id', 'en', default='auto')",
}
config.conf.spec[CONFIG_SECTION] = confspec


def _conf():
	return config.conf[CONFIG_SECTION]


# --- Translation ----------------------------------------------------------------

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locale")
_catalogs = {}


def _(text):
	"""Translate into the language chosen in Code Compass settings, so the
	add-on can speak Indonesian while NVDA itself stays in English."""
	try:
		lang = config.conf[CONFIG_SECTION]["language"]
	except Exception:
		lang = "auto"
	if lang == "auto":
		return _nvdaTranslate(text)
	if lang == "en":
		return text
	catalog = _catalogs.get(lang)
	if catalog is None:
		try:
			catalog = gettext.translation("nvda", localedir=_LOCALE_DIR, languages=[lang])
		except Exception:
			catalog = gettext.NullTranslations()
		_catalogs[lang] = catalog
	return catalog.gettext(text)


analyzer._ = _
problems._ = _


def _level_modes():
	return [
		# Translators: a level report mode.
		("off", _("Off")),
		# Translators: a level report mode.
		("tone", _("Tone")),
		# Translators: a level report mode.
		("speech", _("Speech")),
		# Translators: a level report mode.
		("both", _("Tone and speech")),
	]


def _sound_styles():
	return [
		# Translators: a sound style: the sounds of Visual Studio Code.
		("vscode", _("VS Code sounds")),
		# Translators: a sound style: simple tones.
		("beeps", _("Beeps")),
	]


def _live_modes():
	return [
		# Translators: do not check for problems while typing.
		("off", _("Off")),
		# Translators: play a sound when typing makes a new problem.
		("sound", _("Play a sound for new problems")),
		# Translators: play a sound and say the problem when typing makes a new one.
		("speech", _("Play a sound and say new problems")),
	]


def _languages():
	return [
		# Translators: follow NVDA's language for Code Compass messages.
		("auto", _("Same as NVDA")),
		("id", "Bahasa Indonesia"),
		("en", "English"),
	]


def _enabled_apps():
	return {a for a in re.split(r"[\s,;]+", _conf()["apps"].lower()) if a}


# --- Document access --------------------------------------------------------


def _window_title(obj):
	fg = api.getForegroundObject()
	return (fg.name if fg else None) or ""


def _converter(info, text):
	"""Offset converter between Python str offsets and the TextInfo's native
	offsets (UTF-16 for Win32 edit controls, bytes for Scintilla)."""
	encoding = getattr(info, "encoding", None)
	if not encoding:
		return None
	try:
		return textUtils.getOffsetConverter(encoding)(text)
	except Exception:
		return None


def _pair(result):
	return result if isinstance(result, tuple) else (result, result)


class _DocCache(object):
	"""Keeps the last analysis so moving by line does not re-parse the file
	unless its text changed."""

	def __init__(self):
		self.key = None
		self.analysis = None

	def get(self, obj):
		text = obj.makeTextInfo(textInfos.POSITION_ALL).text
		lang = analyzer.language_from_title(_window_title(obj))
		key = (getattr(obj, "windowHandle", None), lang)
		a = self.analysis
		if a is None or self.key != key or a.text != text:
			a = self.analysis = analyzer.Analysis(text, lang)
			self.key = key
		return a


_cache = _DocCache()


def _native_to_py(info, text, start, end):
	conv = _converter(info, text)
	if conv is not None:
		try:
			return _pair(conv.encodedToStrOffsets(start, end))
		except Exception:
			pass
	return start, end


def _caret_offset(obj, text, caret=None):
	"""Caret position as an offset into text."""
	if caret is None:
		caret = obj.makeTextInfo(textInfos.POSITION_CARET)
	if isinstance(caret, OffsetsTextInfo):
		return _native_to_py(caret, text, caret._startOffset, caret._startOffset)[0]
	before = obj.makeTextInfo(textInfos.POSITION_ALL)
	before.setEndPoint(caret, "endToStart")
	return len(before.text)


def _selection_offsets(obj, text):
	"""Selection as (start, end) offsets into text."""
	sel = obj.makeTextInfo(textInfos.POSITION_SELECTION)
	if isinstance(sel, OffsetsTextInfo):
		return _native_to_py(sel, text, sel._startOffset, sel._endOffset)
	before = obj.makeTextInfo(textInfos.POSITION_ALL)
	before.setEndPoint(sel, "endToStart")
	start = len(before.text)
	return start, start + len(sel.text)


def _range_info(obj, a, start, end):
	"""A TextInfo covering [start, end) of the analysed text."""
	probe = obj.makeTextInfo(textInfos.POSITION_FIRST)
	if isinstance(probe, OffsetsTextInfo):
		conv = _converter(probe, a.text)
		if conv is not None:
			try:
				start, end = _pair(conv.strToEncodedOffsets(start, end))
			except Exception:
				pass
		return obj.makeTextInfo(Offsets(start, end))
	# Generic fallback: walk by paragraph (logical line), then by character.
	info = probe
	li = a.line_index(start)
	info.move(textInfos.UNIT_PARAGRAPH, li)
	info.move(textInfos.UNIT_CHARACTER, start - a.lineStarts[li])
	if end != start:
		info.move(textInfos.UNIT_CHARACTER, end - start, endPoint="end")
	return info


def _writable_notepad(obj):
	"""True when obj is classic Notepad's edit control (or another Win32 edit
	control) that is not read-only: the editors Code Compass changes text in."""
	return edit_control.is_writable_edit(getattr(obj, "windowClassName", None), getattr(obj, "windowHandle", None))


def _replace_selection_directly(obj, text):
	"""Insert text at the caret of a writable Win32 edit control (classic
	Notepad) without the clipboard, as one step the user can undo. Returns
	False when obj is not such a control or the message failed, so callers
	can fall back."""
	if not _writable_notepad(obj):
		return False
	try:
		return edit_control.insert(obj.windowHandle, text)
	except Exception:
		log.debugWarning("Code Compass: EM_REPLACESEL failed", exc_info=True)
		return False


def _forget_selection_change(obj):
	"""After moving the caret or selection ourselves, stop NVDA from reading
	the change again when the control's caret event arrives."""
	try:
		obj._lastSelectionPos = obj.makeTextInfo(textInfos.POSITION_SELECTION)
	except Exception:
		pass


# --- Level and closer announcements ---------------------------------------------


def _level_pitch(level):
	c = _conf()
	hz = c["basePitch"] * 2 ** ((level - 1) * c["semitonesPerLevel"] / 12.0)
	return int(max(50, min(hz, 4000)))


def _report_level(level, inner=None, includeTop=False):
	"""Announce a bracket level with the configured mode. Level 0 is silent
	unless includeTop is set, so plain text stays quiet. Lines inside
	parentheses or square brackets get a shorter tone."""
	c = _conf()
	mode = c["levelReport"]
	if level == 0 and not includeTop:
		return
	if mode in ("tone", "both"):
		length = c["toneLength"]
		if c["shortParenTone"] and inner in ("(", "["):
			length = max(10, length // 2)
		tones.beep(_level_pitch(level), length)
	if mode in ("speech", "both"):
		# Translators: spoken bracket level of a line, e.g. "level 2".
		speech.speak([_("level {level}").format(level=level)])


def _announce_line_level(obj, a, li):
	c = _conf()
	if c["levelReport"] == "off":
		return
	level = a.line_depth(li)
	last = getattr(obj, "_codeCompassLastLevel", None)
	try:
		obj._codeCompassLastLevel = level
	except Exception:
		pass
	if c["onlyOnChange"]:
		# Leaving all brackets is news too, so level 0 is reported here.
		if level != last:
			_report_level(level, a.line_inner_bracket(li), includeTop=True)
		return
	_report_level(level, a.line_inner_bracket(li))


#: Error sound (beeps style): a low buzz after the level tone on a line
#: with a problem.
ERROR_TONE = (160, 90)
#: Warning sound (beeps style): a softer buzz.
WARNING_TONE = (300, 60)

#: VS Code's accessibility signal sounds (MIT, see sounds/LICENSE-vscode.txt).
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sounds")
_soundLengths = {}


def _sound_file(name):
	"""Path of a VS Code sound when that style is chosen, else None."""
	if _conf()["soundStyle"] != "vscode":
		return None
	path = os.path.join(SOUNDS_DIR, name + ".wav")
	return path if os.path.isfile(path) else None


def _sound_length(name, beep=None):
	"""How long a sound plays, in milliseconds."""
	path = _sound_file(name)
	if path is None:
		return beep[1] if beep else 0
	if path not in _soundLengths:
		try:
			import wave
			with wave.open(path, "rb") as w:
				_soundLengths[path] = int(w.getnframes() * 1000 / w.getframerate())
		except Exception:
			_soundLengths[path] = 300
	return _soundLengths[path]


def _play(name, beep=None, delay=0):
	"""Play VS Code's sound name, or with the beeps style (or when the file
	is missing) the beep (pitch, length), if any, after delay ms."""
	path = _sound_file(name)
	if path is not None:
		func, args = nvwave.playWaveFile, (path, True)
	elif beep is not None:
		func, args = tones.beep, tuple(beep)
	else:
		return
	if delay:
		return core.callLater(delay, func, *args)
	func(*args)
	return None


def _problem_sound(found):
	"""("error" or "warning", beep) for a set of problems."""
	if all(p.kind == "warning" for p in found):
		return "warning", WARNING_TONE
	return "error", ERROR_TONE


def _announce_line_problem(obj, a, li):
	"""Play the error (or warning) sound on a line with a problem. Returns
	how long it plays (ms), 0 when nothing played."""
	if not _conf()["errorSound"]:
		return 0
	here = [p for p in _problems(obj, a) if p.line == li]
	if not here:
		return 0
	name, beep = _problem_sound(here)
	_keep_line_sound(obj, _play(name, beep, _tone_delay()))
	return _sound_length(name, beep)


#: Window handle -> sounds waiting to play for the caret's line.
_lineSounds = {}


def _keep_line_sound(obj, timer):
	if timer is not None:
		_lineSounds.setdefault(getattr(obj, "windowHandle", None), []).append(timer)


def _stop_line_sounds(obj):
	"""The caret moved on: the last line's sounds still waiting do not play."""
	for timer in _lineSounds.pop(getattr(obj, "windowHandle", None), ()):
		try:
			timer.Stop()
		except Exception:
			pass


def _tone_delay():
	"""Milliseconds until the level tone has played (0 without one)."""
	return _conf()["toneLength"] + 20 if _conf()["levelReport"] in ("tone", "both") else 0


#: Bookmark sound (beeps style): a short high note after the level tone
#: (and error sound). VS Code style: its breakpoint sound.
BOOKMARK_TONE = (1760, 25)


def _announce_line_bookmark(obj, a, li, errorLength=0):
	if not _conf()["bookmarkSound"]:
		return
	marks = _bookmarks_for(obj, a)[1]
	if marks and any(m.line == li and not m.detached for m in marks):
		delay = _tone_delay() + (errorLength + 20 if errorLength else 0)
		_keep_line_sound(obj, _play("break", BOOKMARK_TONE, delay))


# --- Bookmarks ----------------------------------------------------------------------

_bookmarkStore = None
#: Window handle -> (title, key): where the shown document's bookmarks are
#: kept. The title is the one without "*" when the file was found, and as
#: shown when it was not, so saving the document looks again.
_bookmarkKeys = {}
#: Bookmark key -> (Analysis, lines) its bookmarks were last matched against.
_bookmarkSeen = {}


def _bookmark_store():
	global _bookmarkStore
	if _bookmarkStore is None:
		_bookmarkStore = bookmarks.Store(os.path.join(globalVars.appArgs.configPath, "codeCompass", "bookmarks.json"))
	return _bookmarkStore


def _save_bookmarks():
	if _bookmarkStore is not None and not _bookmarkStore.save():
		log.warning("Code Compass: could not save bookmarks to %s" % _bookmarkStore.path)


def _bookmark_key(obj, create=False):
	"""The key the document's bookmarks are kept under: its file's path, or
	its window and title for a document without a known file (kept in
	memory only). Without create, None when no bookmark can belong to the
	document, so moving the caret never goes looking for the file."""
	store = _bookmark_store()
	hwnd = getattr(obj, "windowHandle", None)
	shown = _window_title(obj)
	# "*" comes and goes with unsaved changes; the document stays the same.
	title = shown.lstrip("*")
	cached = _bookmarkKeys.get(hwnd)
	if cached and cached[0] in (title, shown):
		return cached[1]
	name = filepath.title_file(title)
	windowKey = ("window", hwnd, title)
	previous = cached[1] if cached else None
	unsaved = isinstance(previous, tuple) and store.has(previous)
	if not create and not unsaved and not store.has(windowKey):
		base = os.path.normcase(os.path.basename(name)) if name else None
		if not base or not any(isinstance(k, str) and os.path.basename(k) == base for k in store.files):
			return None
	key = windowKey
	text = None
	if name:
		remembered = _rememberedPaths.get(hwnd)
		try:
			text = _cache.get(obj).text
		except Exception:
			text = None
		try:
			path = filepath.find_file(shown, getattr(obj, "processID", None), remembered, text)
		except Exception:
			log.debugWarning("Code Compass: finding the file for bookmarks failed", exc_info=True)
			path = None
		if path:
			key = os.path.normcase(os.path.abspath(path))
			seenBefore = _bookmarkSeen.get(previous) if unsaved else None
			snapshot = _saveSnapshots.get(hwnd)
			texts = []
			if unsaved and snapshot is not None and snapshot[0] == previous[2]:
				texts.append(snapshot[1])
			if seenBefore is not None:
				texts.append(seenBefore[0].text)
			if any(filepath.file_holds(path, t) for t in texts):
				# The document that had them was just saved under this name.
				store.move(previous, key)
				moved = _bookmarkSeen.pop(previous, None)
				if moved is not None:
					_bookmarkSeen[key] = moved
				else:
					_bookmarkSeen.pop(key, None)
	_bookmarkKeys[hwnd] = (title if isinstance(key, str) else shown, key)
	return key


def _bookmarks_for(obj, a, create=False):
	"""(key, bookmarks) of the document in obj, matched against its text a.
	The list is None when there are none (and create is False). Detached
	bookmarks are in the list too: use bookmarks.visible()."""
	key = _bookmark_key(obj, create)
	if key is None:
		return None, None
	store = _bookmark_store()
	seen = _bookmarkSeen.get(key)
	if seen is None or seen[0] is not a:
		clean = not _window_title(obj).startswith("*")
		if isinstance(key, str) and clean and not filepath.file_holds(key, a.text):
			# Classic Notepad's title has no folder: another file with the same
			# name may have been opened in this window. Look again.
			_bookmarkKeys.pop(getattr(obj, "windowHandle", None), None)
			key = _bookmark_key(obj, create)
			if key is None:
				return None, None
			seen = _bookmarkSeen.get(key)
		elif not isinstance(key, str) and clean and not a.text:
			# File > New in classic Notepad: a fresh "Untitled" document.
			store.drop(key)
			_bookmarkSeen.pop(key, None)
	if not create and not store.has(key):
		return key, None
	marks = store.get(key)
	if seen is None or seen[0] is not a:
		lines = [a.line_text(i) for i in range(a.lineCount)]
		if bookmarks.reanchor(marks, lines, seen[1] if seen else None):
			store.dirty = True
		_bookmarkSeen[key] = (a, lines)
	return key, marks


# --- Going back ----------------------------------------------------------------------

#: Window handle -> {"back": [...], "forward": [...]}, places as (title,
#: Bookmark, column): where the caret was before Code Compass (or control+G)
#: moved it far.
_history = {}
HISTORY_SIZE = 50
#: Window handle -> caret line when control+G opened the Go To dialog.
_goToPending = {}


def _place(obj, a, offset):
	li = a.line_index(offset)
	return (_window_title(obj).lstrip("*"), bookmarks.Bookmark(li, a.line_text(li).strip()), offset - a.lineStarts[li])


#: Window handle -> the document title its history last saw.
_historyTitles = {}


def _history_for(obj):
	"""The window's back and forward lists. In classic Notepad (one document
	per window), places of a new document follow it when it is first saved."""
	hwnd = getattr(obj, "windowHandle", None)
	h = _history.setdefault(hwnd, {"back": [], "forward": []})
	title = _window_title(obj).lstrip("*")
	last = _historyTitles.get(hwnd)
	appName = getattr(getattr(obj, "appModule", None), "appName", None)
	try:
		text = _cache.get(obj).text
	except Exception:
		text = None
	if last and last != title and filepath.title_file(last) is None:
		# A new document was either saved under a name (its places follow
		# it) or, in classic Notepad (one document per window), replaced by
		# another one (File > Open: its places are gone). In Notepad++ the
		# other tabs keep theirs.
		snapshot = _saveSnapshots.get(hwnd)
		saved = snapshot is not None and snapshot[0] == last and snapshot[1] == text
		for stack in (h["back"], h["forward"]):
			if saved:
				stack[:] = [(title if t == last else t, mark, column) for t, mark, column in stack]
			elif appName != "notepad++":
				stack[:] = [entry for entry in stack if entry[0] != last]
	if filepath.title_file(title) is None and text == "" and not _window_title(obj).startswith("*"):
		# A fresh, empty new document (File > New, a new tab): nothing of an
		# earlier one with the same title applies.
		for stack in (h["back"], h["forward"]):
			stack[:] = [entry for entry in stack if entry[0] != title]
	_historyTitles[hwnd] = title
	return h


def _remember_place(obj, a, offset, place=None):
	"""Remember offset (or a place taken earlier) as a place to come back to:
	the caret before a jump."""
	h = _history_for(obj)
	if place is None:
		place = _place(obj, a, offset)
	back = h["back"]
	if back and back[-1][0] == place[0] and back[-1][1].line == place[1].line:
		back[-1] = place
	else:
		back.append(place)
	del back[:-HISTORY_SIZE]
	h["forward"] = []


def _after_go_to(obj, before):
	"""After Notepad's Go To dialog (control+G): when the caret moved,
	remember where it was and say where it landed. A cancelled dialog
	changes nothing."""
	line, place = before
	try:
		a = _cache.get(obj)
		li = a.line_index(_caret_offset(obj, a.text))
	except Exception:
		log.debugWarning("Code Compass: go to line check failed", exc_info=True)
		return
	if li == line:
		return
	_remember_place(obj, a, None, place)
	speech.speak([_line_place(a, li)])


def _line_place(a, li):
	"""Where a line is: "line 40, in function load"."""
	# Translators: a line number, e.g. "line 40".
	place = _("line {line}").format(line=li + 1)
	chain = a.declaration_chain(a.first_char(li))
	if chain:
		place += ", " + _("in {kind} {name}").format(kind=_(chain[-1].kind), name=chain[-1].name)
	return place


def _declaration_message(obj, a, offset):
	"""When the caret has moved into another function or class: what to
	say, like VS Code's breadcrumbs. None when nothing changed."""
	if not _conf()["announceDeclarations"]:
		return None
	chain = a.declaration_chain(offset)
	current = chain[-1] if chain else None
	key = (current.line, current.name) if current else None
	last = getattr(obj, "_codeCompassLastDeclaration", "unset")
	try:
		obj._codeCompassLastDeclaration = key
	except Exception:
		pass
	if last == "unset" or key == last:
		return None
	if current is None:
		# Translators: the caret left every function and class.
		return _("top level")
	# Translators: the caret entered a function or class, e.g. "in function load".
	return _("in {kind} {name}").format(kind=_(current.kind), name=current.name)


def _line_closer_message(a, li):
	"""What a line's leading closing bracket closes, if that is enabled."""
	if not _conf()["announceClosers"]:
		return None
	off = a.leading_closer(li)
	return a.describe_closer(off) if off is not None else None


def _after_typed_character(obj, ch):
	"""Runs just after a character was typed in a code editor: auto-close a
	bracket or quote, type over an auto-closed one, line a closing bracket up
	with its opener, and say what a closing bracket closes."""
	if api.getFocusObject() is not obj:
		return
	try:
		a = _cache.get(obj)
		caret = _caret_offset(obj, a.text)
	except Exception:
		log.debugWarning("Code Compass: typed character check failed", exc_info=True)
		return
	off = caret - 1
	if off < 0 or a.text[off] != ch:
		return
	c = _conf()
	writable = _writable_notepad(obj)
	if writable and c["autoClose"]:
		hwnd = getattr(obj, "windowHandle", None)
		li = a.line_index(caret)
		lineEnd = a.line_bounds(li)[1]
		# Characters auto-close added on this line, as (line, characters
		# after them to the line end, character): that distance stays the
		# same while typing before them.
		pending = [p for p in _autoClosed.get(hwnd, ()) if p[0] == li]
		_autoClosed[hwnd] = pending
		if editing.stale_apostrophe(a, caret, ch):
			# "'a " (a lifetime) cannot be a character literal: the apostrophe
			# auto-close added after it goes.
			if not _apply_edit(obj, a, caret, caret + 1, "", caret):
				return
			pending[:] = [p for p in pending if p[1] != lineEnd - caret]
			a = _cache.get(obj)
			lineEnd -= 1
		mine = (li, lineEnd - caret, ch)
		if a.text[caret:caret + 1] == ch and (mine in pending or editing.autoclose_skip(a, caret, ch)):
			# Typing over the closing character auto-close added.
			if not _apply_edit(obj, a, caret, caret + 1, "", caret):
				return
			if mine in pending:
				pending.remove(mine)
			a = _cache.get(obj)
		elif editing.should_autoclose(a, caret, ch):
			if _apply_edit(obj, a, caret, caret, editing.AUTO_PAIRS[ch], caret):
				pending.append((li, lineEnd + 1 - caret, editing.AUTO_PAIRS[ch]))
			return
	if ch not in analyzer.CLOSERS:
		return
	if writable and c["autoIndent"]:
		change = editing.closer_reindent(a, off)
		if change:
			start, end, indent = change
			newCaret = start + len(indent) + (caret - end)
			if _apply_edit(obj, a, start, end, indent, newCaret):
				a = _cache.get(obj)
				off = newCaret - 1
	if c["announceClosers"]:
		msg = a.describe_closer(off)
		if msg:
			speech.speak([msg])


#: Window handle -> characters auto-close added and not typed over yet.
_autoClosed = {}


def _delete_auto_pair(obj):
	"""Backspace between an opener and the closer auto-close added for it
	("(|)"): delete both. True when done."""
	a = _cache.get(obj)
	start, end = _selection_offsets(obj, a.text)
	if start != end or start < 1:
		return False
	caret = start
	ch = a.text[caret - 1]
	partner = editing.AUTO_PAIRS.get(ch)
	if partner is None or a.text[caret:caret + 1] != partner:
		return False
	hwnd = getattr(obj, "windowHandle", None)
	li = a.line_index(caret)
	entry = (li, a.line_bounds(li)[1] - caret, partner)
	pending = _autoClosed.get(hwnd, [])
	if entry not in pending:
		return False
	if not _apply_edit(obj, a, caret - 1, caret + 1, "", caret - 1):
		return False
	pending.remove(entry)
	speech.speakSpelling(ch)
	return True


# --- Problems ---------------------------------------------------------------------

#: The last run's error per editor window: (file name, problems.Problem).
#: It only counts while the window still shows that file.
_runErrors = {}
#: Window handle: number of the latest run started from it.
_runSequence = {}
#: Windows whose run error F8 has not visited yet.
_runErrorPending = set()


def _problems(obj, a):
	"""Problems in the analysed document (cached on the analysis)."""
	hwnd = getattr(obj, "windowHandle", None)
	title = _window_title(obj)
	runError = _run_error_for(hwnd, title)
	ext = analyzer.extension_from_title(title)
	key = (ext, id(runError))
	cached = getattr(a, "_codeCompassProblems", None)
	if cached and cached[0] == key:
		return cached[1]
	extra = [runError] if runError is not None and runError.line < a.lineCount else []
	try:
		found = problems.find_problems(a, ext, extra)
	except Exception:
		log.debugWarning("Code Compass: problem check failed", exc_info=True)
		found = []
	a._codeCompassProblems = (key, found)
	return found


def _duration(seconds):
	"""A short spoken duration: "0.4 seconds", "12 seconds", "1 minute",
	"2 minutes 5 seconds"."""
	if seconds < 0.05:
		# Translators: a very short program run.
		return _("under 0.1 seconds")
	if seconds < 9.95:
		# Translators: the decimal separator in numbers such as "1.3".
		point = _(".")
		# Translators: a duration in seconds, e.g. "1.3 seconds".
		return _("{seconds} seconds").format(seconds=("%.1f" % seconds).replace(".", point))
	total = int(round(seconds))
	minutes, rest = divmod(total, 60)
	parts = []
	if minutes:
		# Translators: minutes of a duration, e.g. "2 minutes".
		parts.append(_("1 minute") if minutes == 1 else _("{minutes} minutes").format(minutes=minutes))
	if rest or not minutes:
		# Translators: seconds of a duration, e.g. "1 second".
		parts.append(_("1 second") if rest == 1 else _("{seconds} seconds").format(seconds=rest))
	return " ".join(parts)


def _line_count(item):
	"""How long a declaration is, from its header to its end: "42 lines"."""
	count = item.endLine - item.line + 1
	# Translators: the length of a function or class, e.g. "42 lines".
	return _("{count} lines").format(count=count) if count != 1 else _("1 line")


def _run_error_for(hwnd, title):
	"""The last run's error for this window, if the window still shows the
	file that was run."""
	entry = _runErrors.get(hwnd)
	if entry is None:
		return None
	name, problem = entry
	current = filepath.title_file(title)
	if not current or os.path.basename(current).lower() != name.lower():
		return None
	return problem


def _problem_label(p):
	if p.kind == "bracket":
		return p.message
	if p.kind == "warning":
		# Translators: a warning (allowed code that looks like a slip) and its line,
		# e.g. "line 19, warning: main is declared inside main".
		return _("line {line}, warning: {message}").format(line=p.line + 1, message=p.message)
	# Translators: a problem and its line, e.g. "line 12: invalid syntax".
	return _("line {line}: {message}").format(line=p.line + 1, message=p.message)


def _problems_text(found):
	return "; ".join(_problem_label(p) for p in found[:5])


def _problems_message(found):
	if len(found) == 1:
		# Translators: one problem, followed by its description.
		return _("1 problem: {list}").format(list=_problems_text(found))
	# Translators: number of problems, followed by the first few.
	return _("{count} problems: {list}").format(count=len(found), list=_problems_text(found))


#: Window handle -> (title, text) of the document as it was being saved.
_saveSnapshots = {}
#: Windows whose Save As dialog was open when the save was checked.
_saveAsPending = set()


def _before_save(obj):
	"""Note the document as it is saved, so its bookmarks and places can
	follow it to its new name (a new document saved for the first time)."""
	try:
		a = _cache.get(obj)
		hwnd = getattr(obj, "windowHandle", None)
		shown = _window_title(obj)
		_saveSnapshots[hwnd] = (shown.lstrip("*"), a.text, shown)
		# Bookmarks match against this very text.
		_bookmarks_for(obj, a)
		_history_for(obj)
	except Exception:
		log.debugWarning("Code Compass: noting the save failed", exc_info=True)


def _after_save(obj, viaDialog=False):
	"""After control+S or Save As: move bookmarks and places to the new
	name, then report problems. viaDialog: the Save As dialog was open."""
	hwnd = getattr(obj, "windowHandle", None)
	if api.getFocusObject() is not obj:
		# The Save As dialog is open: wait for the editor to get focus back.
		_saveAsPending.add(hwnd)
		return
	title = _window_title(obj)
	snapshot = _saveSnapshots.get(hwnd)
	saved = not title.startswith("*") and filepath.title_file(title)
	if saved and viaDialog and snapshot is not None:
		# After a dialog, only a new name or a cleared "*" means it saved.
		saved = title != snapshot[0] or snapshot[2].startswith("*")
	if not saved:
		# Not saved (the dialog was cancelled).
		_saveSnapshots.pop(hwnd, None)
		return
	try:
		_remember_disk(obj)
		_history_for(obj)
		_bookmarks_for(obj, _cache.get(obj))
		_save_bookmarks()
	except Exception:
		log.debugWarning("Code Compass: following the save failed", exc_info=True)
	if _conf()["checkOnSave"]:
		_check_after_save(obj)
	else:
		_play("save")


def _check_after_save(obj):
	# A Save As dialog took focus: the file is not saved yet.
	if api.getFocusObject() is not obj:
		return
	try:
		a = _cache.get(obj)
		found = _problems(obj, a)
	except Exception:
		log.debugWarning("Code Compass: check on save failed", exc_info=True)
		return
	_liveProblems[getattr(obj, "windowHandle", None)] = (_live_file(obj), _live_snapshot(found))
	if found:
		name, beep = _problem_sound(found)
		_play(name, beep)
		# Translators: reported after saving a file with problems.
		ui.message(_("Saved, but: {problems}").format(problems=_problems_message(found)))
	else:
		_play("save")
		# Translators: reported after saving a file in which no problems were found.
		ui.message(_("Saved, no problems"))


# --- Files changed on disk ---------------------------------------------------------

#: Window handle -> {"title", "path", "stamp", "text"}: the shown file as
#: last seen on disk ("stamp" is its time and size).
_disk = {}


def _disk_path(obj):
	"""The file the editor shows, without asking the user; None if unknown,
	not saved yet, or in Notepad++ (which watches its files itself)."""
	if getattr(getattr(obj, "appModule", None), "appName", None) == "notepad++":
		return None
	shown = _window_title(obj)
	title = shown.lstrip("*")
	hwnd = getattr(obj, "windowHandle", None)
	state = _disk.get(hwnd)
	try:
		text = _cache.get(obj).text
	except Exception:
		text = None
	if state and state["title"] == title:
		if (
			shown.startswith("*") or text is None
			or (state["text"] is not None and filepath.same_text(text, state["text"]))
			or filepath.file_holds(state["path"], text)
		):
			return state["path"]
		# Classic Notepad's title has no folder: File > Open or Save As of a
		# file with the same name elsewhere. Look again.
		_disk.pop(hwnd, None)
	if not filepath.title_file(title):
		return None
	remembered = _rememberedPaths.get(hwnd)
	path = None
	try:
		# The file holding the shown text; with unsaved changes, which hide
		# that, any single candidate.
		path = filepath.find_file(shown, getattr(obj, "processID", None), remembered, text)
		if path is None and shown.startswith("*"):
			path = filepath.find_file(shown, getattr(obj, "processID", None), remembered, None)
	except Exception:
		log.debugWarning("Code Compass: finding the file failed", exc_info=True)
	return path


def _stamp(path):
	try:
		st = os.stat(path)
		return (st.st_mtime_ns, st.st_size)
	except OSError:
		return None


def _remember_disk(obj, path=None, text=None, stamp=None):
	"""Note the file as it is on disk now (after a save or reload). stamp:
	the time stamp taken before text was read, so a change in between is
	noticed later."""
	path = path or _disk_path(obj)
	if not path:
		return
	if text is None:
		stamp = _stamp(path)
		text = filepath.read_text(path)
	elif stamp is None:
		stamp = _stamp(path)
	_disk[getattr(obj, "windowHandle", None)] = {
		"title": _window_title(obj).lstrip("*"), "path": path, "stamp": stamp, "text": text,
	}


def _check_disk(obj):
	"""Back in the editor: if another program changed the file, reload it
	(no unsaved changes) or say so (unsaved changes)."""
	if api.getFocusObject() is not obj:
		return
	try:
		path = _disk_path(obj)
		if not path:
			return
		hwnd = getattr(obj, "windowHandle", None)
		state = _disk.get(hwnd)
		title = _window_title(obj).lstrip("*")
		if state is None or state["title"] != title or state["path"] != path:
			# First look at this file: what is on disk now is the start.
			_remember_disk(obj, path)
			return
		stamp = _stamp(path)
		if stamp == state["stamp"]:
			return
		name = os.path.basename(path)
		if stamp is None:
			state["stamp"] = None
			# Translators: the open file was deleted or moved by another program.
			ui.message(_("{name} is no longer on disk").format(name=name))
			return
		if hwnd in _saveAsPending:
			# A save is under way (a dialog or Notepad's own question): the
			# change is ours.
			return
		disk = filepath.read_text(path)
		if disk is None:
			return
		a = _cache.get(obj)
		previous = state["text"]
		state["stamp"] = stamp
		if previous is not None and filepath.same_text(disk, previous):
			return
		state["text"] = disk
		if filepath.same_text(disk, a.text) or filepath.same_text(disk, filepath.ansi_round_trip(a.text)):
			# Saved from this editor (also as ANSI, where Notepad turns
			# characters the code page lacks into "?"), or changed to the same.
			return
		if not _writable_notepad(obj):
			# Translators: the open file was changed by another program (in an editor
			# Code Compass cannot reload).
			ui.message(_("{name} changed on disk").format(name=name))
			return
		if _window_title(obj).startswith("*") or previous is None or not filepath.same_text(a.text, previous):
			# Unsaved changes, or the editor did not show the version on disk:
			# replacing its text could lose work.
			# Translators: the open file was changed by another program while it has
			# unsaved changes here.
			ui.message(_("{name} changed on disk, and you have unsaved changes. NVDA+shift+K, then R reloads it").format(name=name))
			return
		changes = _reload(obj, a, path, disk, stamp)
		if changes is None:
			# Translators: reloading the file into the editor failed.
			ui.message(_("Could not reload {name}").format(name=name))
			return
		if changes is not None:
			# Translators: the open file was changed by another program and reloaded,
			# e.g. "latihan.py changed on disk and was reloaded: 3 lines added".
			ui.message(_("{name} changed on disk and was reloaded: {changes}").format(name=name, changes=changes))
	except Exception:
		log.debugWarning("Code Compass: checking the file on disk failed", exc_info=True)


#: A whole file replaced at once: Notepad with word wrap needs seconds for
#: a few megabytes.
RELOAD_TIMEOUT_MS = 30000


def _reload(obj, a, path, disk, stamp=None):
	"""Replace the editor's text with disk (the file's text, read after
	stamp was taken), keeping the caret on its line. Returns what changed,
	as words, or None on failure."""
	nl = editing.newline_style(a.text)
	newText = analyzer._NEWLINES.sub(nl, disk)
	oldLines = [a.line_text(i) for i in range(a.lineCount)]
	newLines = analyzer._NEWLINES.split(newText)
	caret = _caret_offset(obj, a.text)
	li = a.line_index(caret)
	column = caret - a.lineStarts[li]
	mapping = bookmarks.line_map(oldLines, newLines)
	target = mapping(li)
	if target is None:
		target = min(li, len(newLines) - 1)
	newStarts = [0]
	for line in newLines[:-1]:
		newStarts.append(newStarts[-1] + len(line) + len(nl))
	newCaret = newStarts[target] + min(column, len(newLines[target]))
	if not _apply_edit(obj, a, 0, len(a.text), newText, newCaret, timeout=RELOAD_TIMEOUT_MS):
		return None
	try:
		edit_control.mark_unmodified(obj.windowHandle)
	except Exception:
		log.debugWarning("Code Compass: clearing the changed mark failed", exc_info=True)
	_remember_disk(obj, path, disk, stamp)
	return _change_words(oldLines, newLines)


def _change_words(oldLines, newLines):
	"""How two versions differ: "2 lines changed, 1 line added"."""
	changed = added = removed = 0
	# Only the part between the unchanged first and last lines is compared,
	# with a diff when it is small; a large one (a reformatted file) is
	# counted by its length, so NVDA never waits on it.
	nOld, nNew = len(oldLines), len(newLines)
	prefix = 0
	while prefix < nOld and prefix < nNew and oldLines[prefix] == newLines[prefix]:
		prefix += 1
	suffix = 0
	while suffix < nOld - prefix and suffix < nNew - prefix and oldLines[nOld - 1 - suffix] == newLines[nNew - 1 - suffix]:
		suffix += 1
	oldMid = oldLines[prefix:nOld - suffix]
	newMid = newLines[prefix:nNew - suffix]
	if len(oldMid) <= 500 and len(newMid) <= 500:
		import difflib
		for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, oldMid, newMid, autojunk=False).get_opcodes():
			if tag == "replace":
				both = min(i2 - i1, j2 - j1)
				changed += both
				added += (j2 - j1) - both
				removed += (i2 - i1) - both
			elif tag == "insert":
				added += j2 - j1
			elif tag == "delete":
				removed += i2 - i1
	else:
		changed = min(len(oldMid), len(newMid))
		added = max(0, len(newMid) - len(oldMid))
		removed = max(0, len(oldMid) - len(newMid))
	parts = []
	if changed:
		# Translators: part of a reload report.
		parts.append(_("1 line changed") if changed == 1 else _("{count} lines changed").format(count=changed))
	if added:
		# Translators: part of a reload report.
		parts.append(_("1 line added") if added == 1 else _("{count} lines added").format(count=added))
	if removed:
		# Translators: part of a reload report.
		parts.append(_("1 line removed") if removed == 1 else _("{count} lines removed").format(count=removed))
	# Translators: a reload that changed only spaces or line breaks.
	return ", ".join(parts) if parts else _("only spacing changed")


# --- Problems while typing ---------------------------------------------------------

#: Window handle -> problems as last checked: a list of (kind, message) with
#: line numbers left out, so lines added above do not make them new.
_liveProblems = {}
#: Window handle -> number of the latest scheduled check (only it runs).
_liveChecks = {}
#: Wait this long after the last key before checking, like VS Code.
LIVE_CHECK_DELAY = 900


def _live_key(p):
	"""A problem without its line number and the line's text, which change
	while typing ("unclosed paren on line 2: print(fo"), in any language."""
	words = {"line", _("line {line}").split("{line}")[0].strip()}
	pattern = r"\b(?:%s)\s*\d+.*$" % "|".join(re.escape(w) for w in words if w)
	return (p.kind, re.sub(pattern, "", p.message))


def _live_file(obj):
	"""The document a window shows (Notepad++ tabs share one window)."""
	return _window_title(obj).lstrip("*")


def _live_snapshot(found):
	return sorted(_live_key(p) for p in found if p.kind != "run")


def _schedule_live_check(obj):
	"""After typing pauses, look for problems again and sound new ones."""
	if _conf()["liveCheck"] == "off":
		return
	hwnd = getattr(obj, "windowHandle", None)
	stored = _liveProblems.get(hwnd)
	if stored is None or stored[0] != _live_file(obj):
		# The problems before this typing started, in this document.
		try:
			_liveProblems[hwnd] = (_live_file(obj), _live_snapshot(_problems(obj, _cache.get(obj))))
		except Exception:
			return
	token = _liveChecks[hwnd] = _liveChecks.get(hwnd, 0) + 1
	core.callLater(LIVE_CHECK_DELAY, _live_check, obj, token)


def _live_check(obj, token):
	hwnd = getattr(obj, "windowHandle", None)
	if _liveChecks.get(hwnd) != token or api.getFocusObject() is not obj:
		return
	mode = _conf()["liveCheck"]
	try:
		a = _cache.get(obj)
		if a.langName == "generic":
			# Plain text: a "(" in prose is no problem.
			return
		found = _problems(obj, a)
		caretLine = a.line_index(_caret_offset(obj, a.text))
	except Exception:
		log.debugWarning("Code Compass: checking while typing failed", exc_info=True)
		return
	now = _live_snapshot(found)
	stored = _liveProblems.get(hwnd)
	_liveProblems[hwnd] = (_live_file(obj), list(now))
	if stored is None or stored[0] != _live_file(obj):
		# Another document now: this is its starting point.
		return
	for item in stored[1]:
		if item in now:
			now.remove(item)
	if not now or mode == "off":
		return
	fresh = [p for p in found if p.kind != "run" and _live_key(p) in now]
	# The one nearest the caret is the one just typed.
	fresh.sort(key=lambda p: abs(p.line - caretLine))
	name, beep = _problem_sound(fresh[:1])
	_play(name, beep)
	if mode == "speech":
		speech.speak([_problem_label(fresh[0])])


# --- Editing Notepad ----------------------------------------------------------------


def _apply_edit(obj, a, start, end, newText, selStart=None, selEnd=None, timeout=None):
	"""Replace a.text[start:end] with newText in a writable Win32 edit
	control, then select selStart..selEnd (offsets in the new text). One
	step for control+Z. True on success."""
	try:
		extra = {"timeout": timeout} if timeout else {}
		ok = edit_control.replace(obj.windowHandle, a.text, start, end, newText, selStart, selEnd, **extra)
	except Exception:
		log.debugWarning("Code Compass: edit failed", exc_info=True)
		ok = False
	if ok:
		_forget_selection_change(obj)
	return ok


def _speak_caret_line(obj, gesture=None):
	"""Read the caret's line the way NVDA does after a caret move, with
	Code Compass's own line reports."""
	try:
		info = obj.makeTextInfo(textInfos.POSITION_CARET)
	except Exception:
		return
	if isinstance(obj, CodeEditor) and gesture is not None:
		obj._caretScriptPostMovedHelper(textInfos.UNIT_LINE, gesture, info)
		return
	# Without a key press (the palette, a line operation), NVDA's own helper
	# cannot be used: it reads the gesture. Do its work here.
	after = obj._codeCompassLineReports(info) if isinstance(obj, CodeEditor) else []
	line = info.copy()
	line.expand(textInfos.UNIT_LINE)
	speech.speakTextInfo(line, unit=textInfos.UNIT_LINE, reason=controlTypes.OutputReason.CARET)
	for message in after:
		speech.speak([message])
	braille.handler.handleCaretMove(obj)


#: The running plugin, for the editor overlay's quick keys.
_plugin = None


def _delegate(name, gesture):
	if _plugin is not None:
		getattr(_plugin, "script_" + name)(gesture)


class CodeEditor(NVDAObject):
	"""Overlay for editors in the enabled applications: reports the bracket
	level, closing brackets, problems and the current function as the caret
	moves, and adds quick keys."""

	_codeCompassLastLevel = None

	def _codeCompassLineReports(self, info=None):
		"""Play the level and problem sounds for the caret's line, and return
		what to say after the line itself (closing bracket, new function)."""
		try:
			a = _cache.get(self)
			offset = _caret_offset(self, a.text, info)
			li = a.line_index(offset)
			_stop_line_sounds(self)
			_announce_line_level(self, a, li)
			errorLength = _announce_line_problem(self, a, li)
			_announce_line_bookmark(self, a, li, errorLength)
			return [m for m in (_line_closer_message(a, li), _declaration_message(self, a, offset)) if m]
		except Exception:
			log.debugWarning("Code Compass: line report failed", exc_info=True)
			return []

	def _caretScriptPostMovedHelper(self, speakUnit, gesture, info=None):
		_autoClosed.pop(getattr(self, "windowHandle", None), None)
		after = []
		if speakUnit == textInfos.UNIT_LINE and not isScriptWaiting():
			after = self._codeCompassLineReports(info)
		super(CodeEditor, self)._caretScriptPostMovedHelper(speakUnit, gesture, info)
		for message in after:
			# After the line itself, e.g. "}" then "closes func load()".
			speech.speak([message])

	def event_typedCharacter(self, ch):
		super(CodeEditor, self).event_typedCharacter(ch)
		_schedule_live_check(self)
		c = _conf()
		if ch in analyzer.CLOSERS or (c["autoClose"] and ch in editing.AUTO_PAIRS):
			# Let the editor insert the character first.
			core.callLater(60, _after_typed_character, self, ch)

	# Keys that change text work in classic Notepad's edit control. Elsewhere
	# (or when turned off) the key does what it always does.

	def script_ccEnter(self, gesture):
		if not (_conf()["autoIndent"] and _writable_notepad(self)):
			return self.script_caret_newLine(gesture)
		try:
			a = _cache.get(self)
			start, end = _selection_offsets(self, a.text)
			text, caretIn = editing.enter_text(a, start, editing.indent_unit(a.text), end)
		except Exception:
			log.debugWarning("Code Compass: auto-indent failed", exc_info=True)
			return self.script_caret_newLine(gesture)
		# Notepad gets no Enter key now, so say the word just typed, as NVDA
		# does on Enter when "Speak typed words" is on.
		speech.speakTypedCharacters("\r")
		selStart = start + caretIn if caretIn is not None else None
		if not _apply_edit(self, a, start, end, text, selStart):
			return self.script_caret_newLine(gesture)
		_speak_caret_line(self, gesture)

	def script_ccTab(self, gesture):
		if not _writable_notepad(self) or not _plugin or not _plugin._shift_lines(self, outward=False):
			gesture.send()

	def script_ccShiftTab(self, gesture):
		if not _writable_notepad(self) or not _plugin or not _plugin._shift_lines(self, outward=True):
			gesture.send()

	def _edit_key(self, name, gesture):
		if _writable_notepad(self):
			_delegate(name, gesture)
		else:
			gesture.send()

	def _notepad_key(self, name, gesture):
		"""A reading key that Notepad++ has its own command for (F8, F12,
		control+shift+P, control+shift+space): Code Compass's in Notepad,
		Notepad++'s own there. The command palette and NVDA+shift+K still
		reach Code Compass's version everywhere."""
		if getattr(getattr(self, "appModule", None), "appName", None) == "notepad++":
			gesture.send()
		else:
			_delegate(name, gesture)

	def script_ccToggleComment(self, gesture):
		self._edit_key("toggleComment", gesture)

	def script_ccComplete(self, gesture):
		self._edit_key("complete", gesture)

	def script_ccRename(self, gesture):
		self._edit_key("rename", gesture)

	def script_ccDeleteLine(self, gesture):
		self._edit_key("deleteLine", gesture)

	def script_ccMoveLineUp(self, gesture):
		self._edit_key("moveLineUp", gesture)

	def script_ccMoveLineDown(self, gesture):
		self._edit_key("moveLineDown", gesture)

	def script_ccDuplicateLine(self, gesture):
		self._edit_key("duplicateLine", gesture)

	# Quick keys that only read (no descriptions: the assignable versions live
	# on the global plugin, in the Code Compass input gestures category).

	def script_ccNextSameLevel(self, gesture):
		_delegate("nextSameLevel", gesture)

	def script_ccPreviousSameLevel(self, gesture):
		_delegate("previousSameLevel", gesture)

	def script_ccNextDeclaration(self, gesture):
		_delegate("nextDeclaration", gesture)

	def script_ccPreviousDeclaration(self, gesture):
		_delegate("previousDeclaration", gesture)

	def script_ccParentDeclaration(self, gesture):
		_delegate("parentDeclaration", gesture)

	def script_ccChildDeclaration(self, gesture):
		_delegate("childDeclaration", gesture)

	def script_ccBlockStart(self, gesture):
		_delegate("blockStart", gesture)

	def script_ccBlockEnd(self, gesture):
		_delegate("blockEnd", gesture)

	def script_ccParameterHint(self, gesture):
		self._notepad_key("parameterHint", gesture)

	def script_ccOutline(self, gesture):
		_delegate("outline", gesture)

	def script_ccPalette(self, gesture):
		self._notepad_key("palette", gesture)

	def script_ccNextProblem(self, gesture):
		self._notepad_key("nextProblem", gesture)

	def script_ccPreviousProblem(self, gesture):
		self._notepad_key("previousProblem", gesture)

	def script_ccProblems(self, gesture):
		_delegate("problemsList", gesture)

	def script_ccRun(self, gesture):
		_delegate("runFile", gesture)

	def script_ccDefinition(self, gesture):
		self._notepad_key("definition", gesture)

	def script_ccReferences(self, gesture):
		_delegate("references", gesture)

	def script_ccTerminal(self, gesture):
		_delegate("terminal", gesture)

	def script_ccExplorer(self, gesture):
		_delegate("explorer", gesture)

	def script_ccToggleBookmark(self, gesture):
		_delegate("toggleBookmark", gesture)

	def script_ccNextBookmark(self, gesture):
		_delegate("nextBookmark", gesture)

	def script_ccPreviousBookmark(self, gesture):
		_delegate("previousBookmark", gesture)

	def script_ccGoToLine(self, gesture):
		try:
			a = _cache.get(self)
			offset = _caret_offset(self, a.text)
			_goToPending[getattr(self, "windowHandle", None)] = (a.line_index(offset), _place(self, a, offset))
		except Exception:
			log.debugWarning("Code Compass: go to line failed", exc_info=True)
		gesture.send()

	def event_gainFocus(self):
		super(CodeEditor, self).event_gainFocus()
		hwnd = getattr(self, "windowHandle", None)
		# Back in the editor: was the file changed by another program?
		core.callLater(150, _check_disk, self)
		before = _goToPending.pop(hwnd, None)
		if before is not None:
			# Back from the Go To dialog: after NVDA reads the line, say where it is.
			core.callLater(100, _after_go_to, self, before)
		if hwnd in _saveAsPending:
			# Back from the Save As dialog.
			_saveAsPending.discard(hwnd)
			core.callLater(300, _after_save, self, True)

	def script_ccGoBack(self, gesture):
		_delegate("goBack", gesture)

	def script_ccGoForward(self, gesture):
		_delegate("goForward", gesture)

	def script_ccBackspace(self, gesture):
		if _conf()["autoClose"] and _writable_notepad(self):
			try:
				if _delete_auto_pair(self):
					return
			except Exception:
				log.debugWarning("Code Compass: backspace failed", exc_info=True)
		self.script_caret_backspaceCharacter(gesture)

	def script_ccSave(self, gesture):
		_before_save(self)
		gesture.send()
		core.callLater(500, _after_save, self)

	def script_ccSaveAs(self, gesture):
		_before_save(self)
		gesture.send()
		core.callLater(500, _after_save, self)

	__gestures = {
		"kb:alt+downArrow": "ccNextSameLevel",
		"kb:alt+upArrow": "ccPreviousSameLevel",
		"kb:alt+pageDown": "ccNextDeclaration",
		"kb:alt+pageUp": "ccPreviousDeclaration",
		"kb:alt+leftArrow": "ccParentDeclaration",
		"kb:alt+rightArrow": "ccChildDeclaration",
		"kb:alt+home": "ccBlockStart",
		"kb:alt+end": "ccBlockEnd",
		"kb:control+s": "ccSave",
		"kb:backspace": "ccBackspace",
		"kb:control+shift+s": "ccSaveAs",
		"kb:enter": "ccEnter",
		"kb:numpadEnter": "ccEnter",
		"kb:tab": "ccTab",
		"kb:shift+tab": "ccShiftTab",
		"kb:control+/": "ccToggleComment",
		"kb:control+space": "ccComplete",
		"kb:control+shift+space": "ccParameterHint",
		"kb:control+shift+o": "ccOutline",
		"kb:control+shift+p": "ccPalette",
		"kb:f8": "ccNextProblem",
		"kb:shift+f8": "ccPreviousProblem",
		"kb:control+shift+m": "ccProblems",
		"kb:control+f5": "ccRun",
		"kb:f12": "ccDefinition",
		"kb:shift+f12": "ccReferences",
		"kb:f2": "ccRename",
		"kb:control+shift+k": "ccDeleteLine",
		"kb:control+shift+upArrow": "ccMoveLineUp",
		"kb:control+shift+downArrow": "ccMoveLineDown",
		"kb:control+shift+d": "ccDuplicateLine",
		"kb:control+`": "ccTerminal",
		"kb:control+shift+e": "ccExplorer",
		"kb:control+alt+k": "ccToggleBookmark",
		"kb:control+alt+l": "ccNextBookmark",
		"kb:control+alt+j": "ccPreviousBookmark",
		"kb:control+g": "ccGoToLine",
		"kb:control+alt+backspace": "ccGoBack",
		"kb:control+alt+shift+backspace": "ccGoForward",
	}


# --- Dialogs ------------------------------------------------------------------

#: The Code Compass dialog currently open, if any.
_openDialog = None


def _bring_to_front(dlg, focus=None, attempt=0):
	"""Windows sometimes keeps the editor in front; insist a few times."""
	try:
		dlg.Raise()
		ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(dlg.GetHandle()))
		if focus is not None:
			focus.SetFocus()
	except Exception:
		log.debugWarning("Code Compass: could not raise dialog", exc_info=True)
		return
	if attempt < 5 and not dlg.IsActive():
		wx.CallLater(100, _bring_to_front, dlg, focus, attempt + 1)


def _run_dialog(create, onClose):
	"""Show a modal dialog in front of the editor. Same order as NVDA's own
	Elements List: prePopup before the dialog exists, so it is created and
	shown while NVDA owns the foreground. onClose(dialog, result) runs before
	the dialog is destroyed. If a Code Compass dialog is already open (maybe
	hidden behind the editor), it is brought back instead."""
	if _openDialog is not None:
		_bring_to_front(_openDialog, getattr(_openDialog, "initialFocus", None))
		return

	def run():
		global _openDialog
		gui.mainFrame.prePopup()
		dlg = None
		try:
			dlg = _openDialog = create()
			focus = getattr(dlg, "initialFocus", None)

			def onShow(evt):
				evt.Skip()
				if evt.IsShown():
					wx.CallAfter(_bring_to_front, dlg, focus)

			dlg.Bind(wx.EVT_SHOW, onShow)
			result = dlg.ShowModal()
			onClose(dlg, result)
		finally:
			# Also when creating the dialog failed, so NVDA's popup state and
			# the "already open" check are not left behind.
			_openDialog = None
			if dlg is not None:
				dlg.Destroy()
			gui.mainFrame.postPopup()

	wx.CallAfter(run)


def _relabel(dialog, buttonId, label):
	"""Change the label of a standard dialog button (wxPython in NVDA has no
	StdDialogButtonSizer.GetAffirmativeButton)."""
	button = wx.FindWindowById(buttonId, dialog)
	if button:
		button.SetLabel(label)


def _finish_dialog(dialog, sizer, helper, buttons):
	helper.addDialogDismissButtons(buttons)
	sizer.Add(helper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND)
	dialog.SetSizer(sizer)
	sizer.Fit(dialog)
	dialog.CentreOnScreen()


class OutlineDialog(wx.Dialog):
	"""Declarations as a tree: methods sit under their class, so NVDA reports
	the level and left/right arrows collapse and expand."""

	def __init__(self, parent, items, selection):
		# Translators: title of the outline dialog.
		super(OutlineDialog, self).__init__(parent, title=_("Code outline"))
		self.choice = None
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.tree = helper.addLabeledControl(
			# Translators: label of the tree of functions and classes.
			_("&Declarations:"),
			wx.TreeCtrl,
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE,
		)
		root = self.tree.AddRoot("")
		nodes = {}
		for i, item in enumerate(items):
			parentNode = nodes.get(id(item.parentItem), root)
			nodes[id(item)] = self.tree.AppendItem(parentNode, item.tree_label(), data=i)
		for item in items:
			if item.children:
				self.tree.Expand(nodes[id(item)])
		if items:
			node = nodes[id(items[selection])]
			self.tree.SelectItem(node)
			self.tree.EnsureVisible(node)
		self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onOk)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		_finish_dialog(self, mainSizer, helper, self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.initialFocus = self.tree
		self.tree.SetFocus()

	def onOk(self, evt):
		if self.choice is None:
			node = self.tree.GetSelection()
			if node and node.IsOk():
				self.choice = self.tree.GetItemData(node)
		if self.IsModal():
			self.EndModal(wx.ID_OK)


class SnippetsDialog(wx.Dialog):
	"""Saved snippets with a preview; Enter inserts the selected one."""

	def __init__(self, parent, folder, preferExt):
		# Translators: title of the snippets dialog.
		super(SnippetsDialog, self).__init__(parent, title=_("Snippets"))
		self.folder = folder
		self.preferExt = preferExt
		self.choice = None
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		# Translators: label of the list of saved snippets.
		self.list = helper.addLabeledControl(_("&Snippets:"), wx.ListBox, choices=[])
		self.list.Bind(wx.EVT_LISTBOX, self.onSelect)
		self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.onOk)
		self.preview = helper.addLabeledControl(
			# Translators: label of the read-only view of a snippet's code.
			_("&Preview:"),
			wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
			size=(500, 200),
		)
		row = guiHelper.ButtonHelper(wx.HORIZONTAL)
		# Translators: button that deletes the selected snippet.
		self.deleteButton = row.addButton(self, label=_("De&lete"))
		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		# Translators: button that opens the snippets folder in Explorer.
		folderButton = row.addButton(self, label=_("Open snippets &folder"))
		folderButton.Bind(wx.EVT_BUTTON, self.onOpenFolder)
		helper.addItem(row)
		buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
		# Translators: button that inserts the selected snippet at the caret.
		_relabel(self, wx.ID_OK, _("&Insert"))
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		_finish_dialog(self, mainSizer, helper, buttons)
		self.refresh()
		self.initialFocus = self.list
		self.list.SetFocus()

	def refresh(self, select=0):
		self.items = snippets.list_snippets(self.folder, self.preferExt)
		self.list.Set([s.label() for s in self.items])
		if self.items:
			self.list.SetSelection(min(select, len(self.items) - 1))
		self.onSelect(None)

	def selected(self):
		i = self.list.GetSelection()
		return self.items[i] if 0 <= i < len(self.items) else None

	def onSelect(self, evt):
		snip = self.selected()
		try:
			self.preview.SetValue(snip.read() if snip else "")
		except (OSError, ValueError):
			log.debugWarning("Code Compass: could not read snippet", exc_info=True)
			self.preview.SetValue("")
		self.deleteButton.Enable(snip is not None)

	def onDelete(self, evt):
		snip = self.selected()
		if snip is None:
			return
		answer = gui.messageBox(
			# Translators: asks before deleting a snippet file.
			_("Delete snippet {name}?").format(name=snip.label()),
			# Translators: title of the delete snippet question.
			_("Delete snippet"),
			wx.YES_NO | wx.ICON_QUESTION,
			self,
		)
		if answer != wx.YES:
			return
		try:
			os.remove(snip.path)
		except OSError:
			log.error("Code Compass: could not delete snippet", exc_info=True)
		self.refresh(self.list.GetSelection())
		self.list.SetFocus()

	def onOpenFolder(self, evt):
		os.makedirs(self.folder, exist_ok=True)
		os.startfile(self.folder)
		self.EndModal(wx.ID_CANCEL)

	def onOk(self, evt):
		self.choice = self.selected()
		if self.IsModal():
			self.EndModal(wx.ID_OK)


class ListDialog(wx.Dialog):
	"""A list to choose from; Enter chooses (references, TODOs, problems)."""

	def __init__(self, parent, title, label, labels, selection=0, onDelete=None):
		super(ListDialog, self).__init__(parent, title=title)
		self.choice = None
		#: Called with an entry's index when Delete removes it (or None).
		self.onDelete = onDelete
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.list = helper.addLabeledControl(label, wx.ListBox, choices=labels)
		if labels:
			self.list.SetSelection(max(0, min(selection, len(labels) - 1)))
		self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.onOk)
		if onDelete is not None:
			self.list.Bind(wx.EVT_KEY_DOWN, self.onListKey)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		_finish_dialog(self, mainSizer, helper, self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.initialFocus = self.list
		self.list.SetFocus()

	def onListKey(self, evt):
		sel = self.list.GetSelection()
		if evt.GetKeyCode() != wx.WXK_DELETE or sel == wx.NOT_FOUND:
			evt.Skip()
			return
		self.onDelete(sel)
		self.list.Delete(sel)
		# Translators: reported after Delete removed an entry from a list.
		ui.message(_("Removed"))
		count = self.list.GetCount()
		if count:
			self.list.SetSelection(min(sel, count - 1))
		elif self.IsModal():
			self.EndModal(wx.ID_CANCEL)

	def onOk(self, evt):
		sel = self.list.GetSelection()
		self.choice = sel if sel != wx.NOT_FOUND else None
		if self.IsModal():
			self.EndModal(wx.ID_OK)


class PaletteDialog(wx.Dialog):
	"""Command palette: type to filter the commands, Enter runs one."""

	def __init__(self, parent, commands):
		# Translators: title of the command palette.
		super(PaletteDialog, self).__init__(parent, title=_("Code Compass commands"))
		#: (label, script name) pairs.
		self.commands = commands
		self.shown = list(commands)
		self.choice = None
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		# Translators: label of the field that filters the command palette.
		self.filter = helper.addLabeledControl(_("&Search commands:"), wx.TextCtrl)
		self.filter.Bind(wx.EVT_TEXT, self.onFilter)
		self.filter.Bind(wx.EVT_KEY_DOWN, self.onFilterKey)
		# Translators: label of the list of commands in the palette.
		self.list = helper.addLabeledControl(_("&Commands:"), wx.ListBox, choices=[l for l, _n in commands])
		if commands:
			self.list.SetSelection(0)
		self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.onOk)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		_finish_dialog(self, mainSizer, helper, self.CreateButtonSizer(wx.OK | wx.CANCEL))
		self.initialFocus = self.filter
		self.filter.SetFocus()

	def onFilter(self, evt):
		words = self.filter.GetValue().lower().split()
		self.shown = [c for c in self.commands if all(w in c[0].lower() for w in words)]
		self.list.Set([l for l, _n in self.shown])
		if self.shown:
			self.list.SetSelection(0)

	def onFilterKey(self, evt):
		# Down arrow goes from the search field to the list.
		if evt.GetKeyCode() == wx.WXK_DOWN and self.shown:
			self.list.SetFocus()
			return
		evt.Skip()

	def onOk(self, evt):
		sel = self.list.GetSelection()
		if 0 <= sel < len(self.shown):
			self.choice = self.shown[sel][1]
		if self.IsModal():
			self.EndModal(wx.ID_OK)


#: Folders and files the explorer leaves out, like VS Code does.
_EXPLORER_HIDDEN = {".git", ".svn", ".hg", "__pycache__", ".ds_store", "thumbs.db", "desktop.ini"}


def _explorer_entries(folder):
	"""(folders, files) in folder, sorted by name, without hidden ones."""
	folders, files = [], []
	try:
		# scandir has each entry's attributes without another system call.
		entries = list(os.scandir(folder))
	except OSError:
		return folders, files
	for entry in entries:
		if entry.name.lower() in _EXPLORER_HIDDEN:
			continue
		try:
			if getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & (2 | 4):
				continue
			isDir = entry.is_dir()
		except OSError:
			continue
		(folders if isDir else files).append(entry.name)
	key = str.lower
	return sorted(folders, key=key), sorted(files, key=key)


class ExplorerDialog(wx.Dialog):
	"""Files and folders of the project as a tree, like VS Code's Explorer.
	Enter opens a file in the editor; buttons create, rename and delete."""

	def __init__(self, parent, root, current, openFile):
		super(ExplorerDialog, self).__init__(parent, title=self._title(root))
		self.root = root
		self.openFile = openFile
		self.choice = None
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.tree = helper.addLabeledControl(
			# Translators: label of the explorer's tree of files and folders.
			_("&Files and folders:"),
			wx.TreeCtrl,
			style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE,
			size=(450, 350),
		)
		self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.onExpanding)
		self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onActivate)
		self.tree.Bind(wx.EVT_KEY_DOWN, self.onTreeKey)
		row = guiHelper.ButtonHelper(wx.HORIZONTAL)
		for label, handler in (
			# Translators: explorer button; each button needs its own & letter.
			(_("New fi&le"), self.onNewFile),
			# Translators: explorer button.
			(_("New fol&der"), self.onNewFolder),
			# Translators: explorer button; F2 does the same in the tree.
			(_("&Rename"), self.onRename),
			# Translators: explorer button; Delete does the same in the tree.
			(_("Dele&te"), self.onDelete),
			# Translators: explorer button that copies the item's full path.
			(_("Copy &path"), self.onCopyPath),
		):
			row.addButton(self, label=label).Bind(wx.EVT_BUTTON, handler)
		helper.addItem(row)
		row2 = guiHelper.ButtonHelper(wx.HORIZONTAL)
		for label, handler in (
			# Translators: explorer button that shows the parent folder.
			(_("&Up one folder"), self.onUp),
			# Translators: explorer button that picks another folder.
			(_("&Choose folder..."), self.onChooseFolder),
			# Translators: explorer button that opens the item in Windows Explorer.
			(_("Show in &Windows Explorer"), self.onShowInExplorer),
			# Translators: explorer button that opens a command prompt there.
			(_("Command pro&mpt here"), self.onTerminal),
		):
			row2.addButton(self, label=label).Bind(wx.EVT_BUTTON, handler)
		helper.addItem(row2)
		buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
		# Translators: explorer button that opens the selected file.
		_relabel(self, wx.ID_OK, _("&Open"))
		# Translators: closes the explorer.
		_relabel(self, wx.ID_CANCEL, _("Close"))
		self.Bind(wx.EVT_BUTTON, self.onOpen, id=wx.ID_OK)
		_finish_dialog(self, mainSizer, helper, buttons)
		self.load(root, current)
		self.initialFocus = self.tree
		self.tree.SetFocus()

	@staticmethod
	def _title(root):
		# Translators: title of the explorer, with the folder's name.
		return _("Explorer: {folder}").format(folder=os.path.basename(root.rstrip("\\/")) or root)

	# Tree ------------------------------------------------------------------

	def load(self, root, select=None):
		self.root = root
		self.SetTitle(self._title(root))
		self.tree.DeleteAllItems()
		node = self.tree.AddRoot(os.path.basename(root.rstrip("\\/")) or root, data=root)
		self._fill(node, root)
		self.tree.Expand(node)
		target = node
		if select and os.path.normcase(select).startswith(os.path.normcase(root.rstrip("\\/") + os.sep)):
			# Expand down to the current file and select it.
			parts = os.path.relpath(select, root).split(os.sep)
			for part in parts:
				child = self._child(target, part)
				if child is None:
					break
				target = child
				if self.tree.ItemHasChildren(target):
					self.tree.Expand(target)
		self.tree.SelectItem(target)
		self.tree.EnsureVisible(target)

	def _fill(self, node, folder):
		self.tree.DeleteChildren(node)
		folders, files = _explorer_entries(folder)
		for name in folders:
			child = self.tree.AppendItem(node, name, data=os.path.join(folder, name))
			# A placeholder so the folder can be expanded; filled on demand.
			self.tree.SetItemHasChildren(child, True)
		for name in files:
			self.tree.AppendItem(node, name, data=os.path.join(folder, name))

	def _child(self, node, name):
		child, cookie = self.tree.GetFirstChild(node)
		while child and child.IsOk():
			if self.tree.GetItemText(child).lower() == name.lower():
				return child
			child, cookie = self.tree.GetNextChild(node, cookie)
		return None

	def onExpanding(self, evt):
		node = evt.GetItem()
		path = self.tree.GetItemData(node)
		if path and os.path.isdir(path) and not self.tree.GetChildrenCount(node, False):
			self._fill(node, path)

	def selected_path(self):
		node = self.tree.GetSelection()
		return self.tree.GetItemData(node) if node and node.IsOk() else None

	def _refresh_parent(self, path, select=None):
		node = self.tree.GetSelection()
		target = node if os.path.isdir(path or "") and node and self.tree.IsExpanded(node) else self.tree.GetItemParent(node)
		if not target or not target.IsOk():
			target = self.tree.GetRootItem()
		folder = self.tree.GetItemData(target)
		self._fill(target, folder)
		self.tree.Expand(target)
		if select:
			child = self._child(target, os.path.basename(select))
			if child is not None:
				self.tree.SelectItem(child)
		self.tree.SetFocus()

	def _target_folder(self):
		path = self.selected_path() or self.root
		return path if os.path.isdir(path) else os.path.dirname(path)

	# Actions ---------------------------------------------------------------

	def onActivate(self, evt):
		path = self.selected_path()
		if path and os.path.isdir(path):
			node = self.tree.GetSelection()
			self.tree.Toggle(node)
		else:
			self.onOpen(evt)

	def onTreeKey(self, evt):
		key = evt.GetKeyCode()
		if key == wx.WXK_F2:
			self.onRename(evt)
		elif key == wx.WXK_DELETE:
			self.onDelete(evt)
		elif key == wx.WXK_BACK:
			self.onUp(evt)
		else:
			evt.Skip()

	def onOpen(self, evt):
		path = self.selected_path()
		if path and os.path.isfile(path):
			self.choice = path
			if self.IsModal():
				self.EndModal(wx.ID_OK)
		elif path:
			self.tree.Toggle(self.tree.GetSelection())

	def _ask_name(self, prompt, title, value=""):
		dlg = wx.TextEntryDialog(self, prompt, title, value)
		try:
			if dlg.ShowModal() != wx.ID_OK:
				return None
			name = dlg.GetValue().strip()
		finally:
			dlg.Destroy()
		if not name or any(c in name for c in '<>:"/\\|?*'):
			if name:
				# Translators: a file or folder name has characters Windows does not allow.
				gui.messageBox(_('A name cannot contain any of these characters: < > : " / \\ | ? *'), title, wx.OK | wx.ICON_ERROR, self)
			return None
		return name

	def onNewFile(self, evt):
		folder = self._target_folder()
		# Translators: asks for a new file's name.
		name = self._ask_name(_("Name of the new file in {folder}:").format(folder=os.path.basename(folder) or folder), _("New file"))
		if not name:
			return
		path = os.path.join(folder, name)
		if os.path.exists(path):
			# Translators: a file or folder with that name exists already.
			gui.messageBox(_("{name} already exists.").format(name=name), _("New file"), wx.OK | wx.ICON_ERROR, self)
			return
		try:
			open(path, "x", encoding="utf-8").close()
		except OSError as e:
			gui.messageBox(str(e), _("New file"), wx.OK | wx.ICON_ERROR, self)
			return
		# Open the new file right away, as VS Code does.
		self.choice = path
		self.EndModal(wx.ID_OK)

	def onNewFolder(self, evt):
		folder = self._target_folder()
		# Translators: asks for a new folder's name.
		name = self._ask_name(_("Name of the new folder in {folder}:").format(folder=os.path.basename(folder) or folder), _("New folder"))
		if not name:
			return
		path = os.path.join(folder, name)
		try:
			os.mkdir(path)
		except OSError as e:
			gui.messageBox(str(e), _("New folder"), wx.OK | wx.ICON_ERROR, self)
			return
		# Refill the node of the folder that got the new one, then select it.
		node = self.tree.GetSelection()
		if not node or not node.IsOk() or self.tree.GetItemData(node) != folder:
			node = self.tree.GetItemParent(node) if node and node.IsOk() else None
		if not node or not node.IsOk():
			node = self.tree.GetRootItem()
		self._fill(node, self.tree.GetItemData(node))
		self.tree.Expand(node)
		child = self._child(node, name)
		if child is not None:
			self.tree.SelectItem(child)
		self.tree.SetFocus()

	def onRename(self, evt):
		path = self.selected_path()
		if not path or path == self.root:
			return
		old = os.path.basename(path)
		# Translators: asks for the new name of a file or folder.
		name = self._ask_name(_("New name for {name}:").format(name=old), _("Rename"), old)
		if not name or name == old:
			return
		newPath = os.path.join(os.path.dirname(path), name)
		try:
			os.rename(path, newPath)
		except OSError as e:
			gui.messageBox(str(e), _("Rename"), wx.OK | wx.ICON_ERROR, self)
			return
		self._refresh_parent(None, newPath)

	def onDelete(self, evt):
		path = self.selected_path()
		if not path or path == self.root:
			return
		name = os.path.basename(path)
		recyclable = filepath.can_recycle(path)
		if recyclable:
			# Translators: asks before moving a file or folder to the Recycle Bin.
			question = _("Move {name} to the Recycle Bin?").format(name=name)
		else:
			# Translators: asks before deleting on a drive with no Recycle Bin (network, USB).
			question = _("{name} is on a drive with no Recycle Bin. Delete it permanently? This cannot be undone.").format(name=name)
		if gui.messageBox(
			question,
			# Translators: title of the delete question.
			_("Delete"),
			wx.YES_NO | wx.ICON_QUESTION | (wx.NO_DEFAULT if not recyclable else 0),
			self,
		) != wx.YES:
			return
		if not filepath.remove(path, permanently=not recyclable):
			# Translators: deleting a file or folder failed or was cancelled.
			gui.messageBox(_("{name} was not deleted.").format(name=name), _("Delete"), wx.OK | wx.ICON_ERROR, self)
			return
		self._refresh_parent(None)

	def onCopyPath(self, evt):
		path = self.selected_path()
		if path and api.copyToClip(path):
			# Translators: reported after copying a path.
			ui.message(_("Copied {path}").format(path=path))

	def onUp(self, evt):
		parent = filepath.parent_folder(self.root)
		if parent is None:
			# Translators: the explorer already shows the top of the drive.
			ui.message(_("Top of the drive"))
			return
		self.load(parent, self.root)

	def onChooseFolder(self, evt):
		# Translators: title of the folder picker.
		dlg = wx.DirDialog(self, _("Choose a folder to explore"), self.root)
		try:
			if dlg.ShowModal() == wx.ID_OK:
				self.load(dlg.GetPath())
		finally:
			dlg.Destroy()
		self.tree.SetFocus()

	def onShowInExplorer(self, evt):
		path = self.selected_path() or self.root
		subprocess.Popen(["explorer.exe", "/select,", path])

	def onTerminal(self, evt):
		_open_terminal(self._target_folder())


# --- Files, running and the terminal ------------------------------------------------

#: The runner that executes a Python program in a console window.
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runner", "run_python.py")
#: Paths the user pointed out for editor windows whose file could not be found.
_rememberedPaths = {}
CREATE_NEW_CONSOLE = 0x00000010


def _open_terminal(folder):
	"""A Command Prompt window in folder."""
	try:
		subprocess.Popen(["cmd.exe"], cwd=folder, creationflags=CREATE_NEW_CONSOLE, env=_environment())
	except OSError:
		log.error("Code Compass: could not open a command prompt", exc_info=True)
		# Translators: the command prompt could not be opened.
		ui.message(_("Could not open a command prompt"))


def _environment():
	"""The user's current environment for programs Code Compass starts, not
	the one NVDA started with (see programs.py)."""
	try:
		return programs.fresh_environment()
	except Exception:
		log.debugWarning("Code Compass: reading the environment failed", exc_info=True)
		return None


def _python_command(env=None):
	"""How to start Python 3 (see programs.python_command), or None."""
	try:
		return programs.python_command(env)
	except Exception:
		log.debugWarning("Code Compass: finding Python failed", exc_info=True)
		return None


def _with_file_path(obj, then, optional=False):
	"""Find the full path of the file in obj's window and call then(path).
	When it cannot be found, ask the user and remember the answer for this
	window and file name. With optional, a document that has no file (never
	saved, or a localized "Untitled" title with no extension) calls then(None)."""
	title = _window_title(obj)
	name = filepath.title_file(title)
	if not name:
		if optional:
			then(None)
			return
		# Translators: the document has never been saved, so it has no file.
		ui.message(_("Save the file first"))
		return
	base = os.path.basename(name)
	hwnd = getattr(obj, "windowHandle", None)
	remembered = _rememberedPaths.get(hwnd)
	if remembered and os.path.basename(remembered).lower() != base.lower():
		remembered = None
	try:
		text = _cache.get(obj).text
	except Exception:
		text = None
	try:
		path = filepath.find_file(title, getattr(obj, "processID", None), remembered, text)
	except Exception:
		log.debugWarning("Code Compass: finding the file failed", exc_info=True)
		path = None
	if path:
		then(path)
		return
	if optional and "." not in base:
		# Probably an untitled document in another language ("Unbenannt").
		then(None)
		return

	def onClose(dlg, result):
		if result == wx.ID_OK:
			chosen = dlg.GetPath()
			_rememberedPaths[hwnd] = chosen
			core.callLater(250, then, chosen)

	_run_dialog(
		lambda: wx.FileDialog(
			gui.mainFrame,
			# Translators: asks where the open file is saved, when Code Compass cannot tell.
			_("Where is {name} saved?").format(name=base),
			wildcard="%s|%s" % (base, base),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		),
		onClose,
	)


def _open_in_editor(obj, path):
	"""Open path in the same editor program as obj (a new Notepad window,
	or a new tab in Notepad++)."""
	program = None
	try:
		program = filepath.process_image_path(obj.processID)
	except Exception:
		pass
	try:
		subprocess.Popen([program or "notepad.exe", path])
	except OSError:
		log.error("Code Compass: could not open %s" % path, exc_info=True)
		# Translators: a file could not be opened.
		ui.message(_("Could not open {name}").format(name=os.path.basename(path)))


#: Command palette entries: script name and the keys that run it.
PALETTE = (
	("whereAmI", "NVDA+shift+K W"),
	("whereAmIDetails", "NVDA+shift+K shift+W"),
	("family", "NVDA+shift+K F"),
	("reportLevel", "NVDA+shift+K D"),
	("outline", "control+shift+O"),
	("explorer", "control+shift+E"),
	("nextProblem", "F8"),
	("previousProblem", "shift+F8"),
	("problemsList", "control+shift+M"),
	("checkBrackets", "NVDA+shift+K C"),
	("runFile", "control+F5"),
	("terminal", "control+`"),
	("definition", "F12"),
	("references", "shift+F12"),
	("rename", "F2"),
	("complete", "control+space"),
	("parameterHint", "control+shift+space"),
	("toggleComment", "control+/"),
	("deleteLine", "control+shift+K"),
	("moveLineUp", "control+shift+up arrow"),
	("moveLineDown", "control+shift+down arrow"),
	("duplicateLine", "control+shift+D"),
	("selectBlock", "NVDA+shift+K S"),
	("matchBracket", "NVDA+shift+K M"),
	("blockStart", "alt+home"),
	("blockEnd", "alt+end"),
	("nextSameLevel", "alt+down arrow"),
	("previousSameLevel", "alt+up arrow"),
	("nextDeclaration", "alt+page down"),
	("previousDeclaration", "alt+page up"),
	("parentDeclaration", "alt+left arrow"),
	("childDeclaration", "alt+right arrow"),
	("todoList", "NVDA+shift+K shift+T"),
	("toggleBookmark", "control+alt+K"),
	("nextBookmark", "control+alt+L"),
	("previousBookmark", "control+alt+J"),
	("bookmarksList", "NVDA+shift+K shift+B"),
	("clearBookmarks", ""),
	("goBack", "control+alt+backspace"),
	("goForward", "control+alt+shift+backspace"),
	("reloadFile", "NVDA+shift+K R"),
	("saveSnippet", "NVDA+shift+K A"),
	("insertSnippet", "NVDA+shift+K I"),
	("cycleLevelReport", "NVDA+shift+K T"),
	("layerHelp", "NVDA+shift+K H"),
)


# --- Command layer ------------------------------------------------------------

#: Keys available after the layer gesture: identifier -> script name.
LAYER_GESTURES = {
	"kb:w": "whereAmI",
	"kb:shift+w": "whereAmIDetails",
	"kb:d": "reportLevel",
	"kb:m": "matchBracket",
	"kb:b": "blockStart",
	"kb:e": "blockEnd",
	"kb:s": "selectBlock",
	"kb:n": "nextDeclaration",
	"kb:p": "previousDeclaration",
	"kb:f": "family",
	"kb:o": "outline",
	"kb:shift+t": "todoList",
	"kb:shift+b": "bookmarksList",
	"kb:backspace": "goBack",
	"kb:r": "reloadFile",
	"kb:shift+backspace": "goForward",
	"kb:shift+c": "problemsList",
	"kb:shift+p": "palette",
	"kb:shift+e": "explorer",
	"kb:a": "saveSnippet",
	"kb:i": "insertSnippet",
	"kb:c": "checkBrackets",
	"kb:t": "cycleLevelReport",
	"kb:h": "layerHelp",
}


def _snippets_folder():
	return os.path.join(globalVars.appArgs.configPath, "codeCompass", "snippets")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: input gestures category for this add-on.
	scriptCategory = _("Code Compass")

	def __init__(self):
		global _plugin
		super(GlobalPlugin, self).__init__()
		self._layerActive = False
		#: Ctrl+Space state: the suggestions being cycled through.
		self._completion = None
		_plugin = self
		if globalVars.appArgs.secure:
			return
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(CodeCompassSettingsPanel)

	def terminate(self):
		global _plugin
		_plugin = None
		_save_bookmarks()
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(CodeCompassSettingsPanel)
		except (AttributeError, ValueError):
			pass
		super(GlobalPlugin, self).terminate()

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if obj.role != controlTypes.Role.EDITABLETEXT:
			return
		if not any(issubclass(cls, EditableText) for cls in clsList):
			return
		appModule = obj.appModule
		if not appModule or appModule.appName.lower() not in _enabled_apps():
			return
		if edit_control.is_single_line(getattr(obj, "windowClassName", "") or "", getattr(obj, "windowHandle", None)):
			# A one-line field in the editor's dialogs (Save As, Find): alt+arrows
			# and the other quick keys belong to the dialog there.
			return
		clsList.insert(0, CodeEditor)

	# Layer ------------------------------------------------------------------

	def getScript(self, gesture):
		if not self._layerActive:
			return super(GlobalPlugin, self).getScript(gesture)
		if getattr(gesture, "isModifier", False):
			# Shift pressed on its way to shift+W: keep the layer open.
			return None
		# One command per layer activation.
		self._layerActive = False
		ids = gesture.normalizedIdentifiers
		for ident in ids:
			name = LAYER_GESTURES.get(ident)
			if name:
				return getattr(self, "script_" + name)
		if "kb:escape" in ids:
			return self.script_layerCancel
		return self.script_layerError

	@script(
		# Translators: describes the command that starts the command layer.
		description=_("Code Compass commands: press a letter next, H lists them"),
		gesture="kb:NVDA+shift+k",
	)
	def script_layer(self, gesture):
		self._layerActive = True
		tones.beep(880, 30)

	def script_layerCancel(self, gesture):
		tones.beep(440, 30)

	def script_layerError(self, gesture):
		tones.beep(150, 100)

	# Helpers ------------------------------------------------------------------

	def _editor(self):
		"""Focused editable text, or None after telling the user."""
		obj = api.getFocusObject()
		if isinstance(obj, EditableText):
			return obj
		# Translators: reported when a command needs a text editor.
		ui.message(_("Not in a text editor"))
		return None

	def _doc(self, obj):
		a = _cache.get(obj)
		return a, _caret_offset(obj, a.text)

	def _move_caret(self, obj, a, offset, remember=True):
		"""Move the caret to offset and read the line. With remember, a jump
		to another line can be undone with control+alt+backspace; steps such
		as alt+down arrow pass remember=False."""
		if remember:
			try:
				here = _caret_offset(obj, a.text)
				if a.line_index(here) != a.line_index(offset):
					_remember_place(obj, a, here)
			except Exception:
				log.debugWarning("Code Compass: remembering the place failed", exc_info=True)
		info = _range_info(obj, a, offset, offset)
		info.updateCaret()
		_forget_selection_change(obj)
		li = a.line_index(offset)
		_announce_line_level(obj, a, li)
		line = info.copy()
		line.expand(textInfos.UNIT_LINE)
		speech.speakTextInfo(line, unit=textInfos.UNIT_LINE, reason=controlTypes.OutputReason.CARET)
		closer = _line_closer_message(a, li)
		if closer:
			speech.speak([closer])
		braille.handler.handleCaretMove(obj)

	# Where am I -----------------------------------------------------------------

	@script(
		# Translators: describes the "where am I" command.
		description=_("Reports the scopes around the caret, outermost first"),
	)
	def script_whereAmI(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		items = a.scopes(off)
		if not items:
			# Translators: the caret is not inside any block.
			ui.message(_("Top level"))
			return
		# The innermost function or class gets its length: "func load(), 42 lines".
		# Its scope is the first one (outermost first) inside its lines: its body,
		# with the brace on the header line, the next line or after wrapped
		# parameters.
		chain = a.declaration_chain(off)
		if chain:
			cur = chain[-1]
			for i, (li, text) in enumerate(items):
				if cur.line <= li <= cur.endLine:
					items[i] = (li, text + ", " + _line_count(cur))
					break
		ui.message("; ".join(text for _li, text in items))

	@script(
		# Translators: describes the detailed "where am I" command.
		description=_("Shows the scopes around the caret, with line numbers, in a reviewable window"),
	)
	def script_whereAmIDetails(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		items = a.scopes(off)
		if not items:
			ui.message(_("Top level"))
			return
		# Translators: one line in the detailed scope list.
		lines = [_("Line {line}: {text}").format(line=li + 1, text=text) for li, text in items]
		# Translators: title of the detailed scope window.
		ui.browseableMessage("\n".join(lines), title=_("Where am I"))

	@script(
		# Translators: describes the report level command.
		description=_("Reports the bracket level at the caret and which brackets are open"),
	)
	def script_reportLevel(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		stack = a.enclosing(off)
		if not stack:
			ui.message(_("level {level}").format(level=0))
			return
		names = ", ".join(analyzer.bracket_name(b.char) for b in stack)
		# Translators: bracket level and the open brackets, e.g. "level 2: brace, paren".
		ui.message(_("level {level}: {names}").format(level=len(stack), names=names))

	# Moving -----------------------------------------------------------------------

	@script(
		# Translators: describes the match bracket command.
		description=_("Moves to the bracket matching the one at or just before the caret"),
	)
	def script_matchBracket(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		b = a.bracket_near(off)
		if b is None:
			# Translators: no bracket at the caret.
			ui.message(_("No bracket here"))
			return
		if b.partner is None:
			# Translators: the bracket at the caret has no partner.
			ui.message(_("Unmatched bracket"))
			return
		self._move_caret(obj, a, b.partner)

	@script(
		# Translators: describes the block start command.
		description=_("Moves to the start of the block around the caret; repeat to go outward"),
	)
	def script_blockStart(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		blocks = a.blocks(off)
		if not blocks:
			ui.message(_("Top level"))
			return
		self._move_caret(obj, a, blocks[-1].start)

	@script(
		# Translators: describes the block end command.
		description=_("Moves to the end of the block around the caret; repeat to go outward"),
	)
	def script_blockEnd(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		blocks = a.blocks(off)
		# Already at a block's end: go to the next one out.
		while blocks and blocks[-1].ends_at(a, off):
			blocks.pop()
		if not blocks:
			ui.message(_("Top level"))
			return
		if blocks[-1].end is None:
			# Translators: the block around the caret never closes.
			ui.message(_("This block is never closed"))
			return
		self._move_caret(obj, a, blocks[-1].end)

	def _same_level(self, step):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		target = a.same_level_line(a.line_index(off), step)
		if target is None:
			if step > 0:
				# Translators: no more lines at this level before the block ends.
				ui.message(_("End of block"))
			else:
				# Translators: no earlier lines at this level in the block.
				ui.message(_("Start of block"))
			return
		self._move_caret(obj, a, a.first_char(target), remember=False)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the next line at the same level, skipping nested blocks"),
	)
	def script_nextSameLevel(self, gesture):
		self._same_level(1)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the previous line at the same level, skipping nested blocks"),
	)
	def script_previousSameLevel(self, gesture):
		self._same_level(-1)

	def _declaration(self, step):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		item = a.declaration_near(a.line_index(off), step)
		if item is None:
			if step > 0:
				# Translators: no function or class after the caret.
				ui.message(_("No next function or class"))
			else:
				# Translators: no function or class before the caret.
				ui.message(_("No previous function or class"))
			return
		self._move_caret(obj, a, a.first_char(item.line), remember=False)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the next function or class"),
	)
	def script_nextDeclaration(self, gesture):
		self._declaration(1)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the previous function or class"),
	)
	def script_previousDeclaration(self, gesture):
		self._declaration(-1)

	@script(
		# Translators: describes the select block command.
		description=_("Selects the whole lines of the block around the caret; repeat to select the next block out"),
	)
	def script_selectBlock(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a = _cache.get(obj)
		sel = _selection_offsets(obj, a.text)
		for block in reversed(a.blocks(sel[0])):
			rng = a.block_range(block)
			if rng is None or rng == sel or rng[0] > sel[0] or rng[1] < sel[1]:
				continue
			info = _range_info(obj, a, rng[0], rng[1])
			info.updateSelection()
			_forget_selection_change(obj)
			first = a.line_index(rng[0])
			count = a.line_index(max(rng[0], rng[1] - 1)) - first + 1
			header = analyzer.shorten(a.line_text(first).strip())
			if count == 1:
				# Translators: reported after selecting a one-line block.
				ui.message(_("Selected 1 line: {header}").format(header=header))
			else:
				# Translators: reported after selecting a block, e.g. "Selected 5 lines: if x {".
				ui.message(_("Selected {count} lines: {header}").format(count=count, header=header))
			return
		# Translators: there is no (closed) block around the caret to select.
		ui.message(_("No block to select"))

	# Declarations ---------------------------------------------------------------------

	@script(
		# Translators: describes the family command.
		description=_("Reports the function or class at the caret, what it is inside, and what it contains"),
	)
	def script_family(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		chain = a.declaration_chain(off)
		if not chain:
			# Translators: the caret is not in any function or class.
			ui.message(_("Not inside a function or class"))
			return
		cur = chain[-1]
		# Translators: a declaration, e.g. "function hello".
		text = _("{kind} {name}").format(kind=_(cur.kind), name=cur.name) + ", " + _line_count(cur)
		ancestors = cur.ancestors()
		for p in ancestors:
			# Translators: the declaration around the previous one, e.g. ", in class Greeter".
			text += _(", in {kind} {name}").format(kind=_(p.kind), name=p.name)
		if not ancestors:
			# Translators: the declaration is not inside another one.
			text += _(", top level")
		if cur.children:
			names = ", ".join(c.name for c in cur.children[:10])
			# Translators: the declarations directly inside, e.g. "Contains 2: greet, wave".
			text += ". " + _("Contains {count}: {names}").format(count=len(cur.children), names=names)
		ui.message(text)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the function or class around the caret, or to its parent when already on it"),
	)
	def script_parentDeclaration(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		chain = a.declaration_chain(off)
		if not chain:
			ui.message(_("Not inside a function or class"))
			return
		cur = chain[-1]
		target = cur.parentItem if cur.line == a.line_index(off) else cur
		if target is None:
			ui.message(_("Top level"))
			return
		self._move_caret(obj, a, a.first_char(target.line), remember=False)

	@script(
		# Translators: describes a navigation command.
		description=_("Moves to the first function or class inside the one at the caret"),
	)
	def script_childDeclaration(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		chain = a.declaration_chain(off)
		if not chain:
			ui.message(_("Not inside a function or class"))
			return
		cur = chain[-1]
		if not cur.children:
			# Translators: the declaration has no functions or classes inside.
			ui.message(_("Nothing declared inside {name}").format(name=cur.name))
			return
		self._move_caret(obj, a, a.first_char(cur.children[0].line), remember=False)

	@script(
		# Translators: describes the outline command.
		description=_("Shows functions and classes as a tree; Enter moves to the selected one"),
	)
	def script_outline(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		items = a.outline()
		if not items:
			# Translators: no functions or classes were found.
			ui.message(_("No functions or classes found"))
			return
		chain = a.declaration_chain(off)
		if chain:
			selection = items.index(chain[-1])
		else:
			caretLine = a.line_index(off)
			selection = 0
			for i, item in enumerate(items):
				if item.line <= caretLine:
					selection = i
		lines = [item.line for item in items]

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None:
				# Give focus time to return to the editor before moving.
				core.callLater(250, self._jump_to_line, lines[dlg.choice])

		_run_dialog(lambda: OutlineDialog(gui.mainFrame, items, selection), onClose)

	def _jump_to_line(self, li):
		obj = api.getFocusObject()
		if not isinstance(obj, EditableText):
			return
		a = _cache.get(obj)
		# Land on the first non-blank character, like Home in most editors.
		self._move_caret(obj, a, a.first_char(min(li, a.lineCount - 1)))

	# Snippets ---------------------------------------------------------------------------

	@script(
		# Translators: describes the save snippet command.
		description=_("Saves the selected code as a snippet, or the function or class at the caret when nothing is selected"),
	)
	def script_saveSnippet(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a = _cache.get(obj)
		start, end = _selection_offsets(obj, a.text)
		suggested = ""
		if end > start:
			lineStart = a.lineStarts[a.line_index(start)]
			before = a.text[lineStart:start]
			text = snippets.dedent(a.text[start:end], before if not before.strip() else "")
			first, last = a.line_index(start), a.line_index(max(start, end - 1))
			inside = [item for item in a.outline() if first <= item.line <= last]
			if inside:
				suggested = inside[0].name
		else:
			chain = a.declaration_chain(_caret_offset(obj, a.text))
			if not chain:
				# Translators: nothing to save as a snippet.
				ui.message(_("Select some code first, or put the caret inside a function or class"))
				return
			start, end = a.declaration_range(chain[-1])
			text = snippets.dedent(a.text[start:end])
			suggested = chain[-1].name
		ext = analyzer.extension_from_title(_window_title(obj)) or "txt"
		folder = _snippets_folder()

		def onClose(dlg, result):
			if result != wx.ID_OK:
				return
			name = snippets.safe_name(dlg.GetValue())
			if not name:
				# Translators: the snippet name was empty.
				core.callLater(100, ui.message, _("Snippet not saved: the name is empty"))
				return
			path = snippets.snippet_path(folder, name, ext)
			if os.path.exists(path) and gui.messageBox(
				# Translators: asks before replacing a snippet with the same name.
				_("A snippet named {name} already exists. Replace it?").format(name=name),
				# Translators: title of the replace snippet question.
				_("Save snippet"),
				wx.YES_NO | wx.ICON_QUESTION,
				gui.mainFrame,
			) != wx.YES:
				return
			snippets.save_snippet(folder, name, ext, text)
			# Translators: reported after saving a snippet.
			core.callLater(100, ui.message, _("Snippet saved: {name}").format(name=name))

		_run_dialog(
			lambda: wx.TextEntryDialog(
				gui.mainFrame,
				# Translators: prompt for the name of a new snippet.
				_("Name for the {ext} snippet:").format(ext=ext),
				# Translators: title of the save snippet dialog.
				_("Save snippet"),
				suggested,
			),
			onClose,
		)

	@script(
		# Translators: describes the insert snippet command.
		description=_("Lists saved snippets; Enter inserts the selected one at the caret"),
	)
	def script_insertSnippet(self, gesture):
		obj = self._editor()
		if not obj:
			return
		folder = _snippets_folder()
		ext = analyzer.extension_from_title(_window_title(obj))
		if not snippets.list_snippets(folder):
			# Translators: there are no snippets yet.
			ui.message(_("No snippets yet. Select code, then press NVDA+shift+K and A to save one"))
			return

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None:
				core.callLater(250, self._insert_snippet, dlg.choice)

		_run_dialog(lambda: SnippetsDialog(gui.mainFrame, folder, ext), onClose)

	def _insert_snippet(self, snip):
		obj = api.getFocusObject()
		if not isinstance(obj, EditableText):
			return
		try:
			code = snip.read()
		except (OSError, ValueError):
			log.error("Code Compass: could not read snippet", exc_info=True)
			# Translators: a snippet file could not be read.
			ui.message(_("Could not read snippet {name}").format(name=snip.name))
			return
		a = _cache.get(obj)
		caret = _caret_offset(obj, a.text)
		prefix = a.text[a.lineStarts[a.line_index(caret)]:caret]
		newline = "\n" if ("\n" in a.text and "\r\n" not in a.text) else "\r\n"
		text = snippets.prepare_insert(code, prefix, newline)
		if _replace_selection_directly(obj, text):
			_forget_selection_change(obj)
			# Translators: reported after inserting a snippet.
			ui.message(_("Inserted snippet {name}").format(name=snip.name))
			return
		# Other editors: paste through the clipboard. Only text can be put back
		# afterwards; files or images copied before are replaced.
		try:
			old = api.getClipData()
		except Exception:
			old = None
		if not api.copyToClip(text):
			# Translators: the clipboard could not be used to insert a snippet.
			ui.message(_("Could not insert the snippet"))
			return
		keyboardHandler.KeyboardInputGesture.fromName("control+v").send()
		if old:
			# Put the user's text back once the editor has pasted.
			core.callLater(800, api.copyToClip, old)
			ui.message(_("Inserted snippet {name}").format(name=snip.name))
		else:
			# Translators: reported after inserting a snippet through the clipboard, which held no text to put back.
			ui.message(_("Inserted snippet {name}. The clipboard now holds the snippet").format(name=snip.name))

	# Checks and settings --------------------------------------------------------------

	@script(
		# Translators: describes the check brackets command.
		description=_("Checks the whole file for unclosed or extra brackets"),
	)
	def script_checkBrackets(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, _off = self._doc(obj)
		found = a.problems()
		if not found:
			# Translators: no bracket problems in the file.
			ui.message(_("All brackets balanced"))
			return
		ui.message(_problems_message([problems.Problem(li, 0, msg, "bracket") for li, msg in found]))

	@script(
		# Translators: describes the command that changes how levels are reported.
		description=_("Cycles how the bracket level is reported when moving by line: off, tone, speech, both"),
	)
	def script_cycleLevelReport(self, gesture):
		modes = _level_modes()
		values = [v for v, _label in modes]
		current = _conf()["levelReport"]
		nxt = values[(values.index(current) + 1) % len(values)] if current in values else "tone"
		_conf()["levelReport"] = nxt
		# Translators: announced after changing the level report mode.
		ui.message(_("Level report: {mode}").format(mode=dict(modes)[nxt]))

	# Editing (classic Notepad) ----------------------------------------------------------

	def _writable_editor(self):
		"""Focused editor if Code Compass can change its text, else None after
		saying why."""
		obj = self._editor()
		if not obj:
			return None
		if not _writable_notepad(obj):
			# Translators: a command that changes text only works in classic Notepad.
			ui.message(_("This command changes text only in Windows 10 Notepad"))
			return None
		return obj

	def _shift_lines(self, obj, outward):
		"""Tab and shift+Tab: indent or outdent the selected lines, or (shift+Tab
		only) the caret's line. Returns False to let a plain Tab through."""
		try:
			a = _cache.get(obj)
			start, end = _selection_offsets(obj, a.text)
		except Exception:
			return False
		first, last = editing.line_block(a, start, end)
		# A selection that crosses a line break is a block of lines, even one
		# whole line selected with shift+down arrow.
		multi = a.line_index(end) > a.line_index(start)
		if not multi and not outward:
			return False
		unit = editing.indent_unit(a.text)
		newText = editing.shift_lines(a, first, last, unit, outward)
		rangeStart, rangeEnd = editing.lines_range(a, first, last)
		if newText == a.text[rangeStart:rangeEnd]:
			# Translators: there was no indentation to remove.
			ui.message(_("No indentation to remove"))
			return True
		if multi:
			ok = _apply_edit(obj, a, rangeStart, rangeEnd, newText, rangeStart, max(rangeStart, end + len(newText) - (rangeEnd - rangeStart)))
		else:
			caret = max(rangeStart, end - (rangeEnd - rangeStart - len(newText)))
			ok = _apply_edit(obj, a, rangeStart, rangeEnd, newText, caret)
		if not ok:
			return False
		count = last - first + 1
		if outward:
			# Translators: reported after outdenting lines.
			ui.message(_("Outdented {count} lines").format(count=count) if count > 1 else _("Outdented"))
		else:
			# Translators: reported after indenting lines.
			ui.message(_("Indented {count} lines").format(count=count) if count > 1 else _("Indented"))
		return True

	@script(
		# Translators: describes the toggle comment command.
		description=_("Comments or uncomments the selected lines, or the caret's line"),
	)
	def script_toggleComment(self, gesture):
		obj = self._writable_editor()
		if not obj:
			return
		a = _cache.get(obj)
		start, end = _selection_offsets(obj, a.text)
		first, last = editing.line_block(a, start, end)
		result = editing.toggle_comment(a, first, last)
		if result is None:
			# Translators: the line is blank or the language has no comments.
			ui.message(_("Nothing to comment"))
			return
		newText, commented = result
		rangeStart, rangeEnd = editing.lines_range(a, first, last)
		if last > first:
			_apply_edit(obj, a, rangeStart, rangeEnd, newText, rangeStart, rangeStart + len(newText))
		else:
			# The caret stays put before the change and moves with the text after it.
			old = a.text[rangeStart:rangeEnd]
			same = len(os.path.commonprefix([old, newText]))
			column = end - rangeStart
			if column > same:
				column = max(same, column + len(newText) - len(old))
			_apply_edit(obj, a, rangeStart, rangeEnd, newText, rangeStart + min(column, len(newText)))
		count = last - first + 1
		if commented:
			# Translators: reported after commenting lines.
			ui.message(_("{count} lines commented").format(count=count) if count > 1 else _("Commented"))
		else:
			# Translators: reported after uncommenting lines.
			ui.message(_("{count} lines uncommented").format(count=count) if count > 1 else _("Uncommented"))

	@script(
		# Translators: describes the completion command.
		description=_("Completes the word at the caret with names from the file; press again for the next suggestion"),
	)
	def script_complete(self, gesture):
		obj = self._writable_editor()
		if not obj:
			return
		a = _cache.get(obj)
		caret = _caret_offset(obj, a.text)
		state = self._completion
		if (
			state and state["hwnd"] == obj.windowHandle
			and state["text"] == a.text and state["caret"] == caret
		):
			index = (state["index"] + 1) % (len(state["words"]) + 1)
		else:
			start, prefix, words = editing.completions(a, caret)
			if not words:
				self._completion = None
				# Translators: no completion was found for the word at the caret.
				ui.message(_("No suggestions"))
				return
			state = {"hwnd": obj.windowHandle, "start": start, "prefix": prefix, "words": words}
			index = 0
		words = state["words"]
		start = state["start"]
		# After the last suggestion comes back what was typed.
		word = state["prefix"] if index == len(words) else words[index]
		if not _apply_edit(obj, a, start, caret, word, start + len(word)):
			return
		state.update(index=index, text=a.text[:start] + word + a.text[caret:], caret=start + len(word))
		self._completion = state
		if index == len(words):
			# Translators: completion went back to the letters the user typed.
			ui.message(_("{word}, as typed").format(word=word) if word else _("as typed"))
		else:
			# Translators: a completion and its place, e.g. "currentUser, 1 of 3".
			ui.message(_("{word}, {index} of {count}").format(word=word, index=index + 1, count=len(words)))

	@script(
		# Translators: describes the parameter hint command.
		description=_("Reports the parameters of the function whose parentheses hold the caret"),
	)
	def script_parameterHint(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		hint = editing.parameter_hint(a, off)
		if hint is None:
			name = editing.called_name(a, off)
			if name:
				ui.message(_("{name} is not declared in this file").format(name=name))
			else:
				# Translators: control+shift+space was pressed outside a function call.
				ui.message(_("Put the caret inside the parentheses of a call"))
			return
		signature, number = hint
		# Translators: a function's signature and the argument the caret is on.
		ui.message(_("{signature}, argument {number}").format(signature=signature, number=number))

	def _line_operation(self, compute, message):
		obj = self._writable_editor()
		if not obj:
			return
		a = _cache.get(obj)
		start, end = _selection_offsets(obj, a.text)
		first, last = editing.line_block(a, start, end)
		change = compute(a, first, last, start, end)
		if change is None:
			# Translators: a line cannot move further.
			ui.message(_("Cannot move further"))
			return
		rangeStart, rangeEnd, newText, selStart, selEnd = change
		if _apply_edit(obj, a, rangeStart, rangeEnd, newText, selStart, selEnd):
			if message:
				speech.speak([message])
			_speak_caret_line(obj)

	@script(
		# Translators: describes the delete line command.
		description=_("Deletes the selected lines, or the caret's line"),
	)
	def script_deleteLine(self, gesture):
		def compute(a, first, last, start, end):
			rangeStart, rangeEnd = editing.full_lines(a, first, last)
			return rangeStart, rangeEnd, "", rangeStart, rangeStart

		# Translators: reported after deleting lines; the new current line follows.
		self._line_operation(compute, _("Deleted"))

	def _move(self, step):
		def compute(a, first, last, start, end):
			moved = editing.move_lines(a, first, last, step)
			if moved is None:
				return None
			rangeStart, rangeEnd, newText, newFirst = moved
			column = start - a.lineStarts[first]
			nl = editing.newline_style(a.text)
			lines = newText.split(nl)
			# Where the moved lines now start inside the changed region.
			offsetInRegion = 0 if step < 0 else len(lines[0]) + len(nl)
			newStart = rangeStart + offsetInRegion
			if end > start:
				span = end - a.lineStarts[first]
				return rangeStart, rangeEnd, newText, newStart + column, newStart + span
			return rangeStart, rangeEnd, newText, newStart + column, newStart + column

		self._line_operation(compute, None)

	@script(
		# Translators: describes the move line command.
		description=_("Moves the selected lines, or the caret's line, up"),
	)
	def script_moveLineUp(self, gesture):
		self._move(-1)

	@script(
		# Translators: describes the move line command.
		description=_("Moves the selected lines, or the caret's line, down"),
	)
	def script_moveLineDown(self, gesture):
		self._move(1)

	@script(
		# Translators: describes the duplicate line command.
		description=_("Copies the selected lines, or the caret's line, below themselves"),
	)
	def script_duplicateLine(self, gesture):
		def compute(a, first, last, start, end):
			insertAt, text = editing.duplicate_lines(a, first, last)
			copyStart = insertAt + len(editing.newline_style(a.text))
			column = start - a.lineStarts[first]
			return insertAt, insertAt, text, copyStart + column, copyStart + column

		# Translators: reported after duplicating lines; the copy's line follows.
		self._line_operation(compute, _("Duplicated"))

	# Names: definition, references, rename ------------------------------------------------

	def _name_at_caret(self, obj, a, off):
		found = editing.identifier_at(a, off)
		if found is None:
			# Translators: there is no name (identifier) at the caret.
			ui.message(_("No name at the caret"))
		return found

	@script(
		# Translators: describes the go to definition command.
		description=_("Moves to the declaration of the function or class named at the caret"),
	)
	def script_definition(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		found = self._name_at_caret(obj, a, off)
		if not found:
			return
		name = found[2]
		item = editing.definition_of(a, name)
		if item is None:
			# Translators: the name is not declared in this file.
			ui.message(_("{name} is not declared in this file").format(name=name))
			return
		if item.line == a.line_index(off):
			# Translators: the caret is already on the declaration.
			ui.message(_("This is where {name} is declared").format(name=name))
			return
		lineStart = a.lineStarts[item.line]
		column = a.line_code(item.line).find(name)
		self._move_caret(obj, a, lineStart + column if column >= 0 else a.first_char(item.line))

	@script(
		# Translators: describes the find references command.
		description=_("Lists every line that uses the name at the caret; Enter moves there"),
	)
	def script_references(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		found = self._name_at_caret(obj, a, off)
		if not found:
			return
		name = found[2]
		spots = editing.occurrences(a, name)
		labels = [
			# Translators: one use of a name, e.g. "line 12: total = add(1)".
			_("line {line}: {text}").format(line=a.line_index(s) + 1, text=analyzer.shorten(a.line_text(a.line_index(s)).strip()))
			for s in spots
		]
		selection = next((i for i, s in enumerate(spots) if s == found[0]), 0)

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None:
				core.callLater(250, self._jump_to_offset, spots[dlg.choice], a.text)

		_run_dialog(
			# Translators: title of the references list, e.g. "Uses of total: 3".
			lambda: ListDialog(gui.mainFrame, _("Uses of {name}: {count}").format(name=name, count=len(spots)), _("&Uses:"), labels, selection),
			onClose,
		)

	def _jump_to_offset(self, offset, expectedText):
		obj = api.getFocusObject()
		if not isinstance(obj, EditableText):
			return
		a = _cache.get(obj)
		if a.text != expectedText:
			offset = min(offset, len(a.text))
		self._move_caret(obj, a, offset)

	@script(
		# Translators: describes the rename command.
		description=_("Renames the name at the caret everywhere in the file, outside comments and strings"),
	)
	def script_rename(self, gesture):
		obj = self._writable_editor()
		if not obj:
			return
		a, off = self._doc(obj)
		found = self._name_at_caret(obj, a, off)
		if not found:
			return
		name = found[2]
		count = len(editing.occurrences(a, name))

		def onClose(dlg, result):
			if result != wx.ID_OK:
				return
			newName = dlg.GetValue().strip()
			if not newName or newName == name:
				return
			if not re.match(r"^(?:[^\W\d]|\$)[\w$]*$", newName):
				# Translators: the new name is not a valid identifier.
				core.callLater(100, ui.message, _("{name} is not a valid name").format(name=newName))
				return
			core.callLater(250, self._apply_rename, obj, a.text, name, newName)

		_run_dialog(
			lambda: wx.TextEntryDialog(
				gui.mainFrame,
				# Translators: asks for a new name, e.g. "Rename total (3 places) to:".
				_("Rename {name} ({count} places) to:").format(name=name, count=count),
				# Translators: title of the rename dialog.
				_("Rename"),
				name,
			),
			onClose,
		)

	def _apply_rename(self, obj, expectedText, name, newName):
		a = _cache.get(obj)
		if a.text != expectedText:
			# Translators: the file changed while the rename dialog was open.
			ui.message(_("The file changed; rename again"))
			return
		caret = _caret_offset(obj, a.text)
		newText, count = editing.renamed_text(a, name, newName)
		delta = len(newName) - len(name)
		shift = 0
		newCaret = None
		for spot in editing.occurrences(a, name):
			if spot + len(name) <= caret:
				shift += delta
			elif spot <= caret:
				# The caret is inside this occurrence: keep it inside the new name.
				newCaret = spot + shift + min(caret - spot, len(newName))
				break
		if newCaret is None:
			newCaret = caret + shift
		if _apply_edit(obj, a, 0, len(a.text), newText, newCaret):
			# Translators: reported after renaming; control+Z undoes it.
			_play("codeActionApplied")
			ui.message(_("Renamed {count} places to {name}. Control+Z undoes it").format(count=count, name=newName))

	# Problems -------------------------------------------------------------------------------

	def _problem_nav(self, step):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		found = _problems(obj, a)
		if not found:
			# Translators: no problems were found in the file.
			ui.message(_("No problems found"))
			return
		hwnd = getattr(obj, "windowHandle", None)
		run = _run_error_for(hwnd, _window_title(obj))
		if hwnd in _runErrorPending and run is not None and run in found:
			# Right after a run, F8 goes to the error the program stopped on.
			_runErrorPending.discard(hwnd)
			target = run
		else:
			target = problems.next_problem(found, a.line_index(off), step)
		speech.speak([_problem_label(target)])
		lineStart, lineEnd = a.line_bounds(target.line)
		self._move_caret(obj, a, min(lineStart + target.column, lineEnd))

	@script(
		# Translators: describes the next problem command.
		description=_("Moves to the next problem: a syntax error, an unbalanced bracket or the last run's error"),
	)
	def script_nextProblem(self, gesture):
		self._problem_nav(1)

	@script(
		# Translators: describes the previous problem command.
		description=_("Moves to the previous problem"),
	)
	def script_previousProblem(self, gesture):
		self._problem_nav(-1)

	@script(
		# Translators: describes the problems list command.
		description=_("Lists every problem in the file; Enter moves there"),
	)
	def script_problemsList(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		found = _problems(obj, a)
		if not found:
			ui.message(_("No problems found"))
			return
		text = a.text

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None:
				p = found[dlg.choice]
				core.callLater(250, self._jump_to_offset, a.lineStarts[p.line] + p.column, text)

		_run_dialog(
			# Translators: title of the problems list, e.g. "Problems: 2".
			lambda: ListDialog(gui.mainFrame, _("Problems: {count}").format(count=len(found)), _("&Problems:"), [_problem_label(p) for p in found]),
			onClose,
		)

	# Reload ---------------------------------------------------------------------

	@script(
		# Translators: describes the reload command.
		description=_("Reloads the file from disk, after asking when it has unsaved changes"),
	)
	def script_reloadFile(self, gesture):
		obj = self._editor()
		if not obj:
			return
		if getattr(getattr(obj, "appModule", None), "appName", None) == "notepad++":
			# Translators: Notepad++ has its own reload command.
			ui.message(_("Notepad++ reloads files itself: File, Reload from Disk"))
			return
		if not _writable_notepad(obj):
			ui.message(_("This command changes text only in Windows 10 Notepad"))
			return
		path = _disk_path(obj)
		if not path:
			if not filepath.title_file(_window_title(obj)):
				ui.message(_("Save the file first"))
			else:
				# Translators: the file shown in the editor could not be found on disk.
				ui.message(_("Could not find the file on disk"))
			return
		disk = filepath.read_text(path)
		name = os.path.basename(path)
		if disk is None:
			ui.message(_("Could not open {name}").format(name=name))
			return
		a = _cache.get(obj)
		if filepath.same_text(disk, a.text):
			_remember_disk(obj, path, disk)
			# Translators: the editor already shows what the file on disk holds.
			ui.message(_("{name} is the same as on disk").format(name=name))
			return

		def reload():
			# Read again: the file may have changed while the question was open.
			stamp = _stamp(path)
			latest = filepath.read_text(path)
			if latest is None:
				ui.message(_("Could not open {name}").format(name=name))
				return
			current = _cache.get(obj)
			changes = _reload(obj, current, path, latest, stamp)
			if changes is None:
				ui.message(_("Could not reload {name}").format(name=name))
				return
			# Translators: reported after reloading, e.g. "Reloaded latihan.py: 3 lines added".
			ui.message(_("Reloaded {name}: {changes}").format(name=name, changes=changes))

		if not _window_title(obj).startswith("*"):
			reload()
			return

		def onClose(dlg, result):
			if result == wx.ID_YES:
				core.callLater(250, reload)

		_run_dialog(
			lambda: wx.MessageDialog(
				gui.mainFrame,
				# Translators: asks before reloading a file with unsaved changes.
				_("{name} has changes you have not saved. Reload it from disk anyway? Control+Z undoes the reload.").format(name=name),
				# Translators: title of the reload question.
				_("Reload"),
				wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
			),
			onClose,
		)

	# Bookmarks ---------------------------------------------------------------------

	@script(
		# Translators: describes the toggle bookmark command.
		description=_("Adds a bookmark on the caret's line, or removes the one there"),
	)
	def script_toggleBookmark(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		key, marks = _bookmarks_for(obj, a, create=True)
		li = a.line_index(off)
		added = bookmarks.toggle(marks, li, a.line_text(li))
		_bookmark_store().touch(key)
		_save_bookmarks()
		if added:
			# Translators: a bookmark was added, e.g. "Bookmark added, line 12".
			ui.message(_("Bookmark added, line {line}").format(line=li + 1))
		else:
			# Translators: a bookmark was removed, e.g. "Bookmark removed, line 12".
			ui.message(_("Bookmark removed, line {line}").format(line=li + 1))

	# Going back -------------------------------------------------------------------

	def _history_nav(self, step):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		h = _history_for(obj)
		source, other = ("back", "forward") if step < 0 else ("forward", "back")
		stack = h[source]
		title = _window_title(obj).lstrip("*")
		here = a.line_index(off)
		lines = [a.line_text(i) for i in range(a.lineCount)]
		target = None
		for i in range(len(stack) - 1, -1, -1):
			placeTitle, mark, column = stack[i]
			if placeTitle != title:
				# Another file shown in this window (a Notepad++ tab): keep it.
				continue
			del stack[i]
			marks = [mark]
			bookmarks.reanchor(marks, lines)
			if marks and mark.line != here:
				target = (mark, column)
				break
		if target is None:
			if step < 0:
				# Translators: there is no earlier place to go back to.
				ui.message(_("No earlier place to go back to"))
			else:
				# Translators: there is no later place to go forward to.
				ui.message(_("No later place to go forward to"))
			return
		h[other].append(_place(obj, a, off))
		mark, column = target
		lineStart, lineEnd = a.line_bounds(mark.line)
		speech.speak([_line_place(a, mark.line)])
		self._move_caret(obj, a, min(lineStart + column, lineEnd), remember=False)

	@script(
		# Translators: describes the go back command.
		description=_("Goes back to where the caret was before the last jump"),
	)
	def script_goBack(self, gesture):
		self._history_nav(-1)

	@script(
		# Translators: describes the go forward command.
		description=_("Goes forward again after going back"),
	)
	def script_goForward(self, gesture):
		self._history_nav(1)

	def _bookmark_nav(self, step):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		marks = _bookmarks_for(obj, a)[1]
		if not marks or not bookmarks.visible(marks):
			# Translators: the file has no bookmarks.
			ui.message(_("No bookmarks in this file"))
			return
		li = a.line_index(off)
		mark, wrapped = bookmarks.neighbour(marks, li, step)
		_save_bookmarks()
		if mark.line == li:
			# Translators: the caret is on the file's only bookmark.
			ui.message(_("This is the only bookmark"))
			return
		parts = []
		if wrapped:
			# Translators: going to the next bookmark went round to the first one.
			parts.append(_("back to the top") if step > 0 else
				# Translators: going to the previous bookmark went round to the last one.
				_("back to the bottom"))
		parts.append(_line_place(a, mark.line))
		speech.speak([", ".join(parts)])
		self._move_caret(obj, a, a.first_char(mark.line))

	@script(
		# Translators: describes the next bookmark command.
		description=_("Moves to the next bookmark"),
	)
	def script_nextBookmark(self, gesture):
		self._bookmark_nav(1)

	@script(
		# Translators: describes the previous bookmark command.
		description=_("Moves to the previous bookmark"),
	)
	def script_previousBookmark(self, gesture):
		self._bookmark_nav(-1)

	@script(
		# Translators: describes the bookmarks list command.
		description=_("Lists the bookmarks in the file; Enter moves there, Delete removes one"),
	)
	def script_bookmarksList(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		key, marks = _bookmarks_for(obj, a)
		shown = bookmarks.visible(marks) if marks else []
		if not shown:
			ui.message(_("No bookmarks in this file"))
			return
		text = a.text
		li = a.line_index(off)
		labels = []
		for mark in shown:
			label = _("line {line}: {text}").format(line=mark.line + 1, text=analyzer.shorten(a.line_text(mark.line).strip()))
			chain = a.declaration_chain(a.first_char(mark.line))
			if chain:
				label += ", " + _("in {kind} {name}").format(kind=_(chain[-1].kind), name=chain[-1].name)
			labels.append(label)
		selection = next((i for i, m in enumerate(shown) if m.line >= li), 0)

		def onDelete(index):
			mark = shown.pop(index)
			if mark in marks:
				marks.remove(mark)
			_bookmark_store().touch(key)
			_save_bookmarks()

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None and dlg.choice < len(shown):
				core.callLater(250, self._jump_to_offset, a.first_char(shown[dlg.choice].line), text)

		_run_dialog(
			lambda: ListDialog(
				# Translators: title of the bookmarks list, e.g. "Bookmarks: 3".
				gui.mainFrame, _("Bookmarks: {count}").format(count=len(shown)),
				# Translators: label of the bookmarks list.
				_("&Bookmarks:"), labels, selection, onDelete=onDelete,
			),
			onClose,
		)

	@script(
		# Translators: describes the command that removes every bookmark of a file.
		description=_("Removes every bookmark in the file"),
	)
	def script_clearBookmarks(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		key, marks = _bookmarks_for(obj, a)
		count = len(bookmarks.visible(marks)) if marks else 0
		if not count:
			ui.message(_("No bookmarks in this file"))
			return
		del marks[:]
		_bookmark_store().touch(key)
		_save_bookmarks()
		# Translators: every bookmark of the file was removed, e.g. "Removed 3 bookmarks".
		ui.message(_("Removed {count} bookmarks").format(count=count) if count > 1 else _("Removed 1 bookmark"))

	@script(
		# Translators: describes the TODO list command.
		description=_("Lists TODO, FIXME and similar notes in comments; Enter moves there"),
	)
	def script_todoList(self, gesture):
		obj = self._editor()
		if not obj:
			return
		a, off = self._doc(obj)
		notes = editing.todos(a)
		if not notes:
			# Translators: there are no TODO notes in the file.
			ui.message(_("No TODO notes found"))
			return
		text = a.text
		labels = [
			# Translators: a TODO note, e.g. "line 4, TODO: handle errors".
			_("line {line}, {kind}: {text}").format(line=li + 1, kind=kind, text=note) for li, kind, note in notes
		]

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice is not None:
				core.callLater(250, self._jump_to_offset, a.first_char(notes[dlg.choice][0]), text)

		_run_dialog(
			# Translators: title of the TODO list, e.g. "TODO notes: 3".
			lambda: ListDialog(gui.mainFrame, _("TODO notes: {count}").format(count=len(notes)), _("&Notes:"), labels),
			onClose,
		)

	# Running, terminal, explorer, palette -----------------------------------------------------

	@script(
		# Translators: describes the run command.
		description=_("Saves and runs the Python file in a console window; F8 then goes to the error it stopped on"),
	)
	def script_runFile(self, gesture):
		obj = self._editor()
		if not obj:
			return
		title = _window_title(obj)
		if not filepath.title_file(title):
			ui.message(_("Save the file first"))
			return
		if analyzer.extension_from_title(title) not in ("py", "pyw"):
			# Translators: only Python files can be run for now.
			ui.message(_("Running works for Python files"))
			return
		if filepath.is_unsaved(title):
			keyboardHandler.KeyboardInputGesture.fromName("control+s").send()
			core.callLater(600, self._run_saved, obj)
			return
		self._run_saved(obj)

	def _run_saved(self, obj):
		if filepath.is_unsaved(_window_title(obj)):
			# Translators: the file still has unsaved changes (for example a Save As dialog is open).
			ui.message(_("The file is not saved yet"))
			return
		_with_file_path(obj, lambda path: self._launch(obj, path))

	def _launch(self, obj, path):
		env = _environment()
		command = _python_command(env)
		if command is None:
			# Translators: Python is not installed.
			ui.message(_("Python was not found. Install it from python.org, then try again"))
			return
		# A report file of its own, so runs that overlap do not mix up results.
		fd, report = tempfile.mkstemp(prefix="codeCompass-run-", suffix=".json")
		os.close(fd)
		# Translators: shown in the console when the program ends; keep {status}.
		prompt = _("\nThe program finished (exit code {status}). Press Enter to close this window.")
		try:
			proc = subprocess.Popen(
				command + [os.path.abspath(RUNNER), path, report, prompt],
				cwd=os.path.dirname(path), creationflags=CREATE_NEW_CONSOLE, env=env,
			)
		except OSError:
			log.error("Code Compass: could not start Python", exc_info=True)
			try:
				os.remove(report)
			except OSError:
				pass
			ui.message(_("Python was not found. Install it from python.org, then try again"))
			return
		hwnd = getattr(obj, "windowHandle", None)
		seq = _runSequence[hwnd] = _runSequence.get(hwnd, 0) + 1
		app = getattr(getattr(obj, "appModule", None), "appName", None)
		# Translators: reported when a program starts, e.g. "Running main.py".
		ui.message(_("Running {name}").format(name=os.path.basename(path)))
		threading.Thread(
			target=self._wait_for_run, args=(proc, report, hwnd, os.path.basename(path), seq, app), daemon=True,
		).start()

	def _wait_for_run(self, proc, report, hwnd, name, seq=None, app=None):
		proc.wait()
		data = None
		try:
			with open(report, encoding="utf-8") as f:
				data = json.load(f)
		except (OSError, ValueError):
			pass
		try:
			os.remove(report)
		except OSError:
			pass
		queueHandler.queueFunction(queueHandler.eventQueue, self._run_finished, data, hwnd, name, seq, app)

	def _run_finished(self, data, hwnd, name="main.py", seq=None, app=None):
		if seq is not None and seq != _runSequence.get(hwnd):
			# An older run of this window ended after a newer one started: the
			# newer run's result is the one that counts.
			return
		error = data.get("error") if data else None
		if error and error.get("line"):
			_runErrors[hwnd] = (name, problems.Problem(error["line"] - 1, 0, error["message"], "run"))
			_runErrorPending.add(hwnd)
			_play("taskFailed")
			if app == "notepad++":
				# Translators: the program stopped on an error, in Notepad++ (where F8 is
				# Notepad++'s own); the problems list goes to its line.
				text = _("The program stopped on line {line}: {message}. NVDA+shift+K, then shift+C lists it")
			else:
				# Translators: the program stopped on an error; F8 goes to its line.
				text = _("The program stopped on line {line}: {message}. Press F8 to go there")
			ui.message(text.format(line=error["line"], message=error["message"]))
			return
		_runErrors.pop(hwnd, None)
		_runErrorPending.discard(hwnd)
		_play("taskFailed" if error or (data or {}).get("status") else "taskCompleted")
		if data is None:
			# Translators: the program's window was closed before it reported back.
			ui.message(_("The program window was closed"))
		elif error:
			# Translators: the program stopped on an error outside this file.
			ui.message(_("The program stopped: {message}").format(message=error["message"]))
		else:
			seconds = data.get("seconds")
			if isinstance(seconds, (int, float)):
				# Translators: the program ended normally, e.g. "The program finished in 1.3 seconds, exit code 0".
				ui.message(_("The program finished in {time}, exit code {status}").format(
					time=_duration(seconds), status=data.get("status", 0)))
			else:
				# Translators: the program ended normally, e.g. "The program finished, exit code 0".
				ui.message(_("The program finished, exit code {status}").format(status=data.get("status", 0)))

	@script(
		# Translators: describes the terminal command.
		description=_("Opens a Command Prompt in the file's folder"),
	)
	def script_terminal(self, gesture):
		obj = self._editor()
		if not obj:
			return
		_with_file_path(
			obj, lambda path: _open_terminal(os.path.dirname(path) if path else os.path.expanduser("~")),
			optional=True)

	@script(
		# Translators: describes the explorer command.
		description=_("Shows the project's files and folders as a tree; Enter opens a file"),
	)
	def script_explorer(self, gesture):
		obj = self._editor()
		if not obj:
			return

		def show(path):
			root = filepath.project_root(path) if path else os.path.expanduser("~")

			def onClose(dlg, result):
				if result != wx.ID_OK or not dlg.choice:
					return
				if path and os.path.normcase(dlg.choice) == os.path.normcase(path):
					# A second Notepad on the same file would overwrite changes.
					# Translators: the chosen file is the one already open.
					core.callLater(250, ui.message, _("{name} is already open").format(name=os.path.basename(path)))
					return
				_open_in_editor(obj, dlg.choice)

			_run_dialog(lambda: ExplorerDialog(gui.mainFrame, root, path, None), onClose)

		_with_file_path(obj, show, optional=True)

	@script(
		# Translators: describes the command palette command.
		description=_("Lists every Code Compass command with its keys; type to filter, Enter runs one"),
	)
	def script_palette(self, gesture):
		commands = []
		for name, keys in PALETTE:
			scriptFunc = getattr(self, "script_" + name, None)
			doc = getattr(scriptFunc, "__doc__", None)
			if doc:
				commands.append(("%s: %s" % (doc.rstrip("."), keys) if keys else doc.rstrip("."), name))

		def onClose(dlg, result):
			if result == wx.ID_OK and dlg.choice:
				core.callLater(250, getattr(self, "script_" + dlg.choice), None)

		_run_dialog(lambda: PaletteDialog(gui.mainFrame, commands), onClose)


	@script(
		# Translators: describes the command that lists layer commands.
		description=_("Lists the Code Compass commands"),
	)
	def script_layerHelp(self, gesture):
		# Translators: the list of Code Compass commands, read by the H key.
		ui.message(_(
			"After NVDA+shift+K: W where am I, shift+W details, F function family, "
			"D level, M matching bracket, B block start, E block end, S select block, "
			"N next function, P previous function, O outline, shift+E explorer, "
			"A save snippet, I insert snippet, C check brackets, shift+C problems, "
			"shift+T TODO notes, shift+B bookmarks, backspace back to where you were, shift+backspace forward again, "
			"R reload from disk, "
			"shift+P all commands, T level report mode. "
			"In Notepad, control+shift+P lists every command and its keys."
		))


# --- Settings panel -------------------------------------------------------------


class CodeCompassSettingsPanel(SettingsPanel):
	# Translators: title of the settings panel.
	title = _("Code Compass")

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		c = _conf()
		modes = _level_modes()
		self.levelReport = helper.addLabeledControl(
			# Translators: label of the level report mode choice.
			_("Report bracket &level when moving by line:"),
			wx.Choice,
			choices=[label for _v, label in modes],
		)
		values = [v for v, _label in modes]
		self.levelReport.SetSelection(values.index(c["levelReport"]) if c["levelReport"] in values else 1)
		self.onlyOnChange = helper.addItem(
			# Translators: checkbox to report the level only when it changes.
			wx.CheckBox(self, label=_("&Only report when the level changes")),
		)
		self.onlyOnChange.SetValue(c["onlyOnChange"])
		self.shortParenTone = helper.addItem(
			# Translators: checkbox for a shorter tone inside parentheses.
			wx.CheckBox(self, label=_("Shorter tone insi&de parentheses and square brackets")),
		)
		self.shortParenTone.SetValue(c["shortParenTone"])
		self.announceClosers = helper.addItem(
			# Translators: checkbox to say what a closing bracket closes.
			wx.CheckBox(self, label=_("Sa&y what closing brackets close")),
		)
		self.announceClosers.SetValue(c["announceClosers"])
		self.checkOnSave = helper.addItem(
			# Translators: checkbox to check for problems when saving with control+S.
			wx.CheckBox(self, label=_("Check for problems &when saving")),
		)
		self.checkOnSave.SetValue(c["checkOnSave"])
		self.errorSound = helper.addItem(
			# Translators: checkbox for a sound on lines with a problem.
			wx.CheckBox(self, label=_("Play a sound on lines with a p&roblem")),
		)
		self.errorSound.SetValue(c["errorSound"])
		self.bookmarkSound = helper.addItem(
			# Translators: checkbox for a sound on lines with a bookmark.
			wx.CheckBox(self, label=_("Play a sound on bookmarked li&nes")),
		)
		self.bookmarkSound.SetValue(c["bookmarkSound"])
		styles = _sound_styles()
		self.soundStyle = helper.addLabeledControl(
			# Translators: label of the choice between VS Code's sounds and beeps.
			_("Sound styl&e:"),
			wx.Choice,
			choices=[label for _v, label in styles],
		)
		styleValues = [v for v, _label in styles]
		self.soundStyle.SetSelection(styleValues.index(c["soundStyle"]) if c["soundStyle"] in styleValues else 0)
		liveModes = _live_modes()
		self.liveCheck = helper.addLabeledControl(
			# Translators: label of the choice of what happens when typing makes a new problem.
			_("E&xamine code while typing:"),
			wx.Choice,
			choices=[label for _v, label in liveModes],
		)
		liveValues = [v for v, _label in liveModes]
		self.liveCheck.SetSelection(liveValues.index(c["liveCheck"]) if c["liveCheck"] in liveValues else 1)
		self.announceDeclarations = helper.addItem(
			# Translators: checkbox to say the function or class the caret moves into.
			wx.CheckBox(self, label=_("Say the &function or class the caret moves into")),
		)
		self.announceDeclarations.SetValue(c["announceDeclarations"])
		self.autoIndent = helper.addItem(
			# Translators: checkbox for automatic indentation in Notepad.
			wx.CheckBox(self, label=_("Automatic &indentation on Enter and closing brackets (Windows 10 Notepad)")),
		)
		self.autoIndent.SetValue(c["autoIndent"])
		self.autoClose = helper.addItem(
			# Translators: checkbox to add closing brackets and quotes automatically.
			wx.CheckBox(self, label=_("Add closing brackets and &quotes automatically (Windows 10 Notepad)")),
		)
		self.autoClose.SetValue(c["autoClose"])
		self.basePitch = helper.addLabeledControl(
			# Translators: pitch of the level 1 tone.
			_("Tone pitc&h for level 1 (Hz):"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=100, max=2000, initial=c["basePitch"],
		)
		self.semitones = helper.addLabeledControl(
			# Translators: how much higher each level's tone is.
			_("Semi&tones higher per level:"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=1, max=12, initial=c["semitonesPerLevel"],
		)
		self.apps = helper.addLabeledControl(
			# Translators: applications where line moves report the level.
			_("Applications with level tones and quick keys (co&mma separated):"),
			wx.TextCtrl,
		)
		self.apps.SetValue(c["apps"])
		langs = _languages()
		self.language = helper.addLabeledControl(
			# Translators: language of Code Compass messages.
			_("Lan&guage of Code Compass messages:"),
			wx.Choice,
			choices=[label for _v, label in langs],
		)
		langValues = [v for v, _label in langs]
		self.language.SetSelection(langValues.index(c["language"]) if c["language"] in langValues else 0)

	def onSave(self):
		c = _conf()
		c["levelReport"] = _level_modes()[self.levelReport.GetSelection()][0]
		c["onlyOnChange"] = self.onlyOnChange.GetValue()
		c["shortParenTone"] = self.shortParenTone.GetValue()
		c["announceClosers"] = self.announceClosers.GetValue()
		c["checkOnSave"] = self.checkOnSave.GetValue()
		c["errorSound"] = self.errorSound.GetValue()
		c["bookmarkSound"] = self.bookmarkSound.GetValue()
		c["soundStyle"] = _sound_styles()[self.soundStyle.GetSelection()][0]
		c["liveCheck"] = _live_modes()[self.liveCheck.GetSelection()][0]
		c["announceDeclarations"] = self.announceDeclarations.GetValue()
		c["autoIndent"] = self.autoIndent.GetValue()
		c["autoClose"] = self.autoClose.GetValue()
		c["basePitch"] = self.basePitch.GetValue()
		c["semitonesPerLevel"] = self.semitones.GetValue()
		c["apps"] = self.apps.GetValue().strip()
		c["language"] = _languages()[self.language.GetSelection()][0]
