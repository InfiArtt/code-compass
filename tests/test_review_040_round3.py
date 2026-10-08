# -*- coding: UTF-8 -*-
# Regression tests for the third 0.4.0 review round: string interpolation,
# declaration headers, typing over quotes, notes, signatures, file paths and
# runs.

import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))
import test_plugin_v040 as v040  # noqa: E402

codeCompass = v040.codeCompass
MODS = v040.MODS
CONF = v040.CONF
Gesture = v040.Gesture

from analyzer import Analysis  # noqa: E402
import analyzer  # noqa: E402
import editing  # noqa: E402
import filepath  # noqa: E402


def outline_names(src, lang):
	return [i.name for i in Analysis(src, lang).outline()]


def outline_range(src, lang, name):
	item = next(i for i in Analysis(src, lang).outline() if i.name == name)
	return item.startLine, item.endLine


class InterpolationTests(unittest.TestCase):
	def rename(self, src, lang, name, new):
		a = Analysis(src, lang)
		self.assertEqual(a.problems(), [])
		return editing.renamed_text(a, name, new)[0]

	def test_dict_key_in_f_string(self):
		src = "name = row['name']\r\nprint(f\"{row['name']} is {name}\")\r\nprint(name)"
		self.assertEqual(
			self.rename(src, "python", "name", "user"),
			"user = row['name']\r\nprint(f\"{row['name']} is {user}\")\r\nprint(user)",
		)

	def test_format_specs_are_not_code(self):
		self.assertEqual(self.rename("x = 255\nprint(f\"{x:x}\")\n", "python", "x", "v"), "v = 255\nprint(f\"{v:x}\")\n")
		self.assertEqual(self.rename("d = now()\nprint(f\"{d:%Y-%m-%d}\")\n", "python", "d", "day"), "day = now()\nprint(f\"{day:%Y-%m-%d}\")\n")
		self.assertEqual(self.rename("r = 5\nprint(f\"{r!r}\")\n", "python", "r", "radius"), "radius = 5\nprint(f\"{radius!r}\")\n")

	def test_nested_spec_field_and_comparison(self):
		self.assertEqual(self.rename("s = 1\nw = 5\nprint(f\"{s:>{w}s}\")\n", "python", "w", "width"), "s = 1\nwidth = 5\nprint(f\"{s:>{width}s}\")\n")
		self.assertEqual(self.rename("a = 1\nb = 2\nprint(f\"{a <= b} {a != b}\")\n", "python", "b", "c"), "a = 1\nc = 2\nprint(f\"{a <= c} {a != c}\")\n")

	def test_named_escape_is_text(self):
		self.assertEqual(self.rename("DASH = 1\nprint(f\"a\\N{EM DASH}b\")\n", "python", "DASH", "SEP"), "SEP = 1\nprint(f\"a\\N{EM DASH}b\")\n")

	def test_brackets_in_nested_strings(self):
		self.assertEqual(Analysis("depth = 2\r\nprint(f\"{'(' * depth}\")\r\nfoo(x)\r\n", "python").problems(), [])
		self.assertEqual(Analysis("const s = `${a.split(\"(\")[0]}`;\n", "js").problems(), [])
		self.assertEqual(Analysis("let r = #\"\\(([^)]*)\\)\"#\n", "swift").problems(), [])

	def test_nested_template_and_swift_dict(self):
		src = "function list(items) {\n  const s = `${items.map(i => `<li>${i}</li>`).join(',')}`;\n  return s;\n}\n"
		a = Analysis(src, "js")
		self.assertEqual(a.problems(), [])
		self.assertEqual(len(editing.occurrences(a, "i")), 2)
		a = Analysis("let d = [\"k\": 1]\nprint(\"value: \\(d[\"k\"]!)\")\n", "swift")
		self.assertEqual(a.problems(), [])
		self.assertEqual(len(editing.occurrences(a, "d")), 2)

	def test_no_outline_from_multi_line_strings(self):
		self.assertEqual(outline_names("const page = `\n  <h1>${title}</h1>\n  ${header} ${renderItems(items)}\n`;\nfunction main() {\n}\n", "js"), ["main"])
		self.assertEqual(outline_names("let s = \"\"\"\n    \\(greeting) \\(format(name))\n    \"\"\"\nfunc main() {\n}\n", "swift"), ["main"])


class DeclarationHeaderTests(unittest.TestCase):
	def test_comparison_in_default_value(self):
		self.assertEqual(outline_range("fun f(x: Boolean = a<b) {\n    check()\n}\nval top = 1\nfun g() {\n}\n", "clike", "f"), (0, 2))

	def test_arrow_returning_object_types(self):
		self.assertEqual(outline_range("const load = async (id: string): Promise<{ ok: boolean }> => {\n  return run(id);\n};\n", "js", "load"), (0, 2))
		self.assertEqual(outline_range("const rows = (): Array<{ id: number }> => {\n  return [];\n};\n", "js", "rows"), (0, 2))
		self.assertEqual(outline_range("const load = async (\n  id: string,\n): Promise<{ ok: boolean }> => {\n  return run(id);\n};\n", "js", "load"), (0, 4))

	def test_generic_defaults(self):
		self.assertEqual(outline_range("function useX<T = {}>(x: T) {\n  check();\n}\n", "js", "useX"), (0, 2))
		self.assertEqual(outline_range("function useX<P extends object = { a: number }>(p: P) {\n  check();\n}\n", "js", "useX"), (0, 2))

	def test_expression_body_comparison(self):
		src = "class U {\n    fun isMinor() = age<18\n    init {\n        check()\n    }\n}\n"
		self.assertEqual([i.name for i in Analysis(src, "clike").declaration_chain(src.index("check()"))], ["U"])

	def test_decorators_with_nested_arguments(self):
		self.assertEqual(outline_range("@given(st.lists(st.integers()))\ndef test_sorted(xs):\n    pass\n", "python", "test_sorted"), (0, 2))
		self.assertEqual(outline_range("@Component({\n  selector: 'x',\n  template: f(g(1)),\n})\nexport class App {\n}\n", "js", "App"), (0, 5))
		self.assertEqual(outline_range("class C {\n  @Input() name: string;\n  @HostListener('click')\n  onClick() {\n    go();\n  }\n}\n", "js", "onClick"), (2, 5))

	def test_attributes_before_declarations(self):
		self.assertEqual(outline_names("public class H {\n    [HttpGet] public IActionResult Index() {\n        return View();\n    }\n}\n", "clike"), ["H", "Index"])
		self.assertEqual(outline_names("class V {\n    [[nodiscard]] bool empty() const {\n        return true;\n    }\n};\n", "clike"), ["V", "empty"])
		self.assertEqual(outline_names("[[nodiscard]] int compute(int a) {\n    return a;\n}\n", "clike"), ["compute"])
		self.assertEqual(outline_names("class M {\n    [Required, StringLength(50)]\n    public string Name { get; set; }\n}\n", "clike"), ["M"])

	def test_heritage_clause_on_next_line(self):
		src = "export class AppComponent\n  implements OnInit, OnDestroy {\n  load(\n    id: string,\n  ) {\n    go();\n  }\n}\n"
		self.assertEqual(outline_names(src, "js"), ["AppComponent", "load"])
		self.assertEqual(outline_names("class Foo\n  extends Bar {\n  render(\n    a,\n  ) {\n    go();\n  }\n}\n", "js"), ["Foo", "render"])


class EditingRoundThreeTests(unittest.TestCase):
	def test_quote_type_over_only_when_closing(self):
		# The typed quote closed "abc": the one after the caret goes.
		self.assertTrue(editing.autoclose_skip(Analysis('x = "abc""\n', "python"), 9, '"'))
		# The typed quote opens a string before an existing one: keep both.
		self.assertFalse(editing.autoclose_skip(Analysis('x = ""b"\n', "python"), 5, '"'))
		# A quote typed inside a comment is text.
		self.assertFalse(editing.autoclose_skip(Analysis('x = 1  # say ""\n', "python"), 14, '"'))

	def test_todos_only_in_comments(self):
		src = "TODO = 1\nx = TODO  # later\n# TODO: fix it\ns = 'FIXME not a note'\n"
		self.assertEqual(editing.todos(Analysis(src, "python")), [(2, "TODO", "fix it")])

	def test_kotlin_primary_constructor_and_init_block(self):
		src = "class User(val name: String, val age: Int) {\n    init {\n        check()\n    }\n}\nval u = User(\"a\", "
		self.assertEqual(editing.parameter_hint(Analysis(src, "clike"), len(src)), ("User(val name: String, val age: Int)", 2))

	def test_java_constructor_by_class_name(self):
		src = "class Shop {\n    Shop(String name, int price) {\n        this.name = name;\n    }\n}\nShop s = new Shop(\"a\", "
		self.assertEqual(editing.parameter_hint(Analysis(src, "clike"), len(src)), ("Shop(String name, int price)", 2))

	def test_python_class_bases_are_not_parameters(self):
		src = "class Shop(Base):\n    def __init__(self, name, price):\n        pass\n\nShop('a', "
		self.assertEqual(editing.parameter_hint(Analysis(src, "python"), len(src)), ("Shop(name, price)", 2))

	def test_lambda_is_a_name_outside_python(self):
		src = "function f(a, b) {\n}\nf(lambda, "
		self.assertEqual(editing.parameter_hint(Analysis(src, "js"), len(src)), ("f(a, b)", 2))


class FilePathRoundThreeTests(unittest.TestCase):
	def setUp(self):
		self.root = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.root, True)

	def write(self, rel, data):
		path = os.path.join(self.root, rel)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "wb") as f:
			f.write(data)
		return path

	def test_application_name_with_hyphen(self):
		self.assertEqual(filepath.title_file("main.py - Bloc-notes"), "main.py")
		self.assertEqual(analyzer.extension_from_title("main.py - Bloc-notes"), "py")
		self.assertEqual(filepath.title_file("main - Copy.py - Bloc-notes"), "main - Copy.py")
		self.assertEqual(filepath.title_file("*main.py - Bloc-notes"), "main.py")

	def test_remembered_path_wins(self):
		one = self.write("p1/main.py", b"print('one')\r\n")
		two = self.write("p2/main.py", b"print('one')\r\n")
		with mock.patch.object(filepath, "recent_item_target", return_value=one), \
			mock.patch.object(filepath, "process_command_line", return_value=None):
			# Both hold the text: the user's choice decides.
			self.assertEqual(filepath.find_file("main.py - Notepad", pid=1, remembered=two, text="print('one')\r\n"), two)
			# Unsaved changes: still the user's choice.
			self.assertEqual(filepath.find_file("*main.py - Notepad", pid=1, remembered=two, text="changed"), two)

	def test_remembered_path_loses_to_the_file_that_holds_the_text(self):
		one = self.write("p1/main.py", b"print('one')\r\n")
		two = self.write("p2/main.py", b"print('two')\r\n")
		with mock.patch.object(filepath, "recent_item_target", return_value=one), \
			mock.patch.object(filepath, "process_command_line", return_value=None):
			self.assertEqual(filepath.find_file("main.py - Notepad", pid=1, remembered=two, text="print('one')\r\n"), one)

	def test_one_file_under_two_spellings(self):
		one = self.write("p1/main.py", b"x = 1\r\n")
		other = os.path.join(self.root, "p1", "..", "p1", "main.py")
		with mock.patch.object(filepath, "recent_item_target", return_value=other), \
			mock.patch.object(filepath, "process_command_line", return_value='notepad.exe "%s"' % one):
			self.assertEqual(filepath.find_file("main.py - Notepad", pid=1), one)

	def test_ansi_bytes_without_a_character(self):
		path = self.write("a/x.txt", b"a\x81b\r\n")
		with mock.patch.object(filepath.locale, "getencoding", return_value="cp1252", create=True):
			self.assertTrue(filepath.file_holds(path, "a\x81b\r\n"))

	def test_utf16_without_bom(self):
		path = self.write("a/y.txt", "print('hi')\r\n".encode("utf-16-le"))
		self.assertTrue(filepath.file_holds(path, "print('hi')\r\n"))


class PluginRoundThreeTests(v040.V040Tests):
	# Only the tests below run here; the inherited ones run in their own module.
	def setUp(self):
		super(PluginRoundThreeTests, self).setUp()
		codeCompass._runSequence.clear()

	def test_tab_on_one_line_says_indented(self):
		start = self.ed.text.index("        bar()")
		self.ed.selection = (start, self.ed.text.index("    }\r\n}"))
		self.ed.script_ccTab(Gesture("kb:tab"))
		self.assertEqual(self.message(), "Indented")

	def test_notepad_keys_by_application(self):
		gesture = Gesture("kb:f8")
		self.ed.appModule = types.SimpleNamespace(appName="notepad++")
		with mock.patch.object(codeCompass, "_delegate") as delegate:
			self.ed._notepad_key("nextProblem", gesture)
			gesture.send.assert_called_once()
			delegate.assert_not_called()
			# Another editor with its own control class still gets Code Compass's.
			self.ed.appModule = types.SimpleNamespace(appName="notepad")
			self.ed.windowClassName = "RichEditD2DPT"
			self.ed._notepad_key("nextProblem", gesture)
			delegate.assert_called_once()

	def test_rename_accepts_unicode_names(self):
		self.at("        bar()", 9)

		class NameDialog(object):
			def __init__(self, *args):
				pass

			def Bind(self, *a, **k):
				pass

			def ShowModal(self):
				return 5100

			def GetValue(self):
				return "café"

			def Destroy(self):
				pass

		with mock.patch.object(MODS["wx"], "TextEntryDialog", NameDialog, create=True):
			self.plugin.script_rename(None)
		self.run_later()
		self.assertEqual(self.ed.text.count("café"), 2)

	def test_older_run_result_is_ignored(self):
		self.use("print(1)\nx = 1 / 0\n")
		codeCompass._runSequence[7] = 2
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError"}}, 7, "main.py", 1)
		self.assertNotIn(7, codeCompass._runErrors)
		self.plugin._run_finished({"status": 1, "error": {"line": 2, "message": "ZeroDivisionError"}}, 7, "main.py", 2)
		self.assertIn(7, codeCompass._runErrors)

	def test_report_file_removed_when_python_fails_to_start(self):
		folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, folder, True)
		report = os.path.join(folder, "report.json")

		def mkstemp(**kwargs):
			return os.open(report, os.O_CREAT | os.O_WRONLY), report

		with mock.patch.object(codeCompass.tempfile, "mkstemp", mkstemp), \
			mock.patch.object(codeCompass.subprocess, "Popen", side_effect=OSError), \
			mock.patch.object(codeCompass, "_python_command", return_value=["py", "-3"]):
			self.plugin._launch(self.ed, os.path.join(folder, "main.py"))
		self.assertFalse(os.path.exists(report))
		self.assertNotIn(7, codeCompass._runSequence)


# Keep the inherited V040 tests from running twice.
for _name in list(vars(v040.V040Tests)):
	if _name.startswith("test_") and _name not in vars(PluginRoundThreeTests):
		setattr(PluginRoundThreeTests, _name, None)


if __name__ == "__main__":
	unittest.main()
