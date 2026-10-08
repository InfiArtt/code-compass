# -*- coding: UTF-8 -*-
# Smoke tests for the NVDA plugin, run outside NVDA against stub modules.
# They catch wiring mistakes (wrong names, bad offsets), not NVDA behavior.
#     py -3.13 -m unittest discover -s tests -v

import builtins
import os
import tempfile
import re
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins")

POSITION_ALL, POSITION_CARET, POSITION_FIRST, POSITION_SELECTION = "all", "caret", "first", "selection"
UNIT_LINE, UNIT_PARAGRAPH, UNIT_CHARACTER = "line", "paragraph", "character"


class _Stub(object):
	def __init__(self, *args, **kwargs):
		pass

	def __getattr__(self, name):
		return mock.MagicMock()


class FakeEditableText(object):
	def _caretScriptPostMovedHelper(self, speakUnit, gesture, info=None):
		self.spokeLine = True

	def event_typedCharacter(self, ch):
		self.echoed = ch

	def script_caret_backspaceCharacter(self, gesture):
		"""Notepad's own Backspace: delete the character before the caret."""
		if self.caret > 0:
			self.text = self.text[:self.caret - 1] + self.text[self.caret:]
			self.caret -= 1
			self.selection = (self.caret, self.caret)


class FakeOffsetsTextInfo(object):
	encoding = "utf_16_le"

	def __init__(self, editor, start, end):
		self.editor = editor
		self._startOffset = start
		self._endOffset = end

	@property
	def text(self):
		return self.editor.text[self._startOffset:self._endOffset]

	def updateCaret(self):
		self.editor.caret = self._startOffset
		self.editor.selection = (self._startOffset, self._startOffset)

	def updateSelection(self):
		self.editor.selection = (self._startOffset, self._endOffset)
		self.editor.caret = self._endOffset

	def copy(self):
		return FakeOffsetsTextInfo(self.editor, self._startOffset, self._endOffset)

	def expand(self, unit):
		pass


class FakeOffsets(object):
	def __init__(self, start, end):
		self.startOffset = start
		self.endOffset = end


def install_stubs():
	class Conf(dict):
		spec = {}

	confObj = Conf()
	mods = {}

	def mod(name, **attrs):
		m = types.ModuleType(name)
		for k, v in attrs.items():
			setattr(m, k, v)
		mods[name] = m
		return m

	mod("addonHandler", initTranslation=lambda: None)
	mod("api", getForegroundObject=mock.MagicMock(), getFocusObject=mock.MagicMock(),
		copyToClip=mock.MagicMock(return_value=True), getClipData=mock.MagicMock(return_value="old clip"))
	mod("braille", handler=mock.MagicMock())
	mod("config", conf=confObj)
	mod("controlTypes", Role=types.SimpleNamespace(EDITABLETEXT="editable"),
		OutputReason=types.SimpleNamespace(CARET="caret"))
	mod("core", callLater=mock.MagicMock())
	mod("globalPluginHandler", GlobalPlugin=type("GlobalPlugin", (object,), {
		"__init__": lambda self: None,
		"terminate": lambda self: None,
		"getScript": lambda self, gesture: None,
	}))
	mod("globalVars", appArgs=types.SimpleNamespace(secure=False, configPath=tempfile.mkdtemp()))
	mod("keyboardHandler", KeyboardInputGesture=mock.MagicMock())
	mod("queueHandler", eventQueue=object(), queueFunction=lambda queue, func, *args, **kw: func(*args, **kw))
	settingsDialogs = mod(
		"gui.settingsDialogs", SettingsPanel=_Stub,
		NVDASettingsDialog=types.SimpleNamespace(categoryClasses=[]))
	guiHelper = mod("gui.guiHelper", BoxSizerHelper=mock.MagicMock(), BORDER_FOR_DIALOGS=10)
	nvdaControls = mod("gui.nvdaControls", SelectOnFocusSpinCtrl=mock.MagicMock())
	mod("gui", mainFrame=mock.MagicMock(), runScriptModalDialog=mock.MagicMock(), messageBox=mock.MagicMock(),
		settingsDialogs=settingsDialogs, guiHelper=guiHelper, nvdaControls=nvdaControls)
	mod("speech", speak=mock.MagicMock(), speakTextInfo=mock.MagicMock(), speakTypedCharacters=mock.MagicMock(), speakSpelling=mock.MagicMock())
	textInfos = mod(
		"textInfos", POSITION_ALL=POSITION_ALL, POSITION_CARET=POSITION_CARET,
		POSITION_FIRST=POSITION_FIRST, POSITION_SELECTION=POSITION_SELECTION,
		UNIT_LINE=UNIT_LINE, UNIT_PARAGRAPH=UNIT_PARAGRAPH, UNIT_CHARACTER=UNIT_CHARACTER)
	offsets = mod("textInfos.offsets", Offsets=FakeOffsets, OffsetsTextInfo=FakeOffsetsTextInfo)
	textInfos.offsets = offsets

	class IdentityConverter(object):
		def __init__(self, text):
			pass

		def encodedToStrOffsets(self, a, b=None, raiseOnError=False):
			return (a, b)

		def strToEncodedOffsets(self, a, b=None, raiseOnError=False):
			return (a, b)

	mod("textUtils", getOffsetConverter=lambda enc: IdentityConverter)
	mod("tones", beep=mock.MagicMock())
	mod("nvwave", playWaveFile=mock.MagicMock())
	mod("ui", message=mock.MagicMock(), browseableMessage=mock.MagicMock())
	mod(
		"wx", Dialog=_Stub, BoxSizer=mock.MagicMock(), ListBox=object,
		Choice=object, CheckBox=mock.MagicMock(), TextCtrl=object,
		VERTICAL=1, ALL=2, EXPAND=4, OK=8, CANCEL=16, ID_OK=5100, ID_YES=5103, ID_NO=5104,
		NOT_FOUND=-1, EVT_LISTBOX_DCLICK=1, EVT_BUTTON=2, EVT_SHOW=3, EVT_LISTBOX=4,
		EVT_TREE_ITEM_ACTIVATED=5, TreeCtrl=object, TR_HAS_BUTTONS=1, TR_HIDE_ROOT=2,
		TR_LINES_AT_ROOT=4, TR_SINGLE=8, TE_MULTILINE=1, TE_READONLY=2, TE_DONTWRAP=4,
		HORIZONTAL=2, YES=5103, YES_NO=10, ICON_QUESTION=256, ID_CANCEL=5101,
		TextEntryDialog=_Stub, FileDialog=_Stub, DirDialog=_Stub, FD_OPEN=1, FD_FILE_MUST_EXIST=16,
		EVT_TEXT=6, EVT_KEY_DOWN=7, EVT_TREE_ITEM_EXPANDING=8, WXK_DOWN=317, WXK_F2=341,
		WXK_DELETE=127, WXK_BACK=8, ICON_ERROR=512,
		CallAfter=lambda f, *a: f(*a), CallLater=mock.MagicMock())
	mod("editableText", EditableText=FakeEditableText)
	mod("logHandler", log=mock.MagicMock())
	mod("NVDAObjects", NVDAObject=object)

	def script(**kw):
		def deco(f):
			f.__doc__ = kw.get("description")
			return f
		return deco

	mod("scriptHandler", isScriptWaiting=lambda: False, script=script)
	sys.modules.update(mods)
	builtins._ = lambda s: s
	return mods, confObj


MODS, CONF = install_stubs()
sys.path.insert(0, ROOT)
import codeCompass  # noqa: E402


def default_config():
	"""Defaults straight from the plugin's confspec."""
	conf = {}
	for key, spec in codeCompass.confspec.items():
		raw = re.search(r"default=([^,)]+)", spec).group(1).strip("'")
		if raw in ("True", "False"):
			conf[key] = raw == "True"
		elif raw.isdigit():
			conf[key] = int(raw)
		else:
			conf[key] = raw
	return conf


SOURCE = (
	"class Foo {\r\n"
	"    func bar() {\r\n"
	"        call(1,\r\n"
	"             2)\r\n"
	"    }\r\n"
	"    func baz() {\r\n"
	"    }\r\n"
	"}\r\n"
)


class Editor(codeCompass.CodeEditor, FakeEditableText):
	"""What NVDA would build: the overlay first, then the edit control."""

	role = "editable"
	windowHandle = 42

	def __init__(self, text, caret=0):
		self.text = text
		self.caret = caret
		self.selection = (caret, caret)

	def makeTextInfo(self, position):
		if position == POSITION_ALL:
			return FakeOffsetsTextInfo(self, 0, len(self.text))
		if position == POSITION_CARET:
			return FakeOffsetsTextInfo(self, self.caret, self.caret)
		if position == POSITION_SELECTION:
			return FakeOffsetsTextInfo(self, *self.selection)
		if position == POSITION_FIRST:
			return FakeOffsetsTextInfo(self, 0, 0)
		if isinstance(position, FakeOffsets):
			return FakeOffsetsTextInfo(self, position.startOffset, position.endOffset)
		raise ValueError(position)


class Gesture(object):
	def __init__(self, *ids, isModifier=False):
		self.normalizedIdentifiers = list(ids)
		self.isModifier = isModifier
		self.send = mock.MagicMock()


class PluginTests(unittest.TestCase):
	def setUp(self):
		for m in ("tones", "ui", "speech", "core", "api", "keyboardHandler"):
			for v in vars(MODS[m]).values():
				if isinstance(v, mock.MagicMock):
					v.reset_mock()
		CONF["codeCompass"] = default_config()
		MODS["api"].getForegroundObject.return_value = types.SimpleNamespace(name="Foo.swift - Notepad")
		codeCompass._cache = codeCompass._DocCache()
		self.plugin = codeCompass.GlobalPlugin()
		self.ed = Editor(SOURCE)
		MODS["api"].getFocusObject.return_value = self.ed

	def caret_at(self, needle, extra=0):
		self.ed.caret = SOURCE.index(needle) + extra
		self.ed.selection = (self.ed.caret, self.ed.caret)

	def spoken(self):
		return [c[0][0][0] for c in MODS["speech"].speak.call_args_list]

	# Overlay -------------------------------------------------------------------

	def test_overlay_chosen_for_notepad(self):
		obj = types.SimpleNamespace(role="editable", appModule=types.SimpleNamespace(appName="notepad"))
		clsList = [FakeEditableText]
		self.plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
		self.assertIs(clsList[0], codeCompass.CodeEditor)

	def test_overlay_skipped_elsewhere(self):
		obj = types.SimpleNamespace(role="editable", appModule=types.SimpleNamespace(appName="code"))
		clsList = [FakeEditableText]
		self.plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
		self.assertNotIn(codeCompass.CodeEditor, clsList)

	def test_quick_keys_bound(self):
		gestures = codeCompass.CodeEditor._CodeEditor__gestures
		for name in gestures.values():
			self.assertTrue(hasattr(codeCompass.CodeEditor, "script_" + name), name)
		self.assertEqual(gestures["kb:alt+downArrow"], "ccNextSameLevel")

	# Line moves ------------------------------------------------------------------

	def test_line_move_beeps_with_level_pitch(self):
		self.caret_at("        call")
		info = self.ed.makeTextInfo(POSITION_CARET)
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, info)
		self.assertTrue(self.ed.spokeLine)
		hz, length = MODS["tones"].beep.call_args[0]
		self.assertEqual(hz, int(330 * 2 ** (3 / 12.0)))  # level 2
		self.assertEqual(length, 40)

	def test_line_inside_parens_gets_short_tone(self):
		self.caret_at("             2)")
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, None)
		_hz, length = MODS["tones"].beep.call_args[0]
		self.assertEqual(length, 20)

	def test_top_level_is_silent(self):
		self.ed.caret = 0
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, None)
		MODS["tones"].beep.assert_not_called()

	def test_closing_line_says_what_it_closes(self):
		self.caret_at("    }\r\n    func baz")
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, None)
		self.assertEqual(self.spoken(), ["closes func bar()"])

	def test_closer_announcement_can_be_turned_off(self):
		CONF["codeCompass"]["announceClosers"] = False
		self.caret_at("    }\r\n    func baz")
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, None)
		self.assertEqual(self.spoken(), [])

	def test_typed_closer(self):
		# The user just typed the ")" of "call(1, 2)".
		self.caret_at("2)", 2)
		self.ed.event_typedCharacter(")")
		self.assertEqual(self.ed.echoed, ")")
		_delay, func, obj, ch = MODS["core"].callLater.call_args[0]
		func(obj, ch)
		self.assertEqual(self.spoken(), ["closes call paren"])

	# Layer ---------------------------------------------------------------------

	def test_layer_where_am_i(self):
		self.caret_at("2)")
		self.plugin.script_layer(None)
		scr = self.plugin.getScript(Gesture("kb(desktop):w", "kb:w"))
		scr(None)
		MODS["ui"].message.assert_called_with("class Foo; func bar(), 4 lines; call paren")
		# The layer is single-shot.
		self.assertIsNone(self.plugin.getScript(Gesture("kb:w")))

	def test_layer_survives_shift(self):
		self.plugin.script_layer(None)
		self.assertIsNone(self.plugin.getScript(Gesture("kb:shift", isModifier=True)))
		scr = self.plugin.getScript(Gesture("kb(desktop):shift+w", "kb:shift+w"))
		self.assertEqual(scr, self.plugin.script_whereAmIDetails)

	def test_layer_unknown_key_beeps(self):
		self.plugin.script_layer(None)
		scr = self.plugin.getScript(Gesture("kb:q"))
		self.assertEqual(scr, self.plugin.script_layerError)

	# Moves -----------------------------------------------------------------------

	def test_match_bracket_moves_caret(self):
		self.caret_at("call(", 4)
		self.plugin.script_matchBracket(None)
		self.assertEqual(self.ed.caret, SOURCE.index("2)") + 1)
		MODS["speech"].speakTextInfo.assert_called()

	def test_block_start_then_outward(self):
		self.caret_at("        call")
		self.plugin.script_blockStart(None)
		self.assertEqual(self.ed.caret, SOURCE.index("bar() {") + len("bar() "))
		self.plugin.script_blockStart(None)
		self.assertEqual(self.ed.caret, SOURCE.index("{"))

	def test_block_end_then_outward(self):
		self.caret_at("        call")
		self.plugin.script_blockEnd(None)
		self.assertEqual(SOURCE[self.ed.caret], "}")
		self.plugin.script_blockEnd(None)
		self.assertEqual(self.ed.caret, SOURCE.rindex("}"))

	def test_quick_key_same_level(self):
		self.caret_at("    func bar")
		self.ed.script_ccNextSameLevel(Gesture("kb:alt+downArrow"))
		self.assertEqual(self.ed.caret, SOURCE.index("func baz"))
		self.ed.script_ccNextSameLevel(Gesture("kb:alt+downArrow"))
		MODS["ui"].message.assert_called_with("End of block")

	def test_quick_key_declarations(self):
		self.ed.caret = 0
		self.ed.script_ccNextDeclaration(Gesture("kb:alt+pageDown"))
		self.assertEqual(self.ed.caret, SOURCE.index("func bar"))
		self.ed.script_ccPreviousDeclaration(Gesture("kb:alt+pageUp"))
		self.assertEqual(self.ed.caret, 0)

	def test_select_block_expands(self):
		self.caret_at("call")
		self.plugin.script_selectBlock(None)
		start, end = self.ed.selection
		self.assertEqual(SOURCE[start:end], "    func bar() {\r\n        call(1,\r\n             2)\r\n    }\r\n")
		MODS["ui"].message.assert_called_with("Selected 4 lines: func bar() {")
		self.plugin.script_selectBlock(None)
		self.assertEqual(self.ed.selection, (0, len(SOURCE)))

	def test_save_checks_brackets(self):
		self.ed.text = SOURCE.replace("2)", "2")
		gesture = Gesture("kb:control+s")
		self.ed.script_ccSave(gesture)
		gesture.send.assert_called_once()
		_delay, func, obj = MODS["core"].callLater.call_args[0]
		func(obj)
		msg = MODS["ui"].message.call_args[0][0]
		self.assertTrue(msg.startswith("Saved, but: 1 problem: unclosed paren"), msg)

	def test_save_says_no_problems(self):
		self.ed.script_ccSave(Gesture("kb:control+s"))
		_delay, func, obj = MODS["core"].callLater.call_args[0]
		func(obj)
		MODS["ui"].message.assert_called_once_with("Saved, no problems")

	# Other commands ------------------------------------------------------------------

	def test_check_brackets(self):
		self.plugin.script_checkBrackets(None)
		MODS["ui"].message.assert_called_with("All brackets balanced")
		self.ed.text = SOURCE.replace("2)", "2")
		self.plugin.script_checkBrackets(None)
		msg = MODS["ui"].message.call_args[0][0]
		self.assertIn("1 problem:", msg)
		self.assertIn("unclosed paren on line 3", msg)

	def test_report_level(self):
		self.caret_at("2)")
		self.plugin.script_reportLevel(None)
		MODS["ui"].message.assert_called_with("level 3: brace, brace, paren")

	def test_outline_jump(self):
		self.caret_at("        call")

		def showModal(dlg):
			dlg.choice = 2  # "baz"
			return 5100  # wx.ID_OK

		with mock.patch.object(codeCompass.OutlineDialog, "ShowModal", showModal, create=True):
			self.plugin.script_outline(None)
		self.assertIsNone(codeCompass._openDialog)
		_delay, func, line = MODS["core"].callLater.call_args[0]
		func(line)
		self.assertEqual(self.ed.caret, SOURCE.index("func baz"))

	def test_outline_selects_current_declaration(self):
		self.caret_at("        call")
		seen = {}

		def create(parent, items, selection):
			seen["selection"] = items[selection].name
			return mock.MagicMock(ShowModal=mock.MagicMock(return_value=5101))

		with mock.patch.object(codeCompass, "OutlineDialog", create):
			self.plugin.script_outline(None)
		self.assertEqual(seen["selection"], "bar")

	# Declarations ----------------------------------------------------------------

	def test_family(self):
		self.caret_at("        call")
		self.plugin.script_family(None)
		MODS["ui"].message.assert_called_with("function bar, 4 lines, in class Foo")
		self.ed.caret = 0
		self.plugin.script_family(None)
		MODS["ui"].message.assert_called_with("class Foo, 8 lines, top level. Contains 2: bar, baz")

	def test_parent_and_child_keys(self):
		self.caret_at("        call")
		self.ed.script_ccParentDeclaration(Gesture("kb:alt+leftArrow"))
		self.assertEqual(self.ed.caret, SOURCE.index("func bar"))
		self.ed.script_ccParentDeclaration(Gesture("kb:alt+leftArrow"))
		self.assertEqual(self.ed.caret, 0)
		self.ed.script_ccChildDeclaration(Gesture("kb:alt+rightArrow"))
		self.assertEqual(self.ed.caret, SOURCE.index("func bar"))

	# Snippets -----------------------------------------------------------------------

	def run_name_dialog(self, name, action):
		class NameDialog(object):
			def __init__(self, *args):
				self.args = args

			def Bind(self, *a, **k):
				pass

			def ShowModal(self):
				return 5100

			def GetValue(self):
				return name

			def Destroy(self):
				pass

		with mock.patch.object(MODS["wx"], "TextEntryDialog", NameDialog, create=True):
			action()

	def test_save_snippet_from_caret(self):
		folder = codeCompass._snippets_folder()
		self.caret_at("        call")
		self.run_name_dialog("bar", lambda: self.plugin.script_saveSnippet(None))
		path = os.path.join(folder, "bar.swift")
		with open(path, encoding="utf-8") as f:
			saved = f.read()
		self.assertEqual(saved, "func bar() {\n    call(1,\n         2)\n}\n")
		_delay, func, msg = MODS["core"].callLater.call_args[0]
		self.assertEqual(msg, "Snippet saved: bar")

	def test_save_snippet_from_selection(self):
		folder = codeCompass._snippets_folder()
		start = SOURCE.index("        call")
		end = SOURCE.index("    }\r\n    func baz")
		self.ed.selection = (start, end)
		self.run_name_dialog("callTwo", lambda: self.plugin.script_saveSnippet(None))
		with open(os.path.join(folder, "callTwo.swift"), encoding="utf-8") as f:
			self.assertEqual(f.read(), "call(1,\n     2)\n")

	def test_insert_snippet_reindents(self):
		snip = types.SimpleNamespace(name="x", read=lambda: "if a {\n    b()\n}\n")
		# Caret on the blank indented spot at the start of "    func baz".
		self.caret_at("    func baz", 4)
		self.ed.text = SOURCE
		self.plugin._insert_snippet(snip)
		pasted = MODS["api"].copyToClip.call_args_list[0][0][0]
		self.assertEqual(pasted, "if a {\r\n        b()\r\n    }")
		MODS["keyboardHandler"].KeyboardInputGesture.fromName.assert_called_with("control+v")
		_delay, func, old = MODS["core"].callLater.call_args[0]
		self.assertEqual(old, "old clip")

	def test_insert_snippet_in_notepad_skips_clipboard(self):
		snip = types.SimpleNamespace(name="x", read=lambda: "go()\n")
		self.caret_at("    func baz", 4)
		with mock.patch.object(codeCompass, "_replace_selection_directly", return_value=True) as direct:
			self.plugin._insert_snippet(snip)
		self.assertEqual(direct.call_args[0][1], "go()")
		MODS["api"].copyToClip.assert_not_called()
		MODS["ui"].message.assert_called_with("Inserted snippet x")

	def test_insert_snippet_tells_when_clipboard_had_no_text(self):
		snip = types.SimpleNamespace(name="x", read=lambda: "go()\n")
		MODS["api"].getClipData.side_effect = OSError("no text on the clipboard")
		try:
			self.plugin._insert_snippet(snip)
		finally:
			MODS["api"].getClipData.side_effect = None
		MODS["ui"].message.assert_called_with("Inserted snippet x. The clipboard now holds the snippet")
		MODS["core"].callLater.assert_not_called()

	def test_unreadable_snippet_is_reported(self):
		def fail():
			raise UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "bad")

		self.plugin._insert_snippet(types.SimpleNamespace(name="bad", read=fail))
		MODS["ui"].message.assert_called_with("Could not read snippet bad")

	def test_dialog_runner_cleans_up_when_creation_fails(self):
		MODS["gui"].mainFrame.reset_mock()

		def broken():
			raise ValueError("dialog failed")

		with self.assertRaises(ValueError):
			codeCompass._run_dialog(broken, lambda dlg, result: None)
		self.assertEqual(MODS["gui"].mainFrame.prePopup.call_count, 1)
		self.assertEqual(MODS["gui"].mainFrame.postPopup.call_count, 1)
		self.assertIsNone(codeCompass._openDialog)

	def test_cycle_mode(self):
		self.plugin.script_cycleLevelReport(None)
		self.assertEqual(CONF["codeCompass"]["levelReport"], "speech")

	def test_indonesian_messages(self):
		sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
		import build
		build.build_translations()
		CONF["codeCompass"]["language"] = "id"
		codeCompass._catalogs.clear()
		self.caret_at("2)")
		self.plugin.script_reportLevel(None)
		MODS["ui"].message.assert_called_with("level 3: kurung kurawal, kurung kurawal, kurung biasa")
		self.caret_at("    }\r\n    func baz")
		self.ed._caretScriptPostMovedHelper(UNIT_LINE, None, None)
		self.assertEqual(self.spoken()[-1], "tutup func bar()")


if __name__ == "__main__":
	unittest.main()
