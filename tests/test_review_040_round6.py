# -*- coding: UTF-8 -*-
# Regression tests for the last 0.4.0 review round: history around
# control+G and saving, false duplicate and indentation problems, where
# am I's line count.

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_smoke as smoke  # noqa: E402
import test_flavour as flavour  # noqa: E402

codeCompass = flavour.codeCompass
MODS = flavour.MODS
Gesture = flavour.Gesture

import problems  # noqa: E402
from analyzer import Analysis  # noqa: E402


def duplicates(src):
	return [p.line for p in problems.duplicate_problems(Analysis(src, "js"))]


def indents(src):
	return [p.line for p in problems.indentation_problems(Analysis(src, "python"))]


class FalseDuplicateTests(unittest.TestCase):
	def test_named_function_expressions(self):
		self.assertEqual(duplicates("app.get('/', function handler(req, res) {\n  res.send('a');\n});\napp.post('/', function handler(req, res) {\n  res.send('b');\n});\n"), [])
		self.assertEqual(duplicates("Foo.prototype.toString = function toString() {\n  return 'a';\n};\nBar.prototype.toString = function toString() {\n  return 'b';\n};\n"), [])

	def test_static_and_instance(self):
		self.assertEqual(duplicates("class Parser {\n  static parse(text) {\n    return new Parser(text);\n  }\n  parse() {\n    return this.tree;\n  }\n}\n"), [])

	def test_accessors_with_modifiers(self):
		self.assertEqual(duplicates("class A {\n  public get name(): string {\n    return this._n;\n  }\n  public set name(v: string) {\n    this._n = v;\n  }\n}\n"), [])

	def test_overload_signatures(self):
		self.assertEqual(duplicates("function f(\n  a: string,\n  b: string,\n): string;\nfunction f(\n  a: number,\n  b: number,\n): number;\nfunction f(a: any, b: any): any {\n  return a;\n}\n"), [])
		self.assertEqual(duplicates("function f(a: string): string\nfunction f(a: number): number\nfunction f(a: any): any {\n  return a\n}\n"), [])
		self.assertEqual(duplicates("export declare function f(a: string): string\nexport declare function f(a: number): number\n"), [])

	def test_calls_with_typed_callbacks(self):
		self.assertEqual(duplicates("describe('api', () => {\n  it('loads', async (): Promise<void> => {\n    expect(1).toBe(1);\n  });\n  it('saves', async (): Promise<void> => {\n    expect(2).toBe(2);\n  });\n});\n"), [])
		self.assertEqual(duplicates("async function main() {\n  void refresh()\n  await wait(10)\n  void refresh()\n}\n"), [])

	def test_real_duplicates_still_found(self):
		self.assertEqual(duplicates("function load() {\n}\nfunction load() {\n}\n"), [2])
		self.assertEqual(duplicates("class A {\n  go() {\n  }\n  go() {\n  }\n}\n"), [3])


class FalseIndentTests(unittest.TestCase):
	def test_backslash_continuations(self):
		self.assertEqual(indents("def run():\n\twith open('a') as src, \\\n\t     open('b') as dst:\n\t\tdst.write(src.read())\n"), [])
		self.assertEqual(indents("def f():\n    x = a + \\\n\t\tb\n    return x\n"), [])

	def test_closer_and_comment_lines(self):
		self.assertEqual(indents("def f():\n\tx = g(1,\n\t      2\n\t      )\n\treturn x\n"), [])
		self.assertEqual(indents("def f():\n    x = 1\n\t# note\n    return x\n"), [])


PY = flavour.PY


class HistoryTests(flavour.FlavourCommandTests):
	def test_cancelled_go_to_keeps_history(self):
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		self.plugin.script_goBack(None)
		self.ed.script_ccGoToLine(Gesture("kb:control+g"))
		with mock.patch.object(smoke.FakeEditableText, "event_gainFocus", create=True):
			self.ed.event_gainFocus()
		self.run_later()
		self.plugin.script_goForward(None)
		self.assertEqual(self.line(), 0)
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 5)

	def test_history_follows_first_save(self):
		self.use(PY, "Untitled - Notepad")
		self.ed.appModule = types.SimpleNamespace(appName="notepad")
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		# control+S: the document is noted as it is saved.
		codeCompass._before_save(self.ed)
		self.use(PY, "main.py - Notepad")
		self.plugin.script_goBack(None)
		self.assertEqual(self.line(), 5)

	def test_history_of_a_replaced_document_is_dropped(self):
		self.use(PY, "*Untitled - Notepad")
		self.ed.appModule = types.SimpleNamespace(appName="notepad")
		self.at("helper(a)", 2)
		self.plugin.script_definition(None)
		# File > Open another file without saving.
		self.use("import sys\r\n" * 8, "other.py - Notepad")
		self.at("import sys")
		self.plugin.script_goBack(None)
		self.assertEqual(self.message(), "No earlier place to go back to")

	def test_where_am_i_count_with_allman_braces(self):
		self.use("class Program\r\n{\r\n    static void Main()\r\n    {\r\n        int x = 1;\r\n        x++;\r\n    }\r\n}\r\n", "Program.cs - Notepad")
		self.at("x++")
		self.plugin.script_whereAmI(None)
		self.assertIn("5 lines", self.message())
		self.use("class A {\r\n  method(a,\r\n         b) {\r\n    x();\r\n    y();\r\n  }\r\n}\r\n", "a.js - Notepad")
		self.at("y()")
		self.plugin.script_whereAmI(None)
		self.assertNotIn("class A, 7 lines", self.message())
		self.assertIn("5 lines", self.message())


for _name in list(vars(flavour.FlavourCommandTests)) + list(vars(flavour.v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(HistoryTests):
		setattr(HistoryTests, _name, None)


if __name__ == "__main__":
	unittest.main()
