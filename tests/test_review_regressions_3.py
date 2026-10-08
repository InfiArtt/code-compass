# -*- coding: UTF-8 -*-
# Regression tests for the problems the regression hunter found in the
# reworked declaration scanning, the Markdown fallback and snippets.

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "addon", "globalPlugins", "codeCompass"))
sys.path.insert(0, os.path.join(HERE, ".."))

import build  # noqa: E402
import snippets  # noqa: E402
from analyzer import Analysis  # noqa: E402


def chain_at(src, lang, needle):
	a = Analysis(src, lang)
	return [i.name for i in a.declaration_chain(src.index(needle))]


def names(src, lang):
	return [i.name for i in Analysis(src, lang).outline()]


class LessThanTests(unittest.TestCase):
	def test_go_receive_channel(self):
		src = "func worker(jobs <-chan int) {\n\tprocess(jobs)\n}\n\nvar ready = make(chan bool)\n\nfunc main() {\n\tgo()\n}\n"
		self.assertEqual(chain_at(src, "clike", "var ready"), [])

	def test_go_send_channel_long_body(self):
		body = "".join("\tstep%d()\n" % i for i in range(60))
		src = "func pump(out chan<- int) {\n" + body + "\tfinish()\n}\n"
		self.assertEqual(chain_at(src, "clike", "finish()"), ["pump"])

	def test_kotlin_comparison(self):
		src = (
			"class User(val age: Int) {\n"
			"    fun isMinor() = age < 18\n"
			"\n"
			"    val name: String = \"\"\n"
			"    init {\n"
			"        check()\n"
			"    }\n"
			"}\n"
		)
		self.assertEqual(chain_at(src, "clike", "check()"), ["User"])

	def test_default_value_comparison(self):
		src = "function f(a = b < c) {\n  go();\n}\n"
		a = Analysis(src, "js")
		f = a.outline()[0]
		self.assertEqual((f.startLine, f.endLine), (0, 2))


class NoSemicolonTests(unittest.TestCase):
	def test_arrow_then_test_block(self):
		src = (
			"export const add = (a, b) => a + b\n"
			"\n"
			"describe('add', () => {\n"
			"  it('works', () => {\n"
			"    expect(add(1, 2)).toBe(3)\n"
			"  })\n"
			"})\n"
		)
		self.assertEqual(chain_at(src, "js", "expect("), [])

	def test_arrow_then_handler(self):
		src = "const double = (x) => x * 2\nwindow.onload = () => {\n  init()\n}\n"
		self.assertEqual(chain_at(src, "js", "init()"), [])

	def test_gradle_expression_function(self):
		src = 'fun getVersion() = "1.0"\ndependencies {\n    implementation("x")\n}\n'
		self.assertEqual(chain_at(src, "clike", "implementation"), [])


class WrappedExpressionTests(unittest.TestCase):
	def test_wrapped_jsx_and_condition_are_not_functions(self):
		src = (
			"export function Page() {\n"
			"  const content = (\n"
			"    <main>\n"
			"      <Title />\n"
			"    </main>\n"
			"  );\n"
			"  const isWide = (\n"
			"    width > 800 &&\n"
			"    height > 600\n"
			"  );\n"
			"  return content;\n"
			"}\n"
		)
		self.assertEqual(names(src, "js"), ["Page"])

	def test_wrapped_await(self):
		src = "async function load() {\n  let data = (\n    await fetch(url)\n  ).json();\n}\n"
		self.assertEqual(names(src, "js"), ["load"])

	def test_real_wrapped_arrow_still_found(self):
		src = "const build = async (\n  a,\n) => {\n  run(a);\n};\n"
		self.assertEqual(names(src, "js"), ["build"])


class NameTests(unittest.TestCase):
	def test_functions_named_base(self):
		self.assertEqual(names("class Url:\n    def base(self):\n        return 1\n\n    def full(self):\n        pass\n", "python"), ["Url", "base", "full"])
		self.assertEqual(names("func base(p string) string {\n\treturn p\n}\n", "clike"), ["base"])
		self.assertEqual(names("function base(url) {\n  return url;\n}\n", "js"), ["base"])

	def test_python_soft_keywords_and_func(self):
		self.assertEqual(names("def match(x):\n    pass\n\ndef func():\n    pass\n", "python"), ["match", "func"])

	def test_rust_inner_attribute(self):
		src = "#![allow(dead_code)]\n\nfn main() {\n    run();\n}\n"
		main = Analysis(src, "clike").outline()[0]
		self.assertEqual(main.startLine, 2)


class SpeedTests(unittest.TestCase):
	def test_many_declarations_linear(self):
		src = "".join("function f%d(x) {\n  return x + %d;\n}\n" % (i, i) for i in range(8000))
		start = time.perf_counter()
		outline = Analysis(src, "js").outline()
		elapsed = time.perf_counter() - start
		self.assertEqual(len(outline), 8000)
		self.assertLess(elapsed, 2.0, "outline took %.2fs" % elapsed)


class MarkdownTests(unittest.TestCase):
	def test_code_spans_are_left_alone(self):
		self.assertEqual(build.inline_markdown("a `**x**` b **y**"), "a <code>**x**</code> b <strong>y</strong>")

	def test_dunder_and_comment_markers(self):
		self.assertEqual(build.inline_markdown("`__init__` and `/* */`"), "<code>__init__</code> and <code>/* */</code>")

	def test_escapes_and_double_backticks(self):
		self.assertEqual(build.inline_markdown("Escaped \\`tick\\`"), "Escaped `tick`")
		self.assertEqual(build.inline_markdown("``code with ` tick`` end"), "<code>code with ` tick</code> end")

	def test_html_is_escaped(self):
		self.assertEqual(build.inline_markdown("a < b"), "a &lt; b")


class SnippetNameTests(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.folder)

	def test_idempotent(self):
		for raw in (" . $b*$R", "~$draft", "nul." + "x" * 120, "  name  ", "a" * 150):
			once = snippets.safe_name(raw)
			self.assertEqual(snippets.safe_name(once), once, raw)

	def test_saved_names_show_in_list(self):
		for name, ext in (("~$draft", "py"), ("desktop", "ini"), ("Thumbs", "db"), ("plain", "py")):
			snippets.save_snippet(self.folder, name, ext, "x\n")
		listed = sorted(s.label() for s in snippets.list_snippets(self.folder))
		self.assertEqual(listed, ["_Thumbs (db)", "_desktop (ini)", "draft (py)", "plain (py)"])

	def test_ansi_reads_exactly(self):
		path = os.path.join(self.folder, "greet.py")
		with open(path, "wb") as f:
			f.write("print('café €')\n".encode("cp1252"))
		self.assertEqual(snippets.list_snippets(self.folder)[0].read(), "print('café €')\n")

	def test_utf16_reads(self):
		path = os.path.join(self.folder, "wide.py")
		with open(path, "wb") as f:
			f.write("x = 'café'\r\n".encode("utf-16"))
		self.assertEqual(snippets.list_snippets(self.folder)[0].read(), "x = 'café'\r\n")

	def test_binary_file_is_refused(self):
		path = os.path.join(self.folder, "image.png")
		with open(path, "wb") as f:
			f.write(b"\x89PNG\x00\x00\x00binary")
		with self.assertRaises(ValueError):
			snippets.list_snippets(self.folder)[0].read()


if __name__ == "__main__":
	unittest.main()
