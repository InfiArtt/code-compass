# -*- coding: UTF-8 -*-
# Regression tests for problems found when verifying the review fixes.

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "codeCompass"))

from analyzer import Analysis  # noqa: E402


def chain_at(src, lang, needle):
	a = Analysis(src, lang)
	return [i.name for i in a.declaration_chain(src.index(needle))]


def item(src, lang, name):
	a = Analysis(src, lang)
	return [i for i in a.outline() if i.name == name][0], a


def lines_of(src, lang, name):
	it, a = item(src, lang, name)
	return it.startLine, it.endLine


class TypingTests(unittest.TestCase):
	SRC = (
		"class A:\n"
		"    def typing(self):\n"
		"        print(\n"
		"\n"
		"    def b(self):\n"
		"        return 2\n"
		"\n"
		"class C:\n"
		"    def d(self):\n"
		"        pass\n"
	)

	def test_unclosed_bracket_does_not_nest_everything(self):
		d, a = item(self.SRC, "python", "d")
		self.assertEqual([p.name for p in d.ancestors()], ["C"])
		typing = [i for i in a.outline() if i.name == "typing"][0]
		self.assertEqual(typing.children, [])
		b = [i for i in a.outline() if i.name == "b"][0]
		self.assertEqual(b.parent, "A")

	def test_unclosed_bracket_stays_fast(self):
		block = "".join("def f%d(x):\n    return x + %d\n\n" % (i, i) for i in range(1300))
		src = "def broken():\n    foo(\n\n" + block
		start = time.perf_counter()
		a = Analysis(src, "python")
		outline = a.outline()
		elapsed = time.perf_counter() - start
		self.assertEqual(len(outline), 1301)
		self.assertLess(elapsed, 1.0, "outline took %.2fs" % elapsed)

	def test_unterminated_docstring(self):
		src = 'class K:\n    def f(self):\n        """\n        return 1\n\n    def g(self):\n        pass\n'
		self.assertEqual(chain_at(src, "python", "return 1"), ["K", "f"])


class CallbackTests(unittest.TestCase):
	def test_forward_ref(self):
		src = (
			"const Input = forwardRef(function Input(props, ref) {\n"
			"  function handleChange(e) {\n"
			"    go(e);\n"
			"  }\n"
			"  return <input ref={ref} />;\n"
			"});\n"
		)
		self.assertEqual(chain_at(src, "js", "return <input"), ["Input"])
		handle, _a = item(src, "js", "handleChange")
		self.assertEqual(handle.parent, "Input")

	def test_express_handler(self):
		src = "app.get('/', function handler(req, res) {\n  res.send('x');\n});\n"
		self.assertEqual(lines_of(src, "js", "handler"), (0, 2))

	def test_mocha(self):
		src = (
			"describe('suite', function suite() {\n"
			"  it('works', function works() {\n"
			"    check();\n"
			"  });\n"
			"});\n"
		)
		self.assertEqual(chain_at(src, "js", "check()"), ["suite", "works"])


class HeaderWrapTests(unittest.TestCase):
	def test_rust_where(self):
		src = "fn process<T>(items: Vec<T>) -> Result<(), Error>\nwhere\n    T: Clone,\n{\n    Ok(())\n}\n"
		self.assertEqual(lines_of(src, "clike", "process"), (0, 5))

	def test_generic_wrap_class(self):
		src = (
			"export class Foo extends Component<\n"
			"  Props,\n"
			"  State\n"
			"> {\n"
			"  render() {\n"
			"    return null;\n"
			"  }\n"
			"}\n"
		)
		self.assertEqual(lines_of(src, "js", "Foo"), (0, 7))
		render, _a = item(src, "js", "render")
		self.assertEqual(render.parent, "Foo")

	def test_generic_wrap_function(self):
		src = "export function useQuery<\n  TData,\n  TError,\n>(key: string): Result<TData> {\n  return run(key);\n}\n"
		self.assertEqual(lines_of(src, "js", "useQuery"), (0, 5))

	def test_brace_in_generic_constraint_and_return_type(self):
		src = "function pick<T extends { id: number }>(items: T[]): T {\n  return items[0];\n}\n"
		self.assertEqual(chain_at(src, "js", "return items"), ["pick"])
		src2 = "function make(): { ok: boolean } {\n  return { ok: true };\n}\n"
		self.assertEqual(lines_of(src2, "js", "make"), (0, 2))

	def test_java_throws_at_line_end(self):
		src = "class A {\n    void run() throws\n            IOException {\n        go();\n    }\n}\n"
		self.assertEqual(lines_of(src, "clike", "run"), (1, 4))

	def test_extends_at_line_end(self):
		src = "public class Foo extends\n        Bar {\n    int x;\n}\n"
		self.assertEqual(chain_at(src, "clike", "int x"), ["Foo"])

	def test_cpp_requires(self):
		src = "void f(T x)\n    requires std::integral<T>\n{\n    go();\n}\n"
		self.assertEqual(lines_of(src, "clike", "f"), (0, 4))

	def test_swift_async_on_next_line(self):
		src = "func load(url: URL)\n    async throws -> Data {\n    go()\n}\n"
		self.assertEqual(lines_of(src, "swift", "load"), (0, 3))

	def test_wrapped_arrow_function(self):
		src = "export const build = async (\n  a: string,\n): Promise<void> => {\n  await run(a);\n};\n"
		self.assertEqual(chain_at(src, "js", "await run"), ["build"])

	def test_wrapped_method_in_class(self):
		src = "class A {\n  save(\n    a,\n    b,\n  ) {\n    go();\n  }\n}\n"
		self.assertEqual(chain_at(src, "js", "go()"), ["A", "save"])

	def test_wrapped_call_is_not_a_method(self):
		src = "function f() {\n  doThing(\n    1,\n  );\n}\n"
		a = Analysis(src, "js")
		self.assertEqual([i.name for i in a.outline()], ["f"])

	def test_ts_constructor(self):
		src = "class S {\n  constructor(\n    private readonly http: HttpClient,\n  ) {}\n}\n"
		a = Analysis(src, "js")
		self.assertIn("constructor", [i.name for i in a.outline()])


class BodylessTests(unittest.TestCase):
	def test_swift_protocol_member(self):
		src = "protocol P {\n    func items() -> Array<Int>\n    var count: Int { get }\n}\n"
		self.assertEqual(chain_at(src, "swift", "var count"), ["P"])

	def test_kotlin_abstract_then_init(self):
		src = "abstract class Base {\n    abstract fun items(): List<String>\n    init {\n        println()\n    }\n}\n"
		self.assertEqual(chain_at(src, "clike", "println"), ["Base"])

	def test_react_component_in_parens(self):
		src = 'const App = () => (\n  <div className="x">\n    <p>{title}</p>\n  </div>\n);\n'
		self.assertEqual(chain_at(src, "js", "<p>"), ["App"])

	def test_kotlin_data_class(self):
		src = "data class User(\n    val id: Int,\n    val name: String,\n)\n"
		self.assertEqual(chain_at(src, "clike", "val name"), ["User"])

	def test_expression_body(self):
		src = "fun nums() = listOf(\n    1,\n    2,\n)\n"
		self.assertEqual(chain_at(src, "clike", "2,"), ["nums"])


class FalsePositiveTests(unittest.TestCase):
	def test_go_func_typed_parameter(self):
		src = "func (s *S) Run(\n\tctx context.Context,\n\tfn func(int) error,\n) error {\n\treturn fn(1)\n}\n"
		self.assertEqual(chain_at(src, "clike", "return fn"), ["Run"])

	def test_go_handler_parameter(self):
		src = "func Handle(\n\tctx context.Context,\n\thandler func(w http.ResponseWriter),\n) error {\n\treturn nil\n}\n"
		self.assertEqual(chain_at(src, "clike", "return nil"), ["Handle"])

	def test_csharp_base_initializer(self):
		src = "class Cls\n{\n    public Cls(int x)\n        : base(x)\n    {\n        Go();\n    }\n}\n"
		a = Analysis(src, "clike")
		self.assertNotIn("base", [i.name for i in a.outline()])
		self.assertEqual(chain_at(src, "clike", "Go()"), ["Cls", "Cls"])

	def test_kotlin_supertype_line(self):
		src = "class MyView(\n    context: Context,\n)\n    : View(context) {\n    fun draw() {}\n}\n"
		self.assertEqual(chain_at(src, "clike", "fun draw"), ["MyView", "draw"])

	def test_objc_directives(self):
		src = "@interface A : NSObject\n@end\n@interface B : NSObject\n@property int y;\n@end\n"
		b, _a = item(src, "clike", "B")
		self.assertEqual(b.startLine, 2)


class DecoratorTests(unittest.TestCase):
	def test_decorated_field_above_method(self):
		src = "class C {\n  @Input() name: string;\n  @HostListener('click')\n  onClick() {\n    go();\n  }\n}\n"
		self.assertEqual(lines_of(src, "js", "onClick"), (2, 5))
		self.assertEqual(chain_at(src, "js", "@Input"), ["C"])

	def test_comment_between_decorator_and_def(self):
		src = '@app.route("/")\n# index page\ndef index():\n    pass\n'
		self.assertEqual(lines_of(src, "python", "index")[0], 0)

	def test_blank_line_between_decorator_and_class(self):
		src = "@dataclass\n\nclass P:\n    x: int\n"
		self.assertEqual(lines_of(src, "python", "P")[0], 0)

	def test_rust_attribute(self):
		src = "#[derive(Debug, Clone)]\nstruct Point {\n    x: i32,\n}\n"
		self.assertEqual(lines_of(src, "clike", "Point"), (0, 3))
		self.assertEqual(chain_at(src, "clike", "#[derive"), ["Point"])

	def test_cpp_template(self):
		src = "template <typename T>\nT max(T a, T b) {\n    return a;\n}\n"
		self.assertEqual(lines_of(src, "clike", "max"), (0, 3))


class BlockCommentTests(unittest.TestCase):
	def test_code_after_comment_end_is_a_statement(self):
		src = "function f() {\n  /* note\n  */ x();\n  y();\n}\nfunction g() {}\n"
		a = Analysis(src, "js")
		self.assertEqual(a.same_level_line(2, 1), 3)
		self.assertEqual(a.same_level_line(3, -1), 2)


if __name__ == "__main__":
	unittest.main()
