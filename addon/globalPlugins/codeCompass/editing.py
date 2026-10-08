# -*- coding: UTF-8 -*-
# Code Compass - editing helpers: auto-indent, comments, indentation of
# several lines, word completion and parameter hints.
# Pure Python (no NVDA imports) so it can be unit-tested outside NVDA. Each
# function works on an analyzer.Analysis and returns what to change; the
# plugin applies the change to the editor.

import collections
import os
import re

try:
	from . import analyzer
except ImportError:
	# Imported directly by the tests, outside the add-on package.
	import analyzer

_LEADING_WS = re.compile(r"^[ \t]*")
#: An identifier: a letter, "_" or "$", then word characters. The lookbehind
#: keeps it from starting inside a longer token ("e5" in "1e5", "ber" in "über").
_IDENT_PATTERN = r"(?<![\w$])(?:[^\W\d]|\$)[\w$]*"
_IDENT = re.compile(_IDENT_PATTERN)
_IDENT_END = re.compile(_IDENT_PATTERN + "$")
_IDENT_CHARS = re.compile(r"[\w$]*$")

#: Statements after which Python code continues one level out.
_PY_DEDENT_AFTER = re.compile(r"^\s*(return|pass|break|continue|raise)\b")

#: Line comment token per language; CSS only has block comments.
COMMENT_TOKENS = {
	"python": "#", "hash": "#", "yaml": "#",
	"clike": "//", "js": "//", "swift": "//", "php": "//", "generic": "//",
	"sql": "--", "lua": "--",
}
BLOCK_COMMENTS = {"css": ("/*", "*/")}


def leading_ws(line):
	return _LEADING_WS.match(line).group(0)


def newline_style(text):
	"""The line break the document uses: CRLF, LF or CR (CRLF when empty)."""
	if "\r\n" in text:
		return "\r\n"
	if "\n" in text:
		return "\n"
	if "\r" in text:
		return "\r"
	return "\r\n"

def indent_unit(text):
	"""The indentation step the document uses: a tab when most indented lines
	start with one, else the most common increase in spaces (default 4)."""
	tabs = spaces = 0
	steps = collections.Counter()
	previous = 0
	for line in analyzer._NEWLINES.split(text):
		if not line.strip():
			continue
		ws = leading_ws(line)
		if ws.startswith("\t"):
			tabs += 1
			continue
		width = len(ws)
		if width:
			spaces += 1
		if width > previous and width - previous in (2, 3, 4, 8):
			steps[width - previous] += 1
		previous = width
	if tabs > spaces:
		return "\t"
	return " " * (steps.most_common(1)[0][0] if steps else 4)


def remove_one_level(indent, unit):
	if indent.endswith(unit):
		return indent[:-len(unit)]
	if indent.endswith("\t"):
		return indent[:-1]
	return indent[:max(0, len(indent) - len(unit))]


def enter_text(a, caret, unit, end=None):
	"""What Enter should type at caret: (text, caretInText). The new line
	gets the current line's indentation, one level more after an opening
	bracket (or ":" in Python and YAML), one level less after return, pass,
	break, continue or raise in Python. Between a pair such as "{|}", the
	closing bracket goes to its own line and the caret to the middle line.
	end is where a selection being replaced ends (default: caret).
	caretInText is where the caret should end, or None for the end."""
	nl = newline_style(a.text)
	li = a.line_index(caret)
	lineStart, lineEnd = a.line_bounds(li)
	before = a.text[lineStart:caret]
	indent = before if not before.strip() else leading_ws(before)
	codeBefore = a.code[lineStart:caret].rstrip()
	after = caret if end is None else max(caret, min(end, lineEnd))
	codeAfter = a.code[after:lineEnd].strip()
	opens = codeBefore.endswith(("{", "(", "[")) or (a.lang["indentScopes"] and codeBefore.endswith(":"))
	if opens:
		inner = indent + unit
		closer = analyzer.PAIR.get(codeBefore[-1]) if codeBefore[-1] in "{([" else None
		if closer and codeAfter[:1] == closer:
			return nl + inner + nl + indent, len(nl + inner)
		return nl + inner, None
	if a.langName == "python" and _PY_DEDENT_AFTER.match(a.code[lineStart:caret]) and not codeAfter:
		return nl + remove_one_level(indent, unit), None
	return nl + indent, None


def closer_reindent(a, closerOffset):
	"""After a closing bracket typed as the first thing on its line: the
	(start, end, newIndent) that lines it up with the line of its opening
	bracket, or None when nothing should change."""
	b = a.bracket_at(closerOffset)
	if b is None or b.char not in analyzer.CLOSERS or b.partner is None:
		return None
	lineStart = a.lineStarts[a.line_index(closerOffset)]
	ws = a.text[lineStart:closerOffset]
	if ws.strip():
		return None
	target = leading_ws(a.line_text(a.line_index(b.partner)))
	if ws == target:
		return None
	return lineStart, closerOffset, target


def line_block(a, start, end):
	"""(first, last) line indexes covered by a selection. A selection that
	ends at the very start of a line does not include that line."""
	first = a.line_index(start)
	last = a.line_index(end)
	if end > start and last > first and end == a.lineStarts[last]:
		last -= 1
	return first, last


def lines_range(a, first, last):
	"""(start, end) of whole lines first..last, without the final line break."""
	return a.lineStarts[first], a.line_bounds(last)[1]


def toggle_comment(a, first, last):
	"""New text for lines first..last with comments toggled, and whether
	they were commented (True) or uncommented (False). Lines that are all
	commented get uncommented; otherwise every non-blank line is commented at
	the smallest indentation, like VS Code. None when the language has no
	comment syntax."""
	start, end = lines_range(a, first, last)
	lines = analyzer._NEWLINES.split(a.text[start:end])
	nl = newline_style(a.text)
	token = COMMENT_TOKENS.get(a.langName)
	block = BLOCK_COMMENTS.get(a.langName)
	if token is None and block is None:
		return None
	opener, closer = (token, "") if token else block
	filled = [l for l in lines if l.strip()]
	if not filled:
		return None
	if all(l.strip().startswith(opener) and l.rstrip().endswith(closer) for l in filled):
		out = []
		for l in lines:
			if not l.strip():
				out.append(l)
				continue
			ws = leading_ws(l)
			body = l[len(ws) + len(opener):]
			if body.startswith(" "):
				body = body[1:]
			if closer:
				body = body.rstrip()
				body = body[:-len(closer)].rstrip()
			out.append(ws + body)
		return nl.join(out), False
	# The indentation all lines share, so a tab and spaces are not split.
	cut = len(os.path.commonprefix([leading_ws(l) for l in filled]))
	out = []
	for l in lines:
		if not l.strip():
			out.append(l)
			continue
		suffix = " " + closer if closer else ""
		out.append(l[:cut] + opener + " " + l[cut:] + suffix)
	return nl.join(out), True


def shift_lines(a, first, last, unit, outward=False):
	"""New text for lines first..last indented by one level, or outdented
	when outward is True. Blank lines stay as they are."""
	start, end = lines_range(a, first, last)
	lines = analyzer._NEWLINES.split(a.text[start:end])
	out = []
	for l in lines:
		if not l.strip():
			out.append(l)
		elif outward:
			ws = leading_ws(l)
			out.append(remove_one_level(ws, unit) + l[len(ws):])
		else:
			out.append(unit + l)
	return newline_style(a.text).join(out)


# --- Completion -----------------------------------------------------------------

_KEYWORDS = {
	"python": (
		"False None True and as assert async await break class continue def del elif else "
		"except finally for from global if import in is lambda nonlocal not or pass raise "
		"return try while with yield self print len range enumerate input int str float list "
		"dict set tuple bool open isinstance super"
	),
	"js": (
		"async await break case catch class const continue debugger default delete do else "
		"export extends false finally for function if import in instanceof let new null return "
		"static super switch this throw true try typeof undefined var void while yield console "
		"document window"
	),
	"swift": (
		"associatedtype break case catch class continue default defer do else enum extension "
		"fallthrough false for func guard if import in init inout internal let nil private "
		"protocol public repeat return self static struct subscript super switch throw throws "
		"true try var where while print"
	),
	"clike": (
		"auto bool break case catch char class const continue default delete do double else enum "
		"extends false final finally float for if implements import int interface long namespace "
		"new null nullptr package private protected public return short static string struct "
		"super switch this throw true try typedef unsigned using var void while fn let mut impl "
		"func go defer chan fun val when"
	),
	"php": "array as break case class const continue echo else foreach function if new null public private protected return static this true false while",
	"sql": "SELECT FROM WHERE INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE JOIN LEFT RIGHT INNER ORDER BY GROUP HAVING LIMIT AND OR NOT NULL",
	"lua": "and break do else elseif end false for function if in local nil not or repeat return then true until while",
}


def word_at(text, caret):
	"""(start, prefix) of the identifier characters just before caret."""
	m = _IDENT_CHARS.search(text, 0, caret)
	start = m.start() if m else caret
	return start, text[start:caret]


def completions(a, caret):
	"""Candidates for the word being typed at caret: (start, prefix, words).
	After "name." only words seen after "name." in the file are offered;
	after ")." or "]." any word seen after a dot. Otherwise names from the
	file come first, nearest to the caret first, then the language's
	keywords. Comments and strings are ignored."""
	start, prefix = word_at(a.text, caret)
	if prefix[:1].isdigit():
		return start, prefix, []
	rx = None
	if start > 0 and a.code[start - 1] == ".":
		receiver = _IDENT_END.search(a.code, 0, start - 1)
		previous = a.code[start - 2:start - 1]
		if receiver is not None:
			# [ \t] rather than \s, so "self." at a line end does not reach
			# the next line's first word.
			rx = re.compile(r"(?<![\w$])" + re.escape(receiver.group(0)) + r"[ \t]*\.[ \t]*(" + _IDENT_PATTERN + ")")
		elif previous in (")", "]"):
			rx = re.compile(r"\.[ \t]*(" + _IDENT_PATTERN + ")")
		# Otherwise a spread "..." or a relative import ".": plain names.
	if rx is None and not prefix:
		return start, prefix, []
	seen = {}
	matches = rx.finditer(a.code) if rx is not None else _IDENT.finditer(a.code)
	group = 1 if rx is not None else 0
	for m in matches:
		if m.start(group) == start:
			continue
		_note(seen, m.group(group), m.start(group), caret)
	words = [w for w in seen if w != prefix and w.startswith(prefix)]
	words.sort(key=lambda w: (seen[w], w))
	others = [w for w in seen if w != prefix and w not in words and w.lower().startswith(prefix.lower())]
	others.sort(key=lambda w: (seen[w], w))
	words += others
	if rx is None:
		for kw in _KEYWORDS.get(a.langName, "").split():
			if kw.lower().startswith(prefix.lower()) and kw != prefix and kw not in words:
				words.append(kw)
	return start, prefix, words

def _note(seen, word, offset, caret):
	distance = abs(offset - caret)
	if word not in seen or distance < seen[word]:
		seen[word] = distance


def _call_caret(a, caret):
	"""Where to look for the call at caret: in its parentheses. A caret on
	the called name, on its "(" or just after its ")" means that call too
	(a screen reader reads the character after the caret)."""
	code = a.code
	caret = max(0, min(caret, len(code)))
	if code[caret:caret + 1] == "(":
		return caret + 1
	ident = identifier_at(a, caret)
	if ident is not None:
		k = ident[1]
		while k < len(code) and code[k] in " \t":
			k += 1
		if code[k:k + 1] == "(":
			return k + 1
	if caret > 0 and code[caret - 1] == ")":
		closer = a.bracket_at(caret - 1)
		if closer is not None and closer.partner is not None:
			return caret - 1
	return caret


def _call_at(a, caret):
	"""(opener, name) of the call whose parentheses hold caret (see
	_call_caret), or None when the caret is in no call."""
	opener = next((b for b in reversed(a.enclosing(caret)) if b.char == "("), None)
	if opener is None:
		return None
	before = a.code[:opener.offset].rstrip()
	if before.endswith(("=>", "->")):
		# "(item) => (" or "-> (": not a call.
		return None
	if before.endswith(">"):
		# Type arguments: "new Box<>(", "new Cache<string, number>(".
		depth = 0
		lineStart = before.rfind("\n") + 1
		for k in range(len(before) - 1, lineStart - 1, -1):
			if before[k] == ">" and before[k - 1:k] not in ("-", "="):
				depth += 1
			elif before[k] == "<":
				depth -= 1
				if depth == 0:
					before = before[:k].rstrip()
					if before.endswith("::"):
						# Rust's turbofish: "apply::<G>(".
						before = before[:-2].rstrip()
					break
		else:
			return None
	m = _IDENT_END.search(before)
	if m is None:
		return None
	return opener, m.group(0)


def called_name(a, caret):
	"""The name of the function called at caret, or None outside a call."""
	call = _call_at(a, _call_caret(a, caret))
	return call[1] if call else None


def parameter_hint(a, caret):
	"""The signature of the function whose parentheses hold the caret (or
	whose name, "(" or ")" it is on), when that function is declared in this
	file, and which argument the caret is on: (signature, argumentNumber),
	or None."""
	caret = _call_caret(a, caret)
	call = _call_at(a, caret)
	if call is None:
		return None
	opener, name = call
	argument = 1
	depth = 0
	inLambda = False
	for tok in re.finditer(r"[()\[\]{},:]|\blambda\b", a.code[opener.offset + 1:caret]):
		t = tok.group(0)
		if t == "lambda":
			inLambda = a.langName == "python" and (depth == 0 or inLambda)
		elif t in "([{":
			depth += 1
		elif t in ")]}":
			depth -= 1
		elif t == ":" and depth == 0:
			# A Python lambda's parameters end at its ":".
			inLambda = False
		elif t == "," and depth == 0 and not inLambda:
			argument += 1
	for item in a.outline():
		if item.name == name:
			signature = _signature(a, item)
			if signature:
				parent = item.parentItem
				if a.langName == "python" and item.kind == "function" and parent is not None and parent.kind == "class":
					# A method: the call ("toko.tambah(x)") does not pass self or cls.
					signature = re.sub(r"^([\w$]+)\(\s*(?:self|cls)\b\s*,?\s*", r"\1(", signature)
				return signature, argument
	return None


#: The constructor's name per language; None stands for the class's own name.
_CONSTRUCTORS = {
	"python": ("__init__",),
	"js": ("constructor",),
	"swift": ("init",),
	# C++, Java, C#: the class's name; Kotlin: "constructor" (its "init"
	# blocks take no parameters).
	"clike": (None, "constructor"),
}


def _signature(a, item):
	"""A declaration's name and parameter list, read from its own header:
	"name(" on its line, the first "(" after "=" for "const name = (...) =>",
	or for a class its primary constructor ("class User(val name: String)",
	"record Point(int x, int y)") or its constructor (__init__, constructor,
	init or the class's own name, depending on the language)."""
	if item.kind != "function":
		if a.langName != "python":
			# In Python "class Name(Base)" lists base classes, not parameters.
			primary = _header_params(a, item, allowAssignment=False)
			if primary:
				return primary
		names = _CONSTRUCTORS.get(a.langName, ("__init__", "constructor", "init", "__construct"))
		for wanted in names:
			wanted = item.name if wanted is None else wanted
			for child in item.children:
				if child.name == wanted and child is not item:
					inner = _signature(a, child)
					if inner:
						params = inner[len(child.name):]
						if a.langName == "python":
							params = re.sub(r"^\(\s*self\s*,?\s*", "(", params)
						return item.name + params
		return None
	return _header_params(a, item, allowAssignment=True)


def _header_params(a, item, allowAssignment):
	"""item's name followed by the parameter list on its header line, or
	None. With allowAssignment, "name = (a, b) =>" counts too."""
	code = a.code
	lineStart, lineEnd = a.line_bounds(item.line)
	headerEnd = a.line_bounds(min(item.endLine, item.line + 10))[1]
	found = re.compile(r"(?<![\w$])" + re.escape(item.name) + r"\b").search(code, lineStart + item.column, lineEnd)
	if found is None:
		return None
	pos = found.end()
	while pos < headerEnd and code[pos] in " \t":
		pos += 1
	if code[pos:pos + 1] == "<":
		# Skip generic parameters: "name<T, U>(".
		angle = 0
		while pos < headerEnd:
			if code[pos] == "<":
				angle += 1
			elif code[pos] == ">" and code[pos - 1] not in "-=":
				angle -= 1
				if angle == 0:
					pos += 1
					break
			pos += 1
		while pos < headerEnd and code[pos] in " \t\r\n":
			pos += 1
	if code[pos:pos + 1] != "(":
		if not allowAssignment:
			return None
		# "const name = (a, b) =>" or "name = function (a, b)".
		eq = code.find("=", found.end(), lineEnd)
		if eq < 0:
			return None
		pos = code.find("(", eq, headerEnd)
		if pos < 0:
			return None
	paren = a.bracket_at(pos)
	if paren is None or paren.partner is None:
		return None
	signature = item.name + re.sub(r"\s+", " ", a.text[paren.offset:paren.partner + 1])
	return re.sub(r"\(\s+", "(", re.sub(r",?\s*\)$", ")", signature))

# --- Names: definition, references, rename ----------------------------------------

def identifier_at(a, caret):
	"""(start, end, name) of the identifier at or just before caret, in code
	(not in a comment or string), or None."""
	for m in _IDENT.finditer(a.code, max(0, caret - 200), min(len(a.code), caret + 200)):
		if m.start() <= caret <= m.end():
			return m.start(), m.end(), m.group(0)
	return None


def occurrences(a, name):
	"""Offsets where name appears as a whole word in code, outside comments
	and strings."""
	rx = re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")
	return [m.start() for m in rx.finditer(a.code)]


def definition_of(a, name):
	"""The declaration of name in this file: an outline item (function,
	class...), or None."""
	return next((item for item in a.outline() if item.name == name), None)


def renamed_text(a, name, newName):
	"""The whole text with every code occurrence of name replaced by newName,
	and how many were replaced."""
	spots = occurrences(a, name)
	parts = []
	last = 0
	for off in spots:
		parts.append(a.text[last:off])
		parts.append(newName)
		last = off + len(name)
	parts.append(a.text[last:])
	return "".join(parts), len(spots)


_TODO = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b[:\s]*(.*)")


def todos(a):
	"""(lineIndex, kind, text) for TODO, FIXME, HACK, XXX and BUG notes in
	comments."""
	items = []
	for start, end in a.commentSpans:
		# Search each comment on its own, so "x = TODO  # later" (a name in
		# code) is no note and a note ends with its comment.
		for m in _TODO.finditer(a.text, start, end):
			li = a.line_index(m.start())
			items.append((li, m.group(1), shorten_note(m.group(2))))
	return items


def shorten_note(text):
	text = re.sub(r"\s*(\*/|-->)\s*$", "", text.strip())
	return analyzer.shorten(text)


# --- Lines: delete, move, duplicate ----------------------------------------------

def full_lines(a, first, last):
	"""(start, end) of lines first..last with the line break after the last
	one (or before the first one, for the last line of a file without one)."""
	start = a.lineStarts[first]
	if last + 1 < a.lineCount:
		return start, a.lineStarts[last + 1]
	if first > 0:
		# The last line has no break after it: take the one before it.
		return a.line_bounds(first - 1)[1], len(a.text)
	return start, len(a.text)


def move_lines(a, first, last, step):
	"""Swap lines first..last with the line above (step=-1) or below
	(step=1). Returns (start, end, newText, newFirst) for the region that
	changes, or None at the edge of the file."""
	if step < 0 and first == 0:
		return None
	if step > 0 and last >= a.lineCount - 1:
		return None
	nl = newline_style(a.text)
	if step < 0:
		lo, hi = first - 1, last
	else:
		lo, hi = first, last + 1
	start, end = lines_range(a, lo, hi)
	lines = analyzer._NEWLINES.split(a.text[start:end])
	if step < 0:
		lines = lines[1:] + lines[:1]
	else:
		lines = lines[-1:] + lines[:-1]
	return start, end, nl.join(lines), first + step


def duplicate_lines(a, first, last):
	"""(insertAt, text) that copies lines first..last below themselves."""
	nl = newline_style(a.text)
	start, end = lines_range(a, first, last)
	return end, nl + a.text[start:end]


# --- Auto-close ----------------------------------------------------------------------

AUTO_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`"}


def should_autoclose(a, caret, ch):
	"""After ch was typed just before caret: should its partner be added
	after the caret? Only for a character typed in code (not inside a string
	or comment), when the next character is a space, a closing bracket or the
	end of the line, and for a quote, when it opens a string rather than
	closing one or being part of a word (like "don't")."""
	if ch not in AUTO_PAIRS or caret < 1 or a.code[caret - 1] != ch:
		return False
	lineStart, lineEnd = a.line_bounds(a.line_index(caret))
	following = a.text[caret:lineEnd][:1]
	if following and not following.isspace() and following not in ")]};,":
		return False
	if a.langName == "js" and _in_open_regex(a, caret - 1):
		return False
	if ch in "\"'`":
		if ch == "`" and a.langName not in ("js", "generic"):
			return False
		previous = a.text[caret - 2:caret - 1] if caret >= 2 else ""
		if previous and (previous.isalnum() or previous in "_#@"):
			return False
		if a.text[max(0, caret - 3):caret - 1] == ch * 2:
			# The third quote of a triple-quoted string.
			return False
		if ch == "'" and a.lang["charQuote"]:
			# A character literal or a lone apostrophe (a Rust lifetime): the
			# code text keeps the quotes, so an odd count before it means it
			# closes one.
			return a.code[lineStart:caret - 1].count(ch) % 2 == 0
		# Only a quote that starts a string gets its partner; not one that
		# closes a string, also a multi-line one ending on this line.
		return _quote_role(a, caret) == "open"
	return True


def _in_open_regex(a, pos):
	"""True when pos sits in a JavaScript regex literal on its line, also
	one still being typed (no closing "/" yet)."""
	lineStart = a.line_bounds(a.line_index(pos))[0]
	k = lineStart
	while True:
		k = a.code.find("/", k, pos)
		if k < 0:
			return False
		if a.code[k + 1:k + 2] in ("/", "*"):
			return False
		if analyzer.regex_can_start(a.text, k):
			end = analyzer._js_regex_end(a.text, k)
			if end is None or end > pos:
				return True
			k = end
		else:
			k += 1


def _quote_role(a, caret):
	"""What the quote typed just before caret did: "open" (it starts a
	string), "close" (it ends one) or None (it is inside a string, such as
	the first quotes of a closing \"\"\", or in a comment)."""
	span = a.string_at(caret - 1)
	if span is None:
		return None
	start, end, closed = span
	if start == caret - 1:
		return "open"
	quote = a.text[caret - 1]
	if start == caret - 2 and a.text[start:caret + 1] == quote * 3:
		# The second quote of "" next to the one auto-close added: the three
		# read as an opening """, but the typed one closed the empty string.
		return "close"
	if closed and end == caret:
		return "close"
	return None


def stale_apostrophe(a, caret, ch):
	"""In a language with character literals, after ch was typed between
	apostrophes that can no longer form one ("'ab", "'a " of a Rust lifetime
	or loop label): True when the apostrophe right after the caret, which
	auto-close added, should go."""
	if not a.lang["charQuote"] or ch in "'\\" or a.text[caret:caret + 1] != "'":
		return False
	lineStart = a.line_bounds(a.line_index(caret))[0]
	q = a.text.rfind("'", lineStart, caret)
	if q < 0 or a.code[q] != "'" or a.code[caret] != "'":
		return False
	body = a.text[q + 1:caret]
	return len(body) >= 2 and not body.startswith("\\")

def autoclose_skip(a, caret, ch):
	"""After a closing character ch was typed just before caret, with the same
	character right after the caret: True when one of them is left over, so
	the one after the caret should be removed, as if the user typed over it.
	For brackets: a closing bracket of that kind without a partner in the
	run of closing brackets starting at the caret (so nested pairs work).
	For quotes: when the typed quote closed a string (an even number of
	delimiters from the start of the line up to the caret)."""
	if a.text[caret:caret + 1] != ch:
		return False
	if ch in ")]}":
		end = caret
		while end < len(a.code) and a.code[end] in ")]} \t":
			end += 1
		if any(b.char == ch and caret <= b.offset < end for b in a.strayClosers):
			return True
		# A closer typed in an interpolation ("{len(items)|)}"): it closed
		# its bracket, and the one auto-close added now reads as string text.
		lineStart, lineEnd = a.line_bounds(a.line_index(caret))
		line = a.text[lineStart:lineEnd]
		# The line's own text must have one closer too many: Swift's "\(f(x))"
		# ends with the interpolation's own ")", which must stay.
		if line.count(ch) <= line.count({")": "(", "]": "[", "}": "{"}[ch]) or a.code[caret:caret + 1] == ch:
			return False
		typed = a.bracket_at(caret - 1)
		if typed is not None and typed.char == ch and typed.partner is not None:
			return True
		# The ")" that ends a Swift interpolation, typed before the one
		# auto-close added inside it.
		return (
			a.langName == "swift" and ch == ")" and a.code[caret - 1:caret] != ch
			and "\\(" in a.text[lineStart:caret]
		)
	if ch in "\"'`":
		if a.code[caret - 1:caret] != ch:
			# The typed quote is inside a string or comment (blanked): it
			# neither opens nor closes anything.
			return False
		if ch == "'" and a.lang["charQuote"]:
			lineStart = a.line_bounds(a.line_index(caret))[0]
			return a.code[lineStart:caret].count(ch) % 2 == 0
		return _quote_role(a, caret) == "close"
	return False
