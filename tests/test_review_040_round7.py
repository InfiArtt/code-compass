# -*- coding: UTF-8 -*-
# Regression tests for the final 0.4.0 review round: moved bookmarked
# lines, bookmarks of a new document saved after typing, typing over
# auto-closed brackets inside blocks, TypeScript overloads with object
# return types, and outline false positives; plus the nested-name warning.

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF

import bookmarks  # noqa: E402
import editing  # noqa: E402
import problems  # noqa: E402
from analyzer import Analysis  # noqa: E402
from bookmarks import Bookmark  # noqa: E402


def follow(marks, old, new):
	bookmarks.reanchor(marks, new, old)
	return [(m.line, m.text) for m in bookmarks.visible(marks)]


class MovedLineTests(unittest.TestCase):
	OLD = ["def f():", "    a = 1", "    b = 2", "    return a"]

	def test_line_moved_up_and_down(self):
		new = ["def f():", "    b = 2", "    a = 1", "    return a"]
		self.assertEqual(follow([Bookmark(2, "b = 2")], self.OLD, new), [(1, "b = 2")])
		self.assertEqual(follow([Bookmark(1, "a = 1")], self.OLD, new), [(2, "a = 1")])

	def test_moved_up_three_times(self):
		lines = ["l%d" % i for i in range(10)]
		marks = [Bookmark(5, "l5")]
		for _step in range(3):
			k = marks[0].line
			new = list(lines)
			new[k - 1], new[k] = new[k], new[k - 1]
			follow(marks, lines, new)
			lines = new
		self.assertEqual([(m.line, m.detached) for m in marks], [(2, False)])

	def test_restart_with_duplicates_edited_elsewhere(self):
		lines = ["new1", "new2", "a", "b", "c", "d", "e", "pass", "f", "pass", "g"]
		marks = [Bookmark(5, "pass"), Bookmark(7, "pass")]
		self.assertEqual(follow(marks, None, lines), [(7, "pass"), (9, "pass")])

	def test_indenting_a_large_file_is_quick(self):
		old = ["line %d" % i if i % 3 else "" for i in range(2900)]
		new = ["\t" + line if line else line for line in old]
		marks = [Bookmark(i, old[i].strip()) for i in range(1, 2900, 97)]
		start = time.perf_counter()
		bookmarks.reanchor(marks, new, old)
		self.assertLess(time.perf_counter() - start, 0.5)
		self.assertEqual(len(bookmarks.visible(marks)), len(marks))


class OutlineAndProblemTests(unittest.TestCase):
	def test_overloads_with_object_return_types(self):
		src = "export function useThing(id: string): { data: string };\nexport function useThing(id: number): { data: string };\nexport function useThing(id: any): { data: string } {\n  return { data: String(id) };\n}\n"
		self.assertEqual(problems.duplicate_problems(Analysis(src, "js")), [])
		src = "class Store {\n  find(id: string): { id: string };\n  find(ids: string[]): { id: string };\n  find(x: any): any {\n    return x;\n  }\n}\n"
		self.assertEqual(problems.duplicate_problems(Analysis(src, "js")), [])

	def test_hint_after_arrows(self):
		src = "function identity<T>(value: T): T {\n  return value;\n}\nconst rows = items.map((item) => ("
		self.assertIsNone(editing.parameter_hint(Analysis(src, "js"), len(src)))
		src = "fn wrap<T>(x: T) -> T { x }\nfn g() -> ("
		self.assertIsNone(editing.parameter_hint(Analysis(src, "clike"), len(src)))

	def test_python_method_hint_leaves_out_self(self):
		src = "class Toko:\n    def tambah(self, nama, harga, stok=1):\n        pass\n\n    @classmethod\n    def buat(cls, nama):\n        pass\n\ntoko.tambah(\"Kopi\", 45000, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "python"), len(src)), ("tambah(nama, harga, stok=1)", 3))
		src2 = src[:src.rindex("toko.")] + "Toko.buat("
		self.assertEqual(editing.parameter_hint(Analysis(src2, "python"), len(src2)), ("buat(nama)", 1))

	def test_hint_from_the_name_paren_or_after_the_call(self):
		src = "def hitung(harga, jumlah):\n    pass\n\ntotal = hitung(15000, 3)\nprint(total)\n"
		a = Analysis(src, "python")
		call = src.index("hitung(15000")
		self.assertEqual(editing.parameter_hint(a, call + 2), ("hitung(harga, jumlah)", 1))
		self.assertEqual(editing.parameter_hint(a, src.index("(15000")), ("hitung(harga, jumlah)", 1))
		self.assertEqual(editing.parameter_hint(a, src.index("3)") + 2), ("hitung(harga, jumlah)", 2))
		self.assertIsNone(editing.parameter_hint(a, src.index("total =")))
		self.assertIsNone(editing.called_name(a, src.index("total =")))
		self.assertEqual(editing.called_name(a, src.index("print") + 1), "print")

	def test_function_callbacks_are_not_functions(self):
		self.assertEqual(Analysis('describe("Store", function () {\n  it("loads", function () {\n    expect(1).toBe(1);\n  });\n});\n', "js").outline(), [])
		self.assertEqual(Analysis("setTimeout(function () {\n  go();\n}, 100);\n", "js").outline(), [])

	def test_return_type_with_arrow(self):
		src = "class Bus {\n  subscribe(cb: (x: number) => void): () => void {\n    return () => {};\n  }\n  emit(x: number): void {\n  }\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "js").outline()], ["Bus", "subscribe", "emit"])

	def test_go_map_and_chan(self):
		src = "func main() {\n\tcount := func(words []string) map[string]int {\n\t\tm := map[string]int{}\n\t\treturn m\n\t}\n\t_ = count\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "clike").outline()], ["main"])

	def test_enum_constants(self):
		src = "public enum Planet {\n    MERCURY(3.303e+23,\n            2.4397e6),\n    VENUS(4.869e+24, 6.0518e6);\n    private final double mass;\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "clike").outline()], ["Planet"])

	def test_nested_function_with_the_same_name(self):
		src = "def main():\n    g = 1\n    def main():\n        pass\n\nif __name__ == '__main__':\n    main()\n"
		found = problems.find_problems(Analysis(src, "python"))
		self.assertEqual([(p.line, p.kind) for p in found], [(2, "warning")])
		self.assertEqual(codeCompass._problem_label(found[0]), "line 3, warning: main is declared inside main, a function with the same name")
		self.assertEqual(problems.nested_name_warnings(Analysis("def a():\n    def b():\n        pass\n", "python")), [])


PY = "def a():\r\n    pass\r\n\r\ndef b():\r\n    x = 1\r\n    return x\r\n"


class EditorTests(v040.V040Tests):
	def setUp(self):
		super(EditorTests, self).setUp()
		codeCompass._autoClosed.clear()
		CONF["codeCompass"]["autoClose"] = True

	def type(self, chars):
		for ch in chars:
			self.ed.text = self.ed.text[:self.ed.caret] + ch + self.ed.text[self.ed.caret:]
			self.ed.caret += 1
			self.ed.selection = (self.ed.caret, self.ed.caret)
			codeCompass._after_typed_character(self.ed, ch)

	def test_type_over_inside_a_block(self):
		self.use("function f() {\r\n  \r\n}\r\n", "x.js - Notepad")
		self.ed.caret = self.ed.text.index("  \r\n") + 2
		self.type("const o = {a: 1};")
		self.assertEqual(self.ed.text, "function f() {\r\n  const o = {a: 1};\r\n}\r\n")
		self.use("foo(\r\n    \r\n", "x.py - Notepad")
		self.ed.caret = self.ed.text.index("    \r\n") + 4
		self.type("bar(x),")
		self.assertEqual(self.ed.text, "foo(\r\n    bar(x),\r\n")

	def test_a_closer_that_was_not_added_stays(self):
		# An existing ")" closing a call opened on an earlier line.
		self.use("foo(\r\n  bar(x)\r\n", "x.js - Notepad")
		self.ed.caret = self.ed.text.index("x)") + 1
		self.type(")")
		self.assertEqual(self.ed.text, "foo(\r\n  bar(x))\r\n")

	def test_untitled_bookmarks_follow_a_save_after_typing(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		path = os.path.join(folder, "main.py")
		codeCompass._bookmarkStore = bookmarks.Store(os.path.join(folder, "bookmarks.json"))
		codeCompass._bookmarkKeys.clear()
		codeCompass._bookmarkSeen.clear()
		self.addCleanup(setattr, codeCompass, "_bookmarkStore", None)
		with mock.patch.object(codeCompass.filepath, "find_file", return_value=None) as find:
			self.use(PY, "Untitled - Notepad")
			self.at("def b")
			self.plugin.script_toggleBookmark(None)
			typed = PY + "print(b())\r\n"
			self.use(typed, "*Untitled - Notepad")
			codeCompass._before_save(self.ed)
			with open(path, "w", encoding="utf-8", newline="") as f:
				f.write(typed)
			find.return_value = path
			self.use(typed, "main.py - Notepad")
			MODS["api"].getFocusObject.return_value = self.ed
			codeCompass._after_save(self.ed)
			self.at("def a")
			self.plugin.script_nextBookmark(None)
		self.assertEqual(self.ed.text.count("\n", 0, self.ed.caret), 3)
		self.assertTrue(codeCompass._bookmarkStore.has(os.path.normcase(os.path.abspath(path))))


for _cls in (EditorTests,):
	for _name in list(vars(v040.V040Tests)):
		if _name.startswith("test_") and _name not in vars(_cls):
			setattr(_cls, _name, None)


if __name__ == "__main__":
	unittest.main()
