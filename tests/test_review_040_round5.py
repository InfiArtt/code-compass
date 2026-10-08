# -*- coding: UTF-8 -*-
# Regression tests for the fifth 0.4.0 review round: bookmarks following
# their lines through edits and staying with their own document, JSX and
# regex literals, CSS at-rules, Go, Rust and Kotlin declarations, and
# typing with auto-close.

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402
import test_review_040_round4 as round4  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF

import analyzer  # noqa: E402
import bookmarks  # noqa: E402
import editing  # noqa: E402
from analyzer import Analysis  # noqa: E402
from bookmarks import Bookmark  # noqa: E402


def follow(marks, old, new):
	bookmarks.reanchor(marks, new, old)
	return [(m.line, m.text) for m in bookmarks.visible(marks)]


class FollowTests(unittest.TestCase):
	JS = ["function f() {", "  if (a) {", "    g();", "  }", "}", "", "function h() {}"]

	def test_insert_above_duplicate_braces(self):
		new = self.JS[:1] + [""] + self.JS[1:]
		self.assertEqual(follow([Bookmark(3, "}"), Bookmark(4, "}")], self.JS, new), [(4, "}"), (5, "}")])
		self.assertEqual(follow([Bookmark(4, "}")], self.JS, new), [(5, "}")])

	def test_delete_above(self):
		new = self.JS[:2] + self.JS[3:]
		self.assertEqual(follow([Bookmark(3, "}")], self.JS, new), [(2, "}")])

	def test_python_duplicates(self):
		old = ["def a():", "    return None", "def b():", "    return None"]
		self.assertEqual(follow([Bookmark(3, "return None")], old, [""] + old), [(4, "return None")])
		old = ["if a:", "    pass", "if b:", "    pass"]
		self.assertEqual(follow([Bookmark(1, "pass"), Bookmark(3, "pass")], old, ["import os"] + old), [(2, "pass"), (4, "pass")])

	def test_edited_line_keeps_its_place(self):
		old = ["x"] * 10 + ["    return x"] + ["y"] * 379 + ["    return x"] + ["z"] * 9
		new = list(old)
		new[390] = "    return x + 1"
		self.assertEqual(follow([Bookmark(10, "return x"), Bookmark(390, "return x")], old, new), [(10, "return x"), (390, "return x + 1")])

	def test_blank_line_bookmark(self):
		self.assertEqual(follow([Bookmark(2, "")], ["a", "b", "", "c"], ["new", "a", "b", "", "c"]), [(3, "")])

	def test_select_all_delete_and_undo(self):
		old = ["line %d" % i for i in range(100)]
		marks = [Bookmark(20, "line 20"), Bookmark(50, "line 50"), Bookmark(80, "line 80")]
		self.assertEqual(follow(marks, old, [""]), [])
		self.assertEqual(len(marks), 3)
		self.assertEqual(follow(marks, [""], old), [(20, "line 20"), (50, "line 50"), (80, "line 80")])

	def test_detached_marks_are_not_saved(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		store = bookmarks.Store(os.path.join(folder, "b.json"))
		marks = store.get("c:\\a.py")
		marks.extend([Bookmark(0, "a"), Bookmark(5, "gone")])
		marks[1].detached = True
		store.touch("c:\\a.py")
		store.save()
		with open(store.path, encoding="utf-8") as f:
			self.assertEqual(json.load(f), {"c:\\a.py": [[0, "a"]]})

	def test_half_an_emoji_is_saved(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		store = bookmarks.Store(os.path.join(folder, "b.json"))
		store.get("c:\\a.py").append(Bookmark(0, "x = '\ud83d'"))
		store.touch("c:\\a.py")
		self.assertTrue(store.save())
		self.assertEqual(bookmarks.Store(store.path).get("c:\\a.py")[0].text, "x = '\ud83d'")
		self.assertFalse(os.path.exists(store.path + ".tmp"))

	def test_save_as_over_a_file_with_bookmarks(self):
		store = bookmarks.Store(os.path.join(tempfile.gettempdir(), "never-saved-cc.json"))
		store.get("c:\\p\\a.py").append(Bookmark(7, "old"))
		store.get(("window", 1, "Untitled - Notepad")).append(Bookmark(2, "new"))
		store.move(("window", 1, "Untitled - Notepad"), "c:\\p\\a.py")
		self.assertEqual([(m.line, m.text) for m in store.get("c:\\p\\a.py")], [(2, "new")])


PY = "def a():\r\n    pass\r\n\r\ndef b():\r\n    x = 1\r\n    return x\r\n\r\ndef c():\r\n    pass\r\n"


class DocumentTests(v040.V040Tests):
	def setUp(self):
		super(DocumentTests, self).setUp()
		self.folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.file = os.path.join(self.folder, "main.py")
		self.other = os.path.join(self.folder, "other.py")
		self.second = os.path.join(self.folder, "b", "main.py")
		os.makedirs(os.path.dirname(self.second))
		for path, text in ((self.file, PY), (self.other, "x = 1\r\ny = 2\r\n"), (self.second, "print(a)\r\nprint(b)\r\nprint(c)\r\nprint(d)\r\nprint(e)\r\n")):
			with open(path, "w", encoding="utf-8", newline="") as f:
				f.write(text)
		codeCompass._bookmarkStore = bookmarks.Store(os.path.join(self.folder, "bookmarks.json"))
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		self.addCleanup(setattr, codeCompass, "_bookmarkStore", None)
		find = mock.patch.object(codeCompass.filepath, "find_file", return_value=self.file)
		self.find = find.start()
		self.addCleanup(find.stop)
		self.use(PY)

	def line(self):
		return self.ed.text.count("\n", 0, self.ed.caret)

	def key(self, path):
		return os.path.normcase(os.path.abspath(path))

	def test_another_main_py_in_the_same_window(self):
		self.at("    x = 1")
		self.plugin.script_toggleBookmark(None)
		self.find.return_value = self.second
		with open(self.second, encoding="utf-8", newline="") as f:
			self.use(f.read())
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "No bookmarks in this file")
		self.assertEqual([(m.line, m.text) for m in codeCompass._bookmarkStore.get(self.key(self.file))], [(4, "x = 1")])

	def test_unsaved_bookmarks_stay_with_their_document(self):
		self.find.return_value = None
		self.use("one\r\ntwo\r\nthree\r\n", "*Untitled - Notepad")
		self.at("three")
		self.plugin.script_toggleBookmark(None)
		# File > Open other.py without saving.
		self.find.return_value = self.other
		self.use("x = 1\r\ny = 2\r\n", "other.py - Notepad")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "No bookmarks in this file")
		self.assertFalse(codeCompass._bookmarkStore.has(self.key(self.other)))

	def test_notepad_plus_plus_new_tabs(self):
		self.find.return_value = None
		self.use("alpha\r\nbeta\r\ngamma\r\n", "*new 1 - Notepad++")
		self.at("gamma")
		self.plugin.script_toggleBookmark(None)
		self.use("one\r\ntwo\r\nthree\r\nfour\r\n", "*new 2 - Notepad++")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "No bookmarks in this file")
		self.use("alpha\r\nbeta\r\ngamma\r\n", "*new 1 - Notepad++")
		self.at("alpha")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 2)

	def test_file_new_starts_without_bookmarks(self):
		self.find.return_value = None
		self.use("one\r\ntwo\r\n", "*Untitled - Notepad")
		self.at("two")
		self.plugin.script_toggleBookmark(None)
		self.use("", "Untitled - Notepad")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.message(), "No bookmarks in this file")

	def test_lookup_runs_again_after_saving(self):
		self.at("    x = 1")
		self.plugin.script_toggleBookmark(None)
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		self.find.return_value = None
		self.use(PY.replace("x = 1", "x = 2"), "*main.py - Notepad")
		self.ed._codeCompassLineReports()
		self.find.return_value = self.file
		self.use(PY, "main.py - Notepad")
		self.at("def a")
		self.plugin.script_nextBookmark(None)
		self.assertEqual(self.line(), 4)

	def test_braces_survive_enter_above(self):
		src = "function f() {\r\n  if (a) {\r\n    g();\r\n  }\r\n}\r\n"
		self.use(src, "x.js - Notepad")
		self.find.return_value = os.path.join(self.folder, "x.js")
		with open(self.find.return_value, "w", encoding="utf-8", newline="") as f:
			f.write(src)
		for needle in ("  }", "}\r\n"):
			self.ed.caret = src.index(needle) if needle == "  }" else src.rindex("}")
			self.plugin.script_toggleBookmark(None)
		self.use(src.replace("{\r\n", "{\r\n\r\n", 1), "*x.js - Notepad")
		self.ed._codeCompassLineReports()
		marks = codeCompass._bookmarkStore.get(self.key(self.find.return_value))
		self.assertEqual([m.line for m in bookmarks.visible(marks)], [4, 5])


class AnalyzerRoundFiveTests(unittest.TestCase):
	def test_jsx_self_closing_after_attribute(self):
		src = "function List({ items }) {\n  return <ul>{items.map(item => <Item key={item.id} {...item}/>)}</ul>;\n}\n\nfunction Other() {\n  return 1;\n}\n"
		a = Analysis(src, "js")
		self.assertEqual(a.problems(), [])
		self.assertEqual([(i.name, i.parent) for i in a.outline()], [("List", None), ("Other", None)])

	def test_regex_inside_template_interpolation(self):
		src = "function row(item) {\n  return `<td title=\"${item.title.replace(/\"/g, '&quot;')}\">${item.name}</td>`;\n}\n\nfunction after() {\n  return 2;\n}\n"
		a = Analysis(src, "js")
		self.assertEqual(a.problems(), [])
		self.assertEqual([i.name for i in a.outline()], ["row", "after"])

	def test_dart_integer_division_and_arrow_regex(self):
		src = "int cell(List<List<int>> board, int row, int i) {\n  return board[(row ~/ 3) * 3 + i ~/ 3][0];\n}\n"
		self.assertEqual(Analysis(src, "js").problems(), [])
		self.assertEqual(Analysis("const q = lines.filter(l => /^\"/.test(l));\nfunction after() {\n  return 2;\n}\n", "js").problems(), [])

	def test_css_at_rules(self):
		src = "body {\n  margin: 0;\n}\n\n@media screen and (max-width: 600px) {\n  .nav { display: none; }\n}\n\n@supports not (display: grid) {\n  .grid { float: left; }\n}\n"
		self.assertEqual(Analysis(src, "css").outline(), [])
		self.assertEqual(Analysis("@media only screen and (min-width: 768px) {\n  a { b: c; }\n}\n", "clike").outline(), [])

	def test_member_access_on_record_or_object(self):
		src = "function check(record) {\n  record.fields.forEach((field) => {\n    validate(\n      field,\n      rules,\n    );\n  });\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "js").outline()], ["check"])

	def test_go_struct_fields(self):
		src = "package cache\n\ntype Cache[K comparable, V any] struct {\n    data map[K]V\n    fn   Loader[K, V]\n    sub  *Subscriber[K]\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "clike").outline()], ["Cache"])

	def test_vs_code_title(self):
		self.assertEqual(analyzer.extension_from_title("main.rs - three.js - Visual Studio Code"), "rs")
		self.assertEqual(analyzer.extension_from_title("main - Copy.py - Notepad"), "py")

	def test_kotlin_nested_generic_bound(self):
		src = "fun <T : Comparable<T>> List<T>.isSorted(): Boolean {\n    return true\n}\n\nfun <T> List<T>.second(): T {\n    return this[1]\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "clike").outline()], ["isSorted", "second"])

	def test_rust_impl_trait_types(self):
		src = "fn make_adder(x: i32) -> impl Fn(i32) -> i32 {\n    move |y| x + y\n}\n\nfn show(item: impl Display) {\n    println!(\"{}\", item);\n}\n"
		self.assertEqual([(i.kind, i.name) for i in Analysis(src, "clike").outline()], [("function", "make_adder"), ("function", "show")])


class TypingRoundFiveTests(unittest.TestCase):
	CASES = [
		("const r = ", "/'/g;", "js", "const r = /'/g;|"),
		("", "if (/'/.test(s)) {", "js", "if (/'/.test(s)) {|}"),
		("const r = ", '/["]/;', "js", 'const r = /["]/;|'),
		("let s = ", '#"abc"#', "swift", 'let s = #"abc"#|'),
		("String s = ", '"""\nhello\n""";', "clike", 'String s = """\r\nhello\r\n""";|'),
		("string p = ", '@"C:\\temp\\";', "clike", 'string p = @"C:\\temp\\";|'),
		("let e: Box<", "(dyn Error + 'a)>;", "clike", "let e: Box<(dyn Error + 'a)>;|"),
	]

	def test_typing(self):
		for start, typed, lang, want in self.CASES:
			self.assertEqual(round4.type_text(start, typed, lang), want, typed)

	def test_swift_interpolation_keeps_its_closer(self):
		# 'let s = "\(count)"' with "f(" typed in front of count, then ")".
		text = 'let s = "\\(f(count))"'
		caret = text.index("count") + len("count") + 1
		self.assertFalse(editing.autoclose_skip(Analysis(text, "swift"), caret, ")"))

	def test_parameter_hints(self):
		src = "class Cache<K, V> {\n  constructor(size, ttl) {\n  }\n}\nconst c = new Cache<string, () => void>(10, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "js"), len(src)), ("Cache(size, ttl)", 2))
		src = "fn apply<F>(f: F, x: i32) -> i32 {\r\n    f(x)\r\n}\r\nfn main() { apply::<G>(g, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "clike"), len(src)), ("apply(f: F, x: i32)", 2))


class TypeOverAnnouncesTests(v040.V040Tests):
	def test_type_over_still_announces_and_lines_up(self):
		CONF["codeCompass"]["autoClose"] = True
		self.use("if x {\n    load(a))\n}\n", "x.js - Notepad")
		self.ed.caret = self.ed.text.index("))") + 1
		codeCompass._after_typed_character(self.ed, ")")
		self.assertEqual(self.ed.text, "if x {\n    load(a)\n}\n")
		self.assertIn("closes load paren", self.spoken())


# Keep the inherited V040 tests from running twice.
for _cls in (DocumentTests, TypeOverAnnouncesTests):
	for _name in list(vars(v040.V040Tests)):
		if _name.startswith("test_") and _name not in vars(_cls):
			setattr(_cls, _name, None)


if __name__ == "__main__":
	unittest.main()
