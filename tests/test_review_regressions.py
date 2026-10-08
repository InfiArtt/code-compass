# -*- coding: UTF-8 -*-
# Regression tests for problems found in the pre-publish review of 0.3.0.

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))

import snippets  # noqa: E402
from analyzer import Analysis  # noqa: E402


def names(items):
	return [i.name for i in items]


def chain_at(src, lang, needle):
	a = Analysis(src, lang)
	return names(a.declaration_chain(src.index(needle)))


def saved_range(src, lang, name):
	a = Analysis(src, lang)
	item = [i for i in a.outline() if i.name == name][0]
	start, end = a.declaration_range(item)
	return src[start:end]


class ParentTests(unittest.TestCase):
	def test_python_function_after_closed_class_is_top_level(self):
		src = (
			"class Foo:\n"
			"    def m(self):\n"
			"        pass\n"
			"try:\n"
			"    import fast\n"
			"except ImportError:\n"
			"    def speedup(x):\n"
			"        return x\n"
		)
		a = Analysis(src, "python")
		speedup = [i for i in a.outline() if i.name == "speedup"][0]
		self.assertIsNone(speedup.parentItem)
		self.assertEqual(names(a.outline()[0].children), ["m"])
		self.assertEqual(chain_at(src, "python", "return x"), ["speedup"])

	def test_js_function_after_closed_class_is_top_level(self):
		src = "class A {\n  m() {}\n}\nif (x) {\n  function b() {\n    go();\n  }\n}\n"
		a = Analysis(src, "js")
		b = [i for i in a.outline() if i.name == "b"][0]
		self.assertIsNone(b.parentItem)
		self.assertEqual(chain_at(src, "js", "go()"), ["b"])


class BodyBraceTests(unittest.TestCase):
	def test_destructured_parameters(self):
		src = "function Button({ label, onClick }) {\n  return label;\n}\n"
		self.assertEqual(saved_range(src, "js", "Button"), src)

	def test_default_object_parameter(self):
		src = "function f(opts = {}) {\n  go(opts);\n}\n"
		self.assertEqual(saved_range(src, "js", "f"), src)

	def test_declaration_without_body_does_not_swallow_the_next(self):
		src = "data class Point(val x: Int, val y: Int)\n\nfun main() {\n    println(Point(1, 2))\n}\n"
		self.assertEqual(saved_range(src, "clike", "Point"), "data class Point(val x: Int, val y: Int)\n")

	def test_forward_declaration(self):
		src = "class Widget;\nclass Window {\n  Widget* w;\n};\n"
		self.assertEqual(saved_range(src, "clike", "Widget"), "class Widget;\n")
		self.assertEqual(saved_range(src, "clike", "Window"), "class Window {\n  Widget* w;\n};\n")

	def test_one_line_arrow_function(self):
		src = "const double = (x) => x * 2;\nfunction main() {\n  double(2);\n}\n"
		self.assertEqual(saved_range(src, "js", "double"), "const double = (x) => x * 2;\n")


class WrappedSignatureTests(unittest.TestCase):
	def test_prettier_style(self):
		src = "function createUser(\n  name,\n  email,\n) {\n  save(name, email);\n}\n"
		self.assertEqual(chain_at(src, "js", "save("), ["createUser"])
		self.assertEqual(saved_range(src, "js", "createUser"), src)

	def test_csharp_allman_wrapped(self):
		src = "class App\n{\n    public void Run(\n        int a,\n        int b)\n    {\n        Go();\n    }\n}\n"
		self.assertEqual(chain_at(src, "clike", "Go()"), ["App", "Run"])

	def test_go_wrapped(self):
		src = "func handle(\n\tw http.ResponseWriter,\n\tr *http.Request,\n) {\n\tw.Write(nil)\n}\n"
		self.assertEqual(chain_at(src, "clike", "w.Write"), ["handle"])

	def test_java_throws_on_next_line(self):
		src = "class A {\n    void run()\n        throws IOException {\n        go();\n    }\n}\n"
		self.assertEqual(chain_at(src, "clike", "go()"), ["A", "run"])


class MultilineStringTests(unittest.TestCase):
	def test_python_string_at_column_zero(self):
		src = 'def sql():\n    query = """\nSELECT *\nFROM t\n"""\n    return query\n'
		self.assertEqual(saved_range(src, "python", "sql"), src)
		self.assertEqual(chain_at(src, "python", "return query"), ["sql"])


class DecoratorTests(unittest.TestCase):
	def test_python_decorators_are_saved(self):
		src = (
			"import x\n"
			"\n"
			"@dataclass\n"
			"@app.route(\n"
			"    '/x',\n"
			"    methods=['GET'])\n"
			"class Point:\n"
			"    x: int\n"
		)
		self.assertTrue(saved_range(src, "python", "Point").startswith("@dataclass\n@app.route("))

	def test_caret_on_decorator_line(self):
		src = "class A:\n    @property\n    def size(self):\n        return 1\n"
		self.assertEqual(chain_at(src, "python", "@property"), ["A", "size"])

	def test_java_annotation(self):
		src = "class A {\n    @Override\n    public String toString() {\n        return \"a\";\n    }\n}\n"
		self.assertTrue(saved_range(src, "clike", "toString").startswith("    @Override\n"))


class IifeTests(unittest.TestCase):
	def test_iife_after_one_line_declaration(self):
		src = "const log = (m) => console.log(m);\n(async () => {\n  await go();\n})();\n"
		self.assertEqual(chain_at(src, "js", "await go()"), [])
		self.assertEqual(saved_range(src, "js", "log"), "const log = (m) => console.log(m);\n")


class SnippetRobustnessTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.folder)

	def test_ansi_file_reads(self):
		path = os.path.join(self.folder, "greet.py")
		with open(path, "wb") as f:
			f.write("print('caf\u00e9')\n".encode("cp1252"))
		snip = snippets.list_snippets(self.folder)[0]
		self.assertIn("caf", snip.read())

	def test_desktop_ini_and_hidden_files_are_not_snippets(self):
		for fn in ("desktop.ini", ".hidden.py", "real.py"):
			with open(os.path.join(self.folder, fn), "w") as f:
				f.write("x")
		self.assertEqual([s.name for s in snippets.list_snippets(self.folder)], ["real"])

	def test_device_names_are_renamed(self):
		for name in ("nul", "CON", "aux", "com1", "lpt9", "prn"):
			self.assertNotEqual(snippets.safe_name(name).upper(), name.upper(), name)
		self.assertEqual(snippets.safe_name("console"), "console")
		path = snippets.save_snippet(self.folder, "nul", "py", "x\n")
		self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
	unittest.main()
