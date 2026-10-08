# -*- coding: UTF-8 -*-
# Code Compass - problems in a file: syntax errors that can be found without
# running anything, unbalanced brackets, and the last run's error.
# Pure Python (no NVDA imports) so it can be unit-tested outside NVDA.

import ast
import json
import re
import warnings


def _(text):
	"""Replaced by the plugin's translator (Code Compass's language setting)."""
	return text


class Problem(object):
	__slots__ = ("line", "column", "message", "kind")

	def __init__(self, line, column, message, kind="syntax"):
		#: Zero-based line and column.
		self.line = line
		self.column = column
		self.message = message
		#: "syntax", "bracket" (the message names its line), "run",
		#: "indent" (tabs and spaces), "duplicate" (a name declared twice) or
		#: "warning" (allowed, but most likely a slip).
		self.kind = kind

	def __eq__(self, other):
		return isinstance(other, Problem) and (self.line, self.column, self.message) == (other.line, other.column, other.message)

	def __repr__(self):
		return "Problem(%d, %d, %r)" % (self.line, self.column, self.message)


def python_problems(text):
	"""The first syntax error, found by parsing only: nothing is run.
	NVDA's own Python parses the code, so very new or very old syntax may be
	judged by NVDA's Python version."""
	source = text.replace("\r\n", "\n").replace("\r", "\n")
	try:
		with warnings.catch_warnings():
			# Invalid escape sequences and similar only warn; keep them quiet.
			warnings.simplefilter("ignore")
			compile(source, "<code>", "exec", ast.PyCF_ONLY_AST, dont_inherit=True)
	except SyntaxError as e:
		line = max(0, (e.lineno or 1) - 1)
		column = max(0, (e.offset or 1) - 1)
		return [Problem(line, column, e.msg)]
	except (ValueError, RecursionError, MemoryError) as e:
		# Null bytes, or nesting too deep to parse.
		return [Problem(0, 0, str(e))]
	return []


def json_problems(text):
	if not text.strip():
		return []
	try:
		json.loads(text)
	except json.JSONDecodeError as e:
		return [Problem(e.lineno - 1, e.colno - 1, e.msg)]
	return []


def syntax_problems(text, langName, ext=None):
	"""Syntax errors for languages Code Compass can check by itself."""
	if langName == "python":
		return python_problems(text)
	if ext == "json":
		return json_problems(text)
	return []


def indentation_problems(analysis):
	"""Python lines indented with tabs where the file indents with spaces, or
	the other way round, and lines mixing both: Python reads these
	differently from how they sound, or refuses them. Lines inside brackets
	and multi-line strings do not count."""
	if analysis.langName != "python":
		return []
	lines = []
	tabs = spaces = 0
	for li in range(analysis.lineCount):
		if li in analysis._continuation or analysis.line_inner_bracket(li) is not None:
			continue
		if not analysis.line_code(li).strip() or analysis.leading_closer(li) is not None:
			# Comments, and a closing bracket on its own line, may sit anywhere.
			continue
		if li and analysis.line_code(li - 1).rstrip().endswith("\\"):
			# The rest of a statement continued with a backslash.
			continue
		text = analysis.line_text(li)
		indent = text[:len(text) - len(text.lstrip(" \t"))]
		if not indent or not text.strip():
			continue
		lines.append((li, indent))
		if indent[0] == "\t":
			tabs += 1
		else:
			spaces += 1
	# The file's own style: what most lines use (the first one on a tie).
	useTabs = tabs > spaces or (tabs == spaces and bool(lines) and lines[0][1][0] == "\t")
	found = []
	for li, indent in lines:
		if " " in indent and "\t" in indent:
			# Translators: a Python line whose indentation mixes tabs and spaces.
			found.append(Problem(li, 0, _("tabs and spaces mixed in the indentation"), "indent"))
		elif (indent[0] == "\t") != useTabs:
			if useTabs:
				# Translators: a Python line indented with spaces in a file indented with tabs.
				message = _("indented with spaces, the rest of the file uses tabs")
			else:
				# Translators: a Python line indented with tabs in a file indented with spaces.
				message = _("indented with tabs, the rest of the file uses spaces")
			found.append(Problem(li, 0, message, "indent"))
	return found


#: A JavaScript accessor: "get value()" and "set value(v)" share a name.
_ACCESSOR = re.compile(
	r"^\s*(?:(?:static|public|private|protected|readonly|override|abstract|declare|accessor)\s+)*(?:get|set)\s+[\w$#]")
#: A declaration statement: "function f(", "export default class A".
_JS_DECLARATION = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function\b|class\b)")
_JS_STATIC = re.compile(r"^\s*(?:(?:public|private|protected|override|async|readonly)\s+)*static\b")


def nested_name_warnings(analysis):
	"""A function declared inside a function of the same name ("def main()"
	inside "def main()"): allowed, as a local function, but most likely a
	paste or an indentation slip. A warning, in every language."""
	found = []
	for item in analysis.outline():
		parent = item.parentItem
		if (
			parent is not None and item.kind == "function" and parent.kind == "function"
			and item.name == parent.name and item.hasBody
		):
			# Translators: a warning for a function declared inside a function with the
			# same name, e.g. "main is declared inside main, a function with the same name".
			message = _("{name} is declared inside {name}, a function with the same name").format(name=item.name)
			found.append(Problem(item.line, 0, message, "warning"))
	return found


def duplicate_problems(analysis):
	"""Functions and classes declared twice in the same place (Python and
	JavaScript), where the second silently replaces the first. Not reported:
	decorated Python declarations (property setters, overloads), JavaScript
	getters and setters, and TypeScript overload signatures (no body)."""
	if analysis.langName not in ("python", "js"):
		return []
	python = analysis.langName == "python"
	seen = {}
	found = []
	for item in analysis.outline():
		if item.kind not in ("function", "class") or item.name == "_":
			continue
		code = analysis.line_code(item.line)
		if python:
			if item.startLine < item.line:
				continue
			owner = _python_owner(analysis, item.line)
		else:
			if _ACCESSOR.match(code) or re.match(r"^\s*(?:export\s+)?declare\b", code):
				continue
			if not _JS_DECLARATION.match(code) and not analysis._in_class_body(item.line):
				# A call such as "it('x', (): void => {", or a named function
				# expression ("app.get('/', function handler(") whose name only
				# exists inside it.
				continue
			if not item.hasBody:
				# A TypeScript overload signature.
				continue
			stack = analysis.enclosing(analysis.lineStarts[item.line] + item.column)
			owner = (stack[-1].offset if stack else -1, bool(_JS_STATIC.match(code)))
		key = (owner, item.name)
		first = seen.get(key)
		if first is None:
			seen[key] = item
			continue
		seen[key] = item
		# Translators: a function or class declared again in the same place,
		# e.g. "load is declared again; the one on line 4 no longer counts".
		message = _("{name} is declared again; the one on line {line} no longer counts")
		found.append(Problem(item.line, 0, message.format(name=item.name, line=first.line + 1), "duplicate"))
	return found


def _python_owner(analysis, line):
	"""The statement a Python line belongs to: the nearest line above with
	less indentation (-1 at the top level). "if" and "else" branches are
	different owners, so alternatives are not duplicates."""
	text = analysis.line_text(line)
	indent = len(text) - len(text.lstrip(" \t"))
	if not indent:
		return -1
	for j in range(line - 1, -1, -1):
		if j in analysis._continuation or analysis.line_inner_bracket(j) is not None:
			continue
		other = analysis.line_text(j)
		if other.strip() and not other.lstrip().startswith("#") and len(other) - len(other.lstrip(" \t")) < indent:
			return j
	return -1


def find_problems(analysis, ext=None, extra=()):
	"""Every known problem in document order: syntax errors, unbalanced
	brackets and any extra ones (such as the last run's error). A line with a
	syntax error does not also report its brackets (the parser already
	explains it), and exact duplicates are dropped."""
	syntax = list(syntax_problems(analysis.text, analysis.langName, ext))
	syntaxLines = {p.line for p in syntax}
	items = syntax + [
		Problem(li, 0, message, "bracket")
		for li, message in analysis.problems() if li not in syntaxLines
	]
	items.extend(p for p in indentation_problems(analysis) if p.line not in syntaxLines)
	items.extend(duplicate_problems(analysis))
	items.extend(nested_name_warnings(analysis))
	items.extend(extra)
	items.sort(key=lambda p: p.line)
	result = []
	for p in items:
		if any(r.line == p.line and r.message == p.message for r in result):
			continue
		result.append(p)
	return result


def next_problem(problems, line, step):
	"""The problem after (step=1) or before (step=-1) line, wrapping around
	the file like F8 in VS Code. None when there are no problems."""
	if not problems:
		return None
	if step > 0:
		later = [p for p in problems if p.line > line]
		return later[0] if later else problems[0]
	earlier = [p for p in problems if p.line < line]
	return earlier[-1] if earlier else problems[-1]
