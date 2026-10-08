# -*- coding: UTF-8 -*-
# Regression tests for the fourth 0.4.0 review round: one-line strings with
# unclosed fields, regex literals, raw strings, declarations the outline
# missed or invented, typing quotes and brackets with auto-close, and
# dialog fields in the editor's own windows.

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402
import test_plugin_smoke as smoke  # noqa: E402

codeCompass = v040.codeCompass

from analyzer import Analysis  # noqa: E402
import analyzer  # noqa: E402
import editing  # noqa: E402


def names(src, lang):
	return [i.name for i in Analysis(src, lang).outline()]


def items(src, lang):
	return [(i.kind, i.name, i.startLine, i.endLine, i.parent) for i in Analysis(src, lang).outline()]


def renamed(src, lang, name, new):
	return editing.renamed_text(Analysis(src, lang), name, new)


class StringTests(unittest.TestCase):
	def test_unclosed_field_ends_at_the_line(self):
		src = 'def a():\n    print(f"Hello {name")\n\ndef b():\n    pass\n\ndef c():\n    d = {1: 2}\n\ndef e():\n    pass\n'
		self.assertEqual(names(src, "python"), ["a", "b", "c", "e"])
		self.assertEqual(names('x = f"{x:>10"\ndef b():\n    pass\n', "python"), ["b"])
		self.assertEqual(names('let s = "a \\(x"\nfunc foo() {\n}\nfunc bar() {\n}\n', "swift"), ["foo", "bar"])

	def test_many_unclosed_fields(self):
		Analysis('x = f"{a\n' * 3000, "python").outline()

	def test_regex_literals(self):
		src = 'const s = t.replace(/`/g, "\'");\nfunction foo() {\n}\nfunction bar() {\n}\n'
		self.assertEqual(names(src, "js"), ["foo", "bar"])
		self.assertEqual(Analysis(src, "js").problems(), [])
		division = "const r = a / b / c;\nconst q = (x) / 2;\n"
		self.assertEqual(Analysis(division, "js").code, division)
		self.assertEqual(Analysis("const L = () => <ul>{items.map(i => <li>{i}</li>)}</ul>;\n", "js").problems(), [])

	def test_swift_raw_strings(self):
		self.assertEqual(Analysis('let s = #"say "hi (x"#\nfunc foo() {\n}\n', "swift").problems(), [])
		self.assertEqual(renamed('let s = #"say "hello" (x"#\nlet hello = 1\n', "swift", "hello", "bye")[1], 1)
		self.assertEqual(
			renamed('let value = 1\nlet s = #"a \\#(value) b"#\n', "swift", "value", "v2"),
			('let v2 = 1\nlet s = #"a \\#(v2) b"#\n', 2))

	def test_python_raw_f_strings(self):
		self.assertEqual(
			renamed('def f(name):\n    return rf"{root}\\{name}"\n', "python", "name", "nm"),
			('def f(nm):\n    return rf"{root}\\{nm}"\n', 2))
		self.assertEqual(
			renamed('key = 1\npat = rf"\\{{(?P<key>[a-z]+)\\}}"\n', "python", "key", "k2"),
			('k2 = 1\npat = rf"\\{{(?P<key>[a-z]+)\\}}"\n', 1))

	def test_extension_from_the_file_name_only(self):
		self.assertEqual(analyzer.extension_from_title("C:\\dev\\three.js\\README.md - Notepad++"), "md")
		self.assertEqual(analyzer.extension_from_title("main.py.txt - Notepad"), "py")


class OutlineTests(unittest.TestCase):
	def test_class_words_in_parameters(self):
		self.assertEqual(
			items("export function saveRecord(record) {\n  validate(\n    record,\n    schema,\n  );\n  return record;\n}\n", "js"),
			[("function", "saveRecord", 0, 6, None)])
		self.assertEqual(names("class Repo {\n  void save(Record record)\n      throws IOException {\n    validate(\n        record);\n  }\n}\n", "clike"), ["Repo", "save"])
		self.assertEqual(names("func store(_ object: NSManagedObject) {\n    precondition(\n        true)\n}\n", "swift"), ["store"])
		self.assertEqual(names("class A {\n    companion object {\n        fun make(\n            x: Int,\n        ) = A()\n    }\n}\n", "clike"), ["A", "make"])

	def test_decorators_on_the_same_line(self):
		src = "export class Cmp {\n  @HostListener('window:resize', ['$event']) onResize(event) {\n    this.w = 1;\n  }\n  @Input() set value(v) {\n    this.v = v;\n  }\n}\n"
		self.assertEqual(names(src, "js"), ["Cmp", "onResize", "value"])
		src = "public class T {\n  @Override public String toString() {\n    return \"x\";\n  }\n  @Test void works() {\n  }\n}\n"
		self.assertEqual(names(src, "clike"), ["T", "toString", "works"])

	def test_one_line_methods(self):
		self.assertEqual(
			items("class Box {\n  get value() { return this._v; }\n  size() { return 1; }\n  long() {\n    return 2;\n  }\n}\n", "js"),
			[("class", "Box", 0, 6, None), ("function", "value", 1, 1, "Box"), ("function", "size", 2, 2, "Box"), ("function", "long", 3, 5, "Box")])
		self.assertEqual(names("class W {\npublic:\n    int get() const { return x_; }\n    void set(int v) { x_ = v; }\n};\n", "clike"), ["W", "get", "set"])
		self.assertEqual(names("fun main() {\n    repeat(3) { println(it) }\n}\n", "clike"), ["main"])

	def test_go_rust_and_generic_declarations(self):
		go = "type Server struct {\n\taddr string\n}\n\ntype Store interface {\n\tGet(key string) string\n}\n\nfunc Map[T any](xs []T, f func(T) T) []T {\n\treturn xs\n}\n"
		self.assertEqual(names(go, "clike"), ["Server", "Store", "Map"])
		rust = "impl<T: Display> fmt::Display for Wrapper<T> {\n    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {\n        write!(f, \"x\")\n    }\n}\n"
		self.assertEqual(items(rust, "clike"), [("impl", "Wrapper", 0, 4, None), ("function", "fmt", 1, 3, "Wrapper")])
		self.assertEqual(names("class C {\n    public T Find<T>(int id) where T : class {\n        return null;\n    }\n}\n", "clike"), ["C", "Find"])
		self.assertEqual(names("fun <T> List<T>.second(): T = this[1]\nfun String.shout(): String {\n    return this\n}\n", "clike"), ["second", "shout"])
		self.assertEqual(items("const id = <T,>(x: T): T => {\n  return x;\n};\n", "js"), [("function", "id", 0, 2, None)])


def type_text(start, typed, lang):
	"""Type like Notepad with auto-close on, as _after_typed_character does;
	"\\n" is a plain line break."""
	text, caret = start, len(start)
	for ch in typed:
		if ch == "\n":
			text = text[:caret] + "\r\n" + text[caret:]
			caret += 2
			continue
		text = text[:caret] + ch + text[caret:]
		caret += 1
		a = Analysis(text, lang)
		if editing.stale_apostrophe(a, caret, ch):
			text = text[:caret] + text[caret + 1:]
			a = Analysis(text, lang)
		if editing.autoclose_skip(a, caret, ch):
			text = text[:caret] + text[caret + 1:]
		elif editing.should_autoclose(a, caret, ch):
			text = text[:caret] + editing.AUTO_PAIRS[ch] + text[caret:]
	return text[:caret] + "|" + text[caret:]


class TypingTests(unittest.TestCase):
	CASES = [
		("def f():\r\n    ", '"""Doc.\n    More.\n    """', "python", 'def f():\r\n    """Doc.\r\n    More.\r\n    """|'),
		("let s = ", '"""\nab\n"""', "swift", 'let s = """\r\nab\r\n"""|'),
		("const s = ", "`a\nb`;", "js", "const s = `a\r\nb`;|"),
		("x = ", '"abc"', "python", 'x = "abc"|'),
		("x = ", '""', "python", 'x = ""|'),
		("", 'print("hi")', "python", 'print("hi")|'),
		("", "# don't 'x'", "python", "# don't 'x'|"),
		("", 'print(f"Total: {len(items)}")', "python", 'print(f"Total: {len(items)}")|'),
		("s = ", 'f"{a[0]}"', "python", 's = f"{a[0]}"|'),
		("const s = `a ", "${f(x)}", "js", "const s = `a ${f(x)}|"),
		('let s = "', "\\(f(x))", "swift", 'let s = "\\(f(x))|'),
		("", "fn f<'a>(x: &'a str) -> &'a str {", "clike", "fn f<'a>(x: &'a str) -> &'a str {|}"),
		("    ", "'outer: loop {", "clike", "    'outer: loop {|}"),
		("char c = ", "'a';", "clike", "char c = 'a';|"),
		("char c = ", "'\\n';", "clike", "char c = '\\n';|"),
		("", "f(a[1], {b: 2})", "js", "f(a[1], {b: 2})|"),
	]

	def test_typing(self):
		for start, typed, lang, want in self.CASES:
			self.assertEqual(type_text(start, typed, lang), want, typed)


class SignatureTests(unittest.TestCase):
	def test_generic_constructor_calls(self):
		src = "class Box<T> {\r\n    public Box(T value) {\r\n    }\r\n}\r\nBox<Integer> b = new Box<>("
		self.assertEqual(editing.parameter_hint(Analysis(src, "clike"), len(src)), ("Box(T value)", 1))
		src = "class Cache<K, V> {\n  constructor(size, ttl) {\n  }\n}\nconst c = new Cache<string, number>(10, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "js"), len(src)), ("Cache(size, ttl)", 2))

	def test_arrow_inside_generic_bound(self):
		src = "fn apply<F: Fn(i32) -> i32>(f: F, x: i32) -> i32 {\r\n    f(x)\r\n}\r\nfn main() { apply(g, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "clike"), len(src)), ("apply(f: F, x: i32)", 2))


class OverlayTests(unittest.TestCase):
	def setUp(self):
		v040.CONF["codeCompass"] = smoke.default_config()
		self.plugin = codeCompass.GlobalPlugin()

	def test_single_line_fields_keep_their_keys(self):
		obj = types.SimpleNamespace(
			role="editable", appModule=types.SimpleNamespace(appName="notepad"), windowClassName="Edit", windowHandle=5)
		clsList = [smoke.FakeEditableText]
		with mock.patch.object(codeCompass.edit_control, "is_single_line", return_value=True) as single:
			self.plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
		single.assert_called_once_with("Edit", 5)
		self.assertNotIn(codeCompass.CodeEditor, clsList)
		with mock.patch.object(codeCompass.edit_control, "is_single_line", return_value=False):
			self.plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
		self.assertIs(clsList[0], codeCompass.CodeEditor)

	def test_is_single_line_needs_an_edit_class(self):
		self.assertFalse(codeCompass.edit_control.is_single_line("Scintilla", 5))
		self.assertFalse(codeCompass.edit_control.is_single_line("Edit", None))


class RunHintTests(v040.V040Tests):
	def test_run_error_hint_in_notepad_plus_plus(self):
		self.use("print(1)\nx = 1 / 0\n", "C:\\p\\main.py - Notepad++")
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError"}}, 7, "main.py", None, "notepad++")
		self.assertIn("shift+C", self.message())
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError"}}, 7, "main.py", None, "notepad")
		self.assertIn("Press F8", self.message())


# Keep the inherited V040 tests from running twice.
for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(RunHintTests):
		setattr(RunHintTests, _name, None)


if __name__ == "__main__":
	unittest.main()
