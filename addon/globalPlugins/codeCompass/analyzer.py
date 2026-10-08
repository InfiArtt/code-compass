# -*- coding: UTF-8 -*-
# Code Compass - source structure analyzer.
# Pure Python (no NVDA imports) so it can be unit-tested outside NVDA.
#
# The analysis works in two passes:
#   1. Blank out comments and string contents (same length, line breaks kept),
#      so offsets in the "code" text match offsets in the original text.
#   2. Scan the blanked text for brackets and outline patterns.

import bisect
import re


def _(text):
	"""Translation hook. The NVDA plugin replaces this with its translator;
	outside NVDA (tests) messages stay in English."""
	return text


OPENERS = "([{"
CLOSERS = ")]}"
PAIR = {")": "(", "]": "[", "}": "{", "(": ")", "[": "]", "{": "}"}

#: Spoken names for bracket characters (translated at use, see bracket_name).
BRACKET_NAMES = {"{": "brace", "(": "paren", "[": "bracket"}


def bracket_name(ch):
	"""Spoken name of a bracket character, either opening or closing."""
	if ch in CLOSERS:
		ch = PAIR[ch]
	return _(BRACKET_NAMES[ch])

# --- Language definitions -------------------------------------------------

#: name -> settings.
#: line: line comment markers. block: (start, end) comment pairs.
#: strings: string delimiters. multiline: delimiters that may span lines.
#: charQuote: a single quote is a char literal (C, Rust...), so an apostrophe
#: that does not form a short literal is ordinary code.
#: hashNeedsSpace: "#" only starts a comment at a word boundary (shell, YAML).
#: indentScopes: scopes are defined by indentation (Python, YAML).
_BASE = dict(
	line=(), block=(), strings=('"', "'"), multiline=(),
	charQuote=False, hashNeedsSpace=False, indentScopes=False,
)


def _lang(**kw):
	d = dict(_BASE)
	d.update(kw)
	return d


LANGUAGES = {
	"python": _lang(
		line=("#",), strings=('"""', "'''", '"', "'"),
		multiline=('"""', "'''"), indentScopes=True,
	),
	"clike": _lang(line=("//",), block=(("/*", "*/"),), charQuote=True),
	"js": _lang(
		line=("//",), block=(("/*", "*/"),), strings=('"', "'", "`"),
		multiline=("`",),
	),
	"swift": _lang(
		line=("//",), block=(("/*", "*/"),), strings=('"""', '"'),
		multiline=('"""',),
	),
	"php": _lang(line=("//", "#"), block=(("/*", "*/"),)),
	"css": _lang(block=(("/*", "*/"),)),
	"hash": _lang(line=("#",), hashNeedsSpace=True),
	"yaml": _lang(line=("#",), hashNeedsSpace=True, indentScopes=True),
	"lua": _lang(line=("--",), block=(("--[[", "]]"),)),
	"sql": _lang(line=("--",), block=(("/*", "*/"),)),
	"generic": _lang(line=("//",), block=(("/*", "*/"),), charQuote=True),
}

#: File extension -> language name.
EXTENSIONS = {
	"py": "python", "pyw": "python",
	"c": "clike", "h": "clike", "cpp": "clike", "cc": "clike", "cxx": "clike",
	"hpp": "clike", "hh": "clike", "cs": "clike", "java": "clike",
	"rs": "clike", "go": "clike", "kt": "clike", "kts": "clike",
	"scala": "clike", "m": "clike", "mm": "clike", "ino": "clike",
	"scss": "clike", "less": "clike",
	"js": "js", "jsx": "js", "mjs": "js", "cjs": "js", "ts": "js", "tsx": "js",
	"dart": "js", "json": "js", "jsonc": "js",
	"swift": "swift",
	"php": "php",
	"css": "css",
	"rb": "hash", "sh": "hash", "bash": "hash", "zsh": "hash", "pl": "hash",
	"r": "hash", "toml": "hash", "ps1": "hash", "psm1": "hash",
	"yaml": "yaml", "yml": "yaml",
	"lua": "lua",
	"sql": "sql",
}

_EXT_RE = re.compile(r"\.([A-Za-z0-9]+)\b")


def extension_from_title(title):
	"""File extension (lower case, no dot) of the file named in an editor
	window title, preferring known code extensions; None when there is none."""
	if not title:
		return None
	# Only look at the part before the application name, which follows the
	# last separator ("main - Copy.py - Notepad").
	head = re.sub(r"\s+[-\u2013\u2014]\s+(?:(?!\s[-\u2013\u2014]\s).)*$", "", title.strip())
	# "main.rs - three.js - Visual Studio Code": the file comes first.
	segments = [s for s in re.split(r"\s+[-\u2013\u2014]\s+", head) if s]
	allExts = []
	for segment in segments:
		# Notepad++ shows the whole path: a folder named "three.js" says nothing.
		exts = [e.lower() for e in _EXT_RE.findall(re.split(r"[\\/]", segment)[-1])]
		for ext in reversed(exts):
			if ext in EXTENSIONS:
				return ext
		allExts.extend(exts)
	return allExts[-1] if allExts else None


def language_from_title(title):
	"""Guess the language from an editor window title such as
	"main.py - Notepad" or "*C:\\src\\app.swift - Notepad++". Returns a key of
	LANGUAGES; "generic" when nothing matches."""
	return EXTENSIONS.get(extension_from_title(title), "generic")


# --- Pass 1: blank comments and strings ----------------------------------

_CHAR_LITERAL = re.compile(
	r"'(?:\\(?:u\{[0-9A-Fa-f]+\}|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|.)|[^\\'\r\n])'"
)
_NEWLINES = re.compile(r"\r\n|\r|\n")
_NOT_NEWLINE = re.compile(r"[^\r\n]")


def _declares_class(code):
	"""True when a header line declares a class-like type. Only the part
	before the first "(" counts: a parameter called "record" or typed
	"object" ("function save(record) {") declares no class."""
	return bool(_CLASS_HEADER.search(code.split("(", 1)[0]))


def _continues_header(code):
	"""True for a line that continues a declaration header: one starting
	with ":", ",", "extends", "implements", "where" and similar."""
	stripped = code.strip()
	word = re.match(r"[A-Za-z_]\w*", stripped)
	return stripped.startswith((":", ",")) or (word is not None and word.group(0) in ("extends", "implements", "where", "with", "throws"))


def _blank(segment):
	"""Replace everything except line breaks with spaces."""
	return _NOT_NEWLINE.sub(" ", segment)


_tokenCache = {}


def _token_re(langName, lang):
	rx = _tokenCache.get(langName)
	if rx is None:
		starts = list(lang["line"]) + [b[0] for b in lang["block"]] + list(lang["strings"])
		if langName == "js":
			# Regex literals ("/[`'"]/g") hold quotes that start no string.
			starts.append("/")
		# Longest first so that '"""' wins over '"' and '--[[' over '--'.
		starts.sort(key=len, reverse=True)
		rx = re.compile("|".join(re.escape(s) for s in starts))
		_tokenCache[langName] = rx
	return rx


def _find_string_end(text, pos, delim, multiline):
	"""Return (end, closed): end is the offset just past the closing
	delimiter. A single-line string left open ends at the line break."""
	n = len(text)
	while pos < n:
		ch = text[pos]
		if ch == "\\":
			# An escaped CRLF (Notepad's line break) counts as one break.
			pos += 3 if text.startswith("\r\n", pos + 1) else 2
			continue
		if text.startswith(delim, pos):
			return pos + len(delim), True
		if not multiline and ch in "\r\n":
			return pos, False
		pos += 1
	return n, False


def strip_code(text, langName, spans=None, comments=None):
	"""Return text with comments and string contents replaced by spaces.
	Quotes are kept so patterns still see that a string was there. When spans
	is a list, the (start, end, closed) of every string is appended to it, so
	callers can tell which lines start inside a multi-line string. When comments is
	a list, the (start, end) of every comment is appended to it."""
	lang = LANGUAGES.get(langName) or LANGUAGES["generic"]
	tokenRe = _token_re(langName, lang)
	blockEnds = dict(lang["block"])
	out = []
	pos = 0
	n = len(text)
	while pos < n:
		m = tokenRe.search(text, pos)
		if not m:
			break
		tok = m.group(0)
		start = m.start()
		out.append(text[pos:start])
		if tok in lang["line"]:
			if (
				tok == "#" and lang["hashNeedsSpace"]
				and start > 0 and text[start - 1] not in " \t\r\n;"
			):
				out.append(tok)
				pos = start + 1
				continue
			nl = _NEWLINES.search(text, start)
			end = nl.start() if nl else n
			out.append(_blank(text[start:end]))
			if comments is not None:
				comments.append((start, end))
			pos = end
		elif tok in blockEnds:
			close = text.find(blockEnds[tok], start + len(tok))
			end = n if close < 0 else close + len(blockEnds[tok])
			# Not recorded in spans: code after "*/" on a comment's last line
			# is a statement of its own, not a continuation.
			out.append(_blank(text[start:end]))
			if comments is not None:
				comments.append((start, end))
			pos = end
		elif tok == "'" and lang["charQuote"]:
			lit = _CHAR_LITERAL.match(text, start)
			if lit:
				end = lit.end()
				out.append("'" + _blank(text[start + 1:end - 1]) + "'")
				pos = end
			else:
				# A lone apostrophe (e.g. a Rust lifetime): plain code.
				out.append(tok)
				pos = start + 1
		elif tok == "/":
			# Only in JavaScript: a regex literal, or division.
			end = _js_regex_end(text, start)
			if end is None:
				out.append(tok)
				pos = start + 1
			else:
				out.append("/" + _blank(text[start + 1:end - 1]) + "/")
				pos = end
		else:
			bodyStart = start + len(tok)
			end, closed, segments, closeLength = _string_end(text, bodyStart, tok, langName, lang)
			bodyEnd = end - closeLength if closed else end
			body = list(_blank(text[bodyStart:bodyEnd]))
			for segStart, segEnd in segments:
				segEnd = min(segEnd, bodyEnd)
				if segStart < segEnd:
					# The code inside an interpolation counts as code, with its
					# own strings and comments blanked in turn.
					body[segStart - bodyStart:segEnd - bodyStart] = strip_code(text[segStart:segEnd], langName)
			out.append(tok + "".join(body) + text[bodyEnd:end])
			if spans is not None:
				spans.append((start, end, closed))
			pos = end
	out.append(text[pos:])
	return "".join(out)


_PY_PREFIX = re.compile(r"(?<![\w$])[rRbBuUfF]{1,2}$")


def _interpolation_kind(text, start, tok, langName):
	"""Which code-in-string syntax the string starting at start uses, as
	(kind, raw), or None. kind: "f" (Python f-string braces; raw is True for
	rf-strings), "js" (template literal ${...}) or "swift" (\\(...); raw is
	the number of "#" before the quote, as in #"...\\#(x)..."#)."""
	if langName == "python":
		prefix = _PY_PREFIX.search(text, max(0, start - 2), start)
		if prefix and "f" in prefix.group(0).lower():
			return "f", "r" in prefix.group(0).lower()
	elif langName == "js" and tok == "`":
		return "js", 0
	elif langName == "swift" and tok in ('"', '"""'):
		hashes = 0
		while start - hashes - 1 >= 0 and text[start - hashes - 1] == "#":
			hashes += 1
		return "swift", hashes
	return None


def _string_end(text, pos, tok, langName, lang):
	"""For a string whose opening tok ends just before pos: (end, closed,
	segments, closeLength), segments being the code inside interpolations."""
	multiline = tok in lang["multiline"]
	info = _interpolation_kind(text, pos - len(tok), tok, langName)
	if info:
		kind, raw = info
		delim = tok + "#" * raw if kind == "swift" else tok
		end, closed, segments = _scan_interpolated(text, pos, delim, multiline, kind, raw, langName)
		return end, closed, segments, len(delim)
	end, closed = _find_string_end(text, pos, tok, multiline)
	return end, closed, (), len(tok)


def _skip_string(text, pos, langName):
	"""If a string of langName starts at pos, the offset just past it
	(interpolations included); else None."""
	lang = LANGUAGES.get(langName) or LANGUAGES["generic"]
	for tok in sorted(lang["strings"], key=len, reverse=True):
		if text.startswith(tok, pos):
			if tok == "'" and lang["charQuote"]:
				lit = _CHAR_LITERAL.match(text, pos)
				return lit.end() if lit else None
			return _string_end(text, pos + len(tok), tok, langName, lang)[0]
	return None


def _code_end(text, pos, stop, langName, limit=None):
	"""Scan code from pos to the first character in stop at bracket depth 0
	(nested strings, also interpolated ones, are skipped). Returns its offset,
	or limit (default: the end of text) when there is none before it."""
	n = len(text) if limit is None else limit
	depth = 0
	while pos < n:
		ch = text[pos]
		if depth == 0 and ch in stop:
			return pos
		if ch in "([{":
			depth += 1
		elif ch in ")]}":
			if depth == 0:
				return pos
			depth -= 1
		elif ch == "/" and langName == "js":
			if text.startswith("//", pos):
				nl = _NEWLINES.search(text, pos)
				pos = min(n, nl.start() if nl else n)
				continue
			if text.startswith("/*", pos):
				close = text.find("*/", pos + 2, n)
				pos = n if close < 0 else close + 2
				continue
			end = _js_regex_end(text, pos)
			if end is not None and end <= n:
				pos = end
				continue
		else:
			end = _skip_string(text, pos, langName)
			if end is not None:
				pos = max(end, pos + 1)
				continue
		pos += 1
	return n


def _f_field(text, pos, langName, limit):
	"""An f-string replacement field whose "{" is just before pos. Returns
	(segments, close): the expression parts that are code (the expression,
	and nested fields inside the format spec) and the offset of the closing
	"}", or limit when the field does not close before it.
	Conversions (!r) and format specs (:>10, :%Y-%m-%d) are not code."""
	segments = []
	exprEnd = _code_end(text, pos, "!:=}", langName, limit)
	# "!=" and "==" are comparisons, ":=" a walrus inside brackets is already
	# skipped; "=" followed by "}", "!" or ":" is the self-documenting form.
	while exprEnd < limit and text[exprEnd] in "!=" and (
		text[exprEnd + 1:exprEnd + 2] == "=" or text[exprEnd - 1:exprEnd] in ("<", ">", "=", "!")
	):
		exprEnd = _code_end(text, exprEnd + 1, "!:=}", langName, limit)
	segments.append((pos, exprEnd))
	k = exprEnd
	# Nested fields in the format spec ("{x:>{width}}"): a loop, not
	# recursion, so a long run of unclosed fields cannot overflow the stack.
	depth = 0
	while k < limit:
		ch = text[k]
		if ch == "{":
			innerEnd = _code_end(text, k + 1, "!:}", langName, limit)
			segments.append((k + 1, innerEnd))
			depth += 1
			k = innerEnd
			continue
		if ch == "}":
			if depth == 0:
				return segments, k
			depth -= 1
		k += 1
	return segments, limit


def _scan_interpolated(text, pos, delim, multiline, kind, raw, langName):
	"""Like _find_string_end for a string with interpolations: returns
	(end, closed, segments), where segments are the (start, end) offsets of
	the code inside it. Strings nested in the code do not end the string. A
	one-line string ends at the line break, also inside an unclosed field."""
	n = len(text)
	if multiline:
		limit = n
	else:
		nl = _NEWLINES.search(text, pos)
		limit = nl.start() if nl else n
	segments = []
	# Swift raw strings escape and interpolate with "\#" ("\##"...).
	escape = "\\" + "#" * raw if kind == "swift" else "\\"
	while pos < limit:
		ch = text[pos]
		close = None
		if kind == "f":
			if text.startswith(("{{", "}}"), pos):
				pos += 2
				continue
			if ch == "\\" and raw:
				# A raw string keeps its backslashes; one only keeps a quote or
				# another backslash from counting ("rf'\{x}'" has a field).
				pos += 2 if text[pos + 1:pos + 2] in ("\\", delim[0]) else 1
				continue
			if text.startswith("\\N{", pos):
				close = text.find("}", pos, limit)
				pos = limit if close < 0 else close + 1
				continue
			if ch == "{":
				inner, close = _f_field(text, pos + 1, langName, limit)
				segments.extend(inner)
		elif kind == "js":
			if text.startswith("${", pos):
				close = _code_end(text, pos + 2, "}", langName, limit)
				segments.append((pos + 2, close))
		elif kind == "swift":
			if text.startswith(escape + "(", pos):
				start = pos + len(escape) + 1
				close = _code_end(text, start, ")", langName, limit)
				segments.append((start, close))
		if close is not None:
			if close >= limit:
				return limit, False, segments
			pos = close + 1
			continue
		if text.startswith(escape, pos):
			after = pos + len(escape)
			# An escaped CRLF (Notepad's line break) counts as one break.
			pos = after + (2 if text.startswith("\r\n", after) else 1)
			continue
		if text.startswith(delim, pos):
			return pos + len(delim), True, segments
		pos += 1
	return min(pos, limit), False, segments


#: What may come before a JavaScript regex literal ("/x/"): an operator or
#: punctuation, not a value (then "/" divides). Not "<" or ">", which JSX
#: uses around "/" ("</div>").
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%^")
_REGEX_AFTER_WORDS = frozenset((
	"return", "typeof", "case", "do", "else", "in", "of", "new", "delete",
	"void", "throw", "yield", "await", "instanceof",
))


def regex_can_start(text, start):
	"""True when a "/" at start may begin a JavaScript regex literal: after
	an operator, punctuation, "=>" or a keyword like return, not after a
	value (division), and not "/>" (a JSX tag's end)."""
	if text[start + 1:start + 2] == ">":
		return False
	j = start - 1
	while j >= 0 and text[j] in " \t\r\n":
		j -= 1
	if j < 0:
		return True
	c = text[j]
	if c.isalnum() or c in "_$":
		w = j
		while w > 0 and (text[w - 1].isalnum() or text[w - 1] in "_$"):
			w -= 1
		return text[w:j + 1] in _REGEX_AFTER_WORDS
	if c == ">":
		return text[j - 1:j] == "="
	return c in _REGEX_AFTER


def _js_regex_end(text, start):
	"""If a JavaScript regex literal starts at start (a "/"), the offset just
	past its closing "/"; else None. Regex literals stay on one line."""
	if not regex_can_start(text, start):
		return None
	k = start + 1
	n = len(text)
	inClass = False
	while k < n and text[k] not in "\r\n":
		c = text[k]
		if c == "\\":
			k += 2
			continue
		if c == "[":
			inClass = True
		elif c == "]":
			inClass = False
		elif c == "/" and not inClass:
			return k + 1
		k += 1
	return None


# --- Pass 2: brackets and lines -------------------------------------------

_BRACKET_RE = re.compile(r"[()\[\]{}]")
_LEADING_CLOSERS = re.compile(r"^[\s)\]}]+")
#: Same, for Pattern.match at a position (where "^" would not match).
_CLOSERS_RUN = re.compile(r"[\s)\]}]+")
#: A line holding only closing brackets (and separators such as ";" or ",").
_CLOSER_ONLY = re.compile(r"^\s*[)\]}][\s)\]};,]*$")


class Bracket(object):
	__slots__ = ("offset", "char", "partner", "depth")

	def __init__(self, offset, char, depth):
		self.offset = offset
		self.char = char
		#: Offset of the matching bracket, or None when unmatched.
		self.partner = None
		#: Brackets open around this one: before it opens, or after it closes.
		self.depth = depth


class Analysis(object):
	"""Structure of one document. Build once per text, query many times."""

	def __init__(self, text, langName="generic"):
		self.text = text
		self.langName = langName if langName in LANGUAGES else "generic"
		self.lang = LANGUAGES[self.langName]
		#: (start, end, closed) of every string, in order.
		self.stringSpans = spans = []
		#: (start, end) of every comment, in order.
		self.commentSpans = []
		self.code = strip_code(text, self.langName, spans, self.commentSpans)
		self._stringStarts = [sp[0] for sp in spans]
		self._commentStarts = [c[0] for c in self.commentSpans]
		self.lineStarts = [0] + [m.end() for m in _NEWLINES.finditer(text)]
		#: Lines that start inside a multi-line string or comment.
		self._continuation = set()
		for start, end, _closed in spans:
			first = self.line_index(start) + 1
			while first < len(self.lineStarts) and self.lineStarts[first] < end:
				self._continuation.add(first)
				first += 1
		self.brackets = []
		#: Closing brackets with no opener.
		self.strayClosers = []
		#: Openers that never closed.
		self.unclosed = []
		self._scan_brackets()
		self._bracketOffsets = [b.offset for b in self.brackets]
		self._compute_line_depths()
		self._outline = None

	# Brackets -------------------------------------------------------------

	def _scan_brackets(self):
		stack = []
		for m in _BRACKET_RE.finditer(self.code):
			ch = m.group(0)
			off = m.start()
			if ch in OPENERS:
				b = Bracket(off, ch, len(stack))
				stack.append(b)
				self.brackets.append(b)
				continue
			want = PAIR[ch]
			# Nearest opener of the right kind; anything above it was left open.
			idx = len(stack) - 1
			while idx >= 0 and stack[idx].char != want:
				idx -= 1
			if idx < 0:
				b = Bracket(off, ch, len(stack))
				self.brackets.append(b)
				self.strayClosers.append(b)
				continue
			opener = stack[idx]
			del stack[idx:]
			b = Bracket(off, ch, len(stack))
			b.partner = opener.offset
			opener.partner = off
			self.brackets.append(b)
		self.unclosed = [b for b in self.brackets if b.char in OPENERS and b.partner is None]

	def bracket_at(self, offset):
		i = bisect.bisect_left(self._bracketOffsets, offset)
		if i < len(self.brackets) and self.brackets[i].offset == offset:
			return self.brackets[i]
		return None

	def bracket_near(self, offset):
		"""Bracket under the caret, or just before it."""
		return self.bracket_at(offset) or (self.bracket_at(offset - 1) if offset > 0 else None)

	def enclosing(self, offset):
		"""Open brackets that contain offset, outermost first."""
		stack = []
		end = bisect.bisect_left(self._bracketOffsets, offset)
		for b in self.brackets[:end]:
			if b.char in OPENERS:
				stack.append(b)
			elif b.partner is not None:
				while stack and stack[-1].offset != b.partner:
					stack.pop()
				if stack:
					stack.pop()
		return stack

	# Lines ----------------------------------------------------------------

	@property
	def lineCount(self):
		return len(self.lineStarts)

	def line_index(self, offset):
		return bisect.bisect_right(self.lineStarts, offset) - 1

	def line_bounds(self, index):
		"""(start, end) of a line; end excludes the line break."""
		start = self.lineStarts[index]
		if index + 1 < len(self.lineStarts):
			end = self.lineStarts[index + 1]
			while end > start and self.text[end - 1] in "\r\n":
				end -= 1
		else:
			end = len(self.text)
		return start, end

	def line_text(self, index):
		start, end = self.line_bounds(index)
		return self.text[start:end]

	def line_code(self, index):
		start, end = self.line_bounds(index)
		return self.code[start:end]

	def line_depth(self, index):
		"""Nesting level of a line the way indentation would show it: brackets
		open at the line start, minus closing brackets that lead the line (so
		a line holding only "}" sits at the outer level)."""
		return self._lineDepths[index]

	def line_inner_bracket(self, index):
		"""Character of the innermost bracket a line sits in, or None."""
		return self._lineInner[index]

	def _compute_line_depths(self):
		#: Brackets open at each line start.
		self._startDepths = []
		self._lineDepths = []
		self._lineInner = []
		#: The innermost open bracket (a Bracket) at each line, or None.
		self._lineInnerBracket = []
		brackets = self.brackets
		code = self.code
		# The open brackets, outermost first.
		stack = []
		bi = 0
		for li in range(len(self.lineStarts)):
			start, end = self.line_bounds(li)
			depth = len(stack)
			self._startDepths.append(depth)
			lineDepth = depth
			lead = _CLOSERS_RUN.match(code, start, end)
			leadEnd = lead.end() if lead else start
			k = bi
			while k < len(brackets) and brackets[k].offset < leadEnd:
				if brackets[k].partner is not None:
					lineDepth = brackets[k].depth
				k += 1
			lineDepth = max(0, min(lineDepth, depth))
			self._lineDepths.append(lineDepth)
			inner = stack[lineDepth - 1] if lineDepth else None
			self._lineInnerBracket.append(inner)
			self._lineInner.append(inner.char if inner else None)
			nextStart = self.lineStarts[li + 1] if li + 1 < len(self.lineStarts) else len(code)
			while bi < len(brackets) and brackets[bi].offset < nextStart:
				b = brackets[bi]
				if b.char in OPENERS:
					del stack[b.depth:]
					stack.append(b)
				elif b.partner is not None:
					del stack[b.depth:]
				bi += 1

	def string_at(self, offset):
		"""(start, end, closed) of the string holding offset (its quotes
		included), or None."""
		i = bisect.bisect_right(self._stringStarts, offset) - 1
		if i >= 0 and offset < self.stringSpans[i][1]:
			return self.stringSpans[i]
		return None

	def in_comment(self, offset):
		"""True when offset is inside a comment."""
		i = bisect.bisect_right(self._commentStarts, offset) - 1
		return i >= 0 and offset < self.commentSpans[i][1]

	def is_code_line(self, index):
		"""True when the line holds code (not blank, not only a comment, not
		the inside of a multi-line string)."""
		return bool(self.line_code(index).strip())

	def is_statement_start(self, index):
		"""A code line that does not continue an open bracket or a multi-line
		string (such as the closing quotes of a docstring at column 0)."""
		return (
			self.is_code_line(index) and self._startDepths[index] == 0
			and index not in self._continuation
		)

	# Scope description ----------------------------------------------------

	def header_for(self, bracket):
		"""Short description of what a bracket opens, taken from its line."""
		li = self.line_index(bracket.offset)
		start, _end = self.line_bounds(li)
		before = self.text[start:bracket.offset]
		before = _LEADING_CLOSERS.sub("", before).strip()
		if not before and bracket.char == "{":
			# Allman style: the header sits on an earlier line.
			j = li - 1
			while j >= 0 and not self.is_code_line(j):
				j -= 1
			if j >= 0:
				before = self.line_text(j).strip()
		before = shorten(before)
		if bracket.char == "{":
			return before or _("block")
		label = bracket_name(bracket.char)
		return "%s %s" % (before, label) if before else label

	def describe_closer(self, offset):
		"""What the closing bracket at offset closes, as a short sentence, or
		None when there is no closing bracket there."""
		b = self.bracket_at(offset)
		if b is None or b.char not in CLOSERS:
			return None
		if b.partner is None:
			return _("nothing to close")
		opener = self.bracket_at(b.partner)
		what = self.header_for(opener)
		stack = self.enclosing(offset)
		if stack and stack[-1].offset != opener.offset:
			# It skipped over a bracket that is still open.
			inner = stack[-1]
			return _("closes {what}, but {name} from line {line} is still open").format(
				what=what, name=bracket_name(inner.char), line=self.line_index(inner.offset) + 1)
		return _("closes {what}").format(what=what)

	def leading_closer(self, index):
		"""Offset of the closing bracket that starts a line, or None."""
		start, end = self.line_bounds(index)
		code = self.code[start:end]
		stripped = code.lstrip()
		if stripped and stripped[0] in CLOSERS:
			return start + len(code) - len(stripped)
		return None

	def scopes(self, offset):
		"""Where offset sits, outermost scope first, as (lineIndex, text)."""
		items = [(self.line_index(b.offset), self.header_for(b)) for b in self.enclosing(offset)]
		if self.lang["indentScopes"]:
			items.extend(self._indent_scopes(offset))
			items.sort(key=lambda item: item[0])
		return items

	def _indent_scopes(self, offset):
		li = self.line_index(offset)
		# Reference indentation: the caret line, or for a blank/continuation
		# line, the statement above it (one deeper if it opens a block).
		j = li
		while j >= 0 and not self.is_statement_start(j):
			j -= 1
		if j < 0:
			return []
		ind = indent_width(self.line_text(j))
		if j == li:
			ref = ind
			j -= 1
		else:
			ref = ind + 1 if self.line_code(j).rstrip().endswith(":") else ind
		items = []
		while j >= 0 and ref > 0:
			if self.is_statement_start(j):
				ind = indent_width(self.line_text(j))
				if ind < ref:
					items.append((j, shorten(self.line_text(j).strip())))
					ref = ind
			j -= 1
		items.reverse()
		return items

	# Blocks (for moving to a block's start or end) --------------------------

	def blocks(self, offset):
		"""Blocks around offset, outermost first. Bracket blocks always count;
		in indentation languages, indented blocks count too."""
		items = [
			Block(b.offset, b.partner, self.line_index(b.partner) if b.partner is not None else None)
			for b in self.enclosing(offset)
		]
		if self.lang["indentScopes"]:
			for li, _text in self._indent_scopes(offset):
				last = self._indent_block_last_line(li)
				items.append(Block(self.first_char(li), self.first_char(last), last, indented=True))
			items.sort(key=lambda b: b.start)
		return items

	def first_char(self, index):
		"""Offset of the first non-blank character of a line."""
		start, end = self.line_bounds(index)
		text = self.text[start:end]
		return start + len(text) - len(text.lstrip())

	def _indent_block_last_line(self, header, limit=None):
		"""Last line of the block a header line opens: lines that follow it
		while indented deeper, plus continuation lines (open brackets and
		multi-line strings, even unterminated ones while typing). limit is
		the last line the block may reach."""
		headerIndent = indent_width(self.line_text(header))
		last = header
		stop = self.lineCount if limit is None else min(self.lineCount, limit + 1)
		for j in range(header + 1, stop):
			if self.is_statement_start(j):
				if indent_width(self.line_text(j)) <= headerIndent:
					break
				last = j
			elif self.is_code_line(j) or j in self._continuation:
				last = j
		return last

	def block_range(self, block):
		"""(start, end) covering the whole lines of a block, line break
		included, or None when the block never closes."""
		if block.indented:
			endLine = block.endLine
		elif block.end is None:
			return None
		else:
			endLine = self.line_index(block.end)
		startLine = self.line_index(block.start)
		start = self.lineStarts[startLine]
		end = self.lineStarts[endLine + 1] if endLine + 1 < self.lineCount else len(self.text)
		return start, end

	# Line navigation ------------------------------------------------------

	def _nav_level(self, index):
		if self.lang["indentScopes"]:
			return indent_width(self.line_text(index))
		return self._lineDepths[index]

	def _is_nav_line(self, index):
		"""Lines that same-level navigation stops on: statements, not blank
		lines, comments, or lines holding only closing brackets."""
		if self.lang["indentScopes"]:
			return self.is_statement_start(index)
		return (
			self.is_code_line(index) and index not in self._continuation
			and not _CLOSER_ONLY.match(self.line_code(index))
		)

	def same_level_line(self, index, step):
		"""Next (step=1) or previous (step=-1) line at the same level as line
		index, without leaving the block. None at the block's edge."""
		ref = index
		while ref >= 0 and not self._is_nav_line(ref):
			ref -= 1
		level = self._nav_level(ref) if ref >= 0 else 0
		j = index + step
		while 0 <= j < self.lineCount:
			if self._is_nav_line(j):
				lv = self._nav_level(j)
				if lv == level:
					return j
				if lv < level:
					return None
			elif self.is_code_line(j) and not self.lang["indentScopes"] and self._lineDepths[j] < level:
				# A closing-bracket line ends the block.
				return None
			j += step
		return None

	def declaration_near(self, index, step):
		"""Next (step=1) or previous (step=-1) outline item from line index."""
		items = self.outline()
		if step > 0:
			return next((item for item in items if item.line > index), None)
		return next((item for item in reversed(items) if item.line < index), None)

	# Problems -------------------------------------------------------------

	def problems(self):
		"""Unbalanced brackets as (lineIndex, message), in document order."""
		items = []
		for b in self.unclosed:
			li = self.line_index(b.offset)
			items.append((li, _("unclosed {name} on line {line}: {text}").format(
				name=bracket_name(b.char), line=li + 1, text=shorten(self.line_text(li).strip()))))
		for b in self.strayClosers:
			li = self.line_index(b.offset)
			items.append((li, _("extra closing {name} on line {line}: {text}").format(
				name=bracket_name(b.char), line=li + 1, text=shorten(self.line_text(li).strip()))))
		items.sort(key=lambda item: item[0])
		return items

	# Outline --------------------------------------------------------------

	def outline(self):
		"""Functions, classes and similar declarations in document order, each
		linked to its parent and children. Computed once per analysis."""
		if self._outline is None:
			self._outline = self._build_outline()
		return self._outline

	def _build_outline(self):
		patterns = _OUTLINE_PATTERNS.get(self.langName, _OUTLINE_PATTERNS["default"])
		indentScopes = self.lang["indentScopes"]
		items = []
		for li in range(self.lineCount):
			if li in self._continuation:
				# Inside a multi-line string: code in its interpolations
				# ("${render(x)}") is not a declaration.
				continue
			codeLine = self.line_code(li)
			if self.langName == "clike":
				# "[HttpGet] public X Index() {", "[[nodiscard]] bool f() {":
				# match after the attributes; a line of attributes only is none.
				attrs = _LEADING_ATTRIBUTES.match(codeLine)
				if attrs:
					codeLine = " " * attrs.end() + codeLine[attrs.end():]
					if not codeLine.strip():
						continue
			if _CSS_AT_RULE.match(codeLine):
				# "@media screen and (max-width: 600px) {" (CSS, SCSS, Less).
				continue
			if self.langName != "python" and codeLine.lstrip().startswith("@"):
				# "@Input() set value(v) {", "@Override public String toString() {".
				codeLine = self._without_decorators(li, codeLine)
				if not codeLine.strip():
					continue
			first = _FIRST_WORD.match(codeLine)
			if not first or first.group(1) in _CONTROL or _CALL_STATEMENT.match(codeLine):
				continue
			if not indentScopes and codeLine.lstrip().startswith(":"):
				# An initializer or supertype list (C# ": base(x)", Kotlin ": View(c)").
				continue
			for kind, rx, excluded in patterns:
				m = rx.search(codeLine)
				if not m:
					continue
				name = m.group("name")
				if name in excluded:
					continue
				if excluded is _CALL_NOT_NAMES and self._lineInner[li] in ("(", "["):
					# A pattern without a keyword on a line inside parentheses
					# is a parameter or an argument ("handler func(w)"), not a
					# declaration.
					continue
				if kind == "method" and (not self._in_class_body(li) or self._in_enum_body(li)):
					# "name(" alone on a line is a wrapped call unless it sits
					# directly in a class body; in an enum it is a constant
					# ("MERCURY(3.3e23,").
					continue
				if kind == "arrowWrap" and not self._wrapped_arrow(li):
					# "const x = (" is only a function when "=>" follows the ")".
					continue
				kind = m.groupdict().get("kind") or ("function" if kind in ("method", "arrowWrap") else kind)
				level = indent_width(codeLine) if indentScopes else self._lineDepths[li]
				item = OutlineItem(li, kind, name, level)
				item.column = m.start()
				items.append(item)
				break
		# Each declaration covers its lines: decorators, header and body. Two
		# bounds are found in one backward pass each, keeping this linear:
		# the next declaration at the same or a lower indent (indentation
		# languages), and the next one not on a line inside parentheses.
		sameOrLower = [None] * len(items)
		stack = []
		for i in range(len(items) - 1, -1, -1):
			while stack and items[stack[-1]].level > items[i].level:
				stack.pop()
			sameOrLower[i] = stack[-1] if stack else None
			stack.append(i)
		nextBoundary = [None] * len(items)
		boundary = None
		for i in range(len(items) - 1, -1, -1):
			nextBoundary[i] = boundary
			if self._lineInner[items[i].line] not in ("(", "["):
				boundary = i
		for i, item in enumerate(items):
			item.startLine = self._decorators_start(item.line)
			item.endLine = self._declaration_end_line(item, sameOrLower[i], nextBoundary[i], items)
		# The parent is the innermost earlier declaration that contains this one
		# and sits at a lower level (indent, or bracket depth). Both checks keep
		# a typo, such as an unclosed bracket while typing, from nesting every
		# later declaration inside the one before it.
		stack = []
		for item in items:
			while stack and (stack[-1].endLine < item.line or stack[-1].level >= item.level):
				stack.pop()
			if stack:
				parent = stack[-1]
				item.parentItem = parent
				item.parent = parent.name
				parent.children.append(item)
			stack.append(item)
		return items

	def _without_decorators(self, li, codeLine):
		"""codeLine with the decorators or annotations it starts with turned
		into spaces; blank when one continues onto the next line."""
		lineStart = self.lineStarts[li]
		pos = 0
		while True:
			m = _LEADING_DECORATOR.match(codeLine, pos)
			if not m or (self.langName == "clike" and _OBJC_DIRECTIVE.match(codeLine[m.start():].lstrip())):
				break
			pos = m.end()
			if codeLine[pos:pos + 1] == "(":
				opener = self.bracket_at(lineStart + pos)
				if opener is None or opener.partner is None or opener.partner >= lineStart + len(codeLine):
					return ""
				pos = opener.partner + 1 - lineStart
		return " " * pos + codeLine[pos:]

	def _in_enum_body(self, li):
		"""True when line li sits directly in an enum's body."""
		brace = self._lineInnerBracket[li]
		if brace is None:
			return False
		braceLine = self.line_index(brace.offset)
		header = self.code[self.lineStarts[braceLine]:brace.offset]
		if not header.strip():
			j = braceLine - 1
			while j >= 0 and not self.is_code_line(j):
				j -= 1
			header = self.line_code(j) if j >= 0 else ""
		return bool(re.search(r"\benum\b", header))

	def _in_class_body(self, li):
		"""True when line li sits directly inside a class-like body."""
		brace = self._lineInnerBracket[li]
		if brace is None or brace.char != "{":
			return False
		braceLine = self.line_index(brace.offset)
		before = self.code[self.lineStarts[braceLine]:brace.offset]
		if before.strip() and _declares_class(before):
			return True
		if before.strip() and not _continues_header(before):
			return False
		# Allman style ("{" alone on its line), or a heritage clause on its
		# own line ("  implements OnInit {"): the header is further up.
		j = braceLine - 1
		for _step in range(4):
			while j >= 0 and not self.is_code_line(j):
				j -= 1
			if j < 0:
				return False
			lineCode = self.line_code(j)
			if _declares_class(lineCode):
				return True
			if not _continues_header(lineCode):
				return False
			j -= 1
		return False

	def _decorators_start(self, line):
		"""First line of the decorators, annotations or attributes directly
		above a declaration (@property, @Override, C# [Attribute], Rust
		#[derive], C++ template<...>), or line itself. Blank and comment lines
		between a decorator and the declaration are allowed."""
		indent = indent_width(self.line_text(line))
		base = self._startDepths[line]
		start = line
		j = line - 1
		while j >= 0:
			# Skip blank and comment-only lines, but only keep them when a
			# decorator turns up above them.
			k = j
			while k >= 0 and not self.is_code_line(k):
				k -= 1
			if k < 0:
				break
			# A decorator may wrap over several lines inside its parentheses.
			top = k
			while top > 0 and self._startDepths[top] > base:
				top -= 1
			if indent_width(self.line_text(top)) != indent:
				break
			text = " ".join(self.line_code(n).strip() for n in range(top, k + 1))
			if not self._is_decorator(text, top, k):
				break
			start = top
			j = top - 1
		return start

	def _is_decorator(self, text, top, last):
		"""True when lines top..last (text: their code joined) hold only a
		decorator, annotation or attribute."""
		if self.langName == "clike":
			if _OBJC_DIRECTIVE.match(text):
				# Objective-C "@end", "@interface X : Y" are not decorators.
				return False
			if _ATTRIBUTE.match(text) or _RUST_ATTRIBUTE.match(text) or _TEMPLATE.match(text):
				return True
		name = _DECORATOR_NAME.match(text)
		if not name:
			return False
		if name.end() == len(text):
			return True
		if text[name.end()] != "(":
			return False
		# "@name(...)": the "(" after the name must close at the very end,
		# however deeply its arguments nest.
		lineStart = self.lineStarts[top]
		code = self.line_code(top)
		at = code.find("@")
		paren = code.find("(", at)
		opener = self.bracket_at(lineStart + paren) if paren >= 0 else None
		lastCode = self.line_code(last).rstrip()
		closeOffset = self.lineStarts[last] + len(lastCode) - 1
		return opener is not None and opener.partner == closeOffset

	def _declaration_end_line(self, item, sameOrLower, nextBoundary, items):
		"""Last line of item: the end of its indented block, of its brace body,
		or of its header when it has no body. sameOrLower and nextBoundary
		are indexes into items (or None) that bound the search."""
		if self.lang["indentScopes"]:
			# The block cannot reach the next declaration at the same or a
			# lower indent; this bound also keeps an unclosed bracket from
			# making every block run to the end of the file.
			limit = items[sameOrLower].line - 1 if sameOrLower is not None else None
			return self._indent_block_last_line(item.line, limit)
		nextLine = items[nextBoundary].line if nextBoundary is not None else self.lineCount
		opener, headerEnd = self._scan_declaration(item.line, item.column, nextLine)
		if opener is None:
			item.hasBody = False
			return headerEnd
		if opener.partner is None:
			# The body is never closed: it runs to the end of the file.
			return self.lineCount - 1
		return self.line_index(opener.partner)

	def _wrapped_arrow(self, li):
		"""For "const x = (" at the end of line li: True when the matching ")"
		is followed by an optional type and "=>", making x a function."""
		start, end = self.line_bounds(li)
		stripped = self.code[start:end].rstrip()
		b = self.bracket_at(start + len(stripped) - 1)
		if b is None or b.partner is None:
			return False
		return bool(_ARROW_AFTER.match(self.code, b.partner + 1))

	def _scan_declaration(self, line, column, nextLine):
		"""Find the body of the declaration that starts at column on line.
		Returns (opener, headerEnd): the "{" that opens the body or None, and
		the last line of the header.

		Counting starts where the declaration starts, so "forwardRef(function
		X() {" works. A "{" counts only outside the header's parentheses and
		angle brackets (default values, destructured parameters, generic
		constraints), and not right after ":" (a TypeScript object type). A ";"
		ends a declaration without a body. The header continues onto the next
		line while brackets are open, or when the line ends with a continuation
		("," ":" "=>" ... or a word such as throws, extends, where) or the next
		line starts with "{" or such a word. Otherwise the declaration has no
		body and ends where its header does."""
		code = self.code
		paren = angle = 0
		# After "=" or "=>" outside parentheses comes an expression body, where
		# "<" is a comparison, not a generic. "= (" or "= async (" or
		# "= function" starts a function expression instead: its parameters
		# and return type are still header.
		inBody = False
		eqAt = -1
		# One entry per open parenthesis: the angle depth when it opened, and
		# whether a default value ("x = a<b") has started in it.
		parens = []
		limit = min(nextLine, self.lineCount, line + 40)
		headerEnd = line
		li = line
		pos = self.lineStarts[line] + column
		while True:
			start, end = self.line_bounds(li)
			k = max(pos, start)
			while k < end:
				ch = code[k]
				if ch in "([":
					if ch == "(" and paren == 0 and inBody and _FUNCTION_VALUE.match(code[eqAt + 1:k].strip()):
						inBody = False
					paren += 1
					parens.append([angle, False])
				elif ch in ")]":
					paren = max(0, paren - 1)
					if parens:
						# A "<" left open inside the parentheses was a comparison.
						angle = parens.pop()[0]
				elif ch == "," and parens:
					parens[-1][1] = False
				elif ch == "<":
					following = code[k + 1:k + 2]
					if (
						not inBody and not (parens and parens[-1][1])
						and k > 0 and (code[k - 1].isalnum() or code[k - 1] in "_$")
						and following not in ("-", "=", "<") and not following.isdigit()
					):
						angle += 1
				elif ch == ">" and angle and code[k - 1] not in "-=":
					angle -= 1
				elif ch == "=" and code[k + 1:k + 2] != "=" and code[k - 1:k] not in ("=", "!", "<", ">"):
					if parens and angle == parens[-1][0]:
						# A default value in the parameter list.
						parens[-1][1] = True
					elif paren == 0 and angle == 0:
						inBody = True
						eqAt = k
				elif ch == ";" and paren == 0 and angle == 0:
					return None, headerEnd
				elif ch == "{" and paren == 0 and angle == 0:
					b = self.bracket_at(k)
					if code[start:k].rstrip().endswith(":") and b is not None and b.partner is not None and b.partner < end:
						# "): { ok: boolean } {" - an object type, not the body.
						k = b.partner + 1
						continue
					return b, li
				k += 1
			open_ = paren > 0 or angle > 0
			j = li + 1
			while j < limit and not self.is_code_line(j):
				j += 1
			if j >= limit:
				return None, headerEnd
			if not open_:
				swift = self.langName == "swift"
				lineCode = code[start:end].rstrip()
				following = self.line_code(j).lstrip()
				lastWord = _LAST_WORD.search(lineCode)
				firstWord = _FIRST_IDENT.match(following)
				# Swift requirements may end in "throws" or "async" with no body.
				endWords = _HEADER_END_WORDS - {"throws"} if swift else _HEADER_END_WORDS
				nextWords = _HEADER_NEXT_WORDS | {"async"} if swift else _HEADER_NEXT_WORDS
				continues = (
					lineCode.endswith(_HEADER_CONTINUES)
					or (lastWord is not None and lastWord.group(0) in endWords)
					or following.startswith(_HEADER_CONTINUATIONS)
					or (firstWord is not None and firstWord.group(0) in nextWords)
				)
				if not continues:
					return None, headerEnd
			headerEnd = j
			li = j

	def declaration_range(self, item):
		"""(start, end) of the whole lines of a declaration: decorators above
		it, its header and its body."""
		start = self.lineStarts[item.startLine]
		last = item.endLine
		end = self.lineStarts[last + 1] if last + 1 < self.lineCount else len(self.text)
		return start, end

	def declaration_chain(self, offset):
		"""Declarations whose lines contain offset, outermost first."""
		li = self.line_index(offset)
		return [item for item in self.outline() if item.startLine <= li <= item.endLine]


#: A header line ending like this continues on the next line.
_HEADER_CONTINUES = (",", "(", "<", ":", "=>", "->", "|", "&", "=")
#: A next line starting like this continues the header above it.
_HEADER_CONTINUATIONS = ("{", ":", ",", "->", "=>", "where", "throws")
#: A header line ending with one of these words continues on the next line.
_HEADER_END_WORDS = frozenset(("extends", "implements", "where", "requires", "noexcept", "throws"))
#: A next line starting with one of these words continues the header above.
#: Words that can start a member (override, final, async) are left out.
_HEADER_NEXT_WORDS = frozenset(("extends", "implements", "where", "throws", "requires", "rethrows", "noexcept"))
_LAST_WORD = re.compile(r"[A-Za-z_]\w*$")
_ARROW_AFTER = re.compile(r"\s*(?::(?:[^=;{}]|\{[^{}]*\})+)?=>")
_FIRST_IDENT = re.compile(r"[A-Za-z_]\w*")
#: A class-like keyword in declaration position: not "x: object)" or
#: "object = {" (a type or a variable), see _declares_class.
_CLASS_HEADER = re.compile(
	r"(?<![\w$.])(class|struct|interface|object|record|enum|trait|impl|extension|actor)\b(?!\s*[=,);?.])")
_DECORATOR_NAME = re.compile(r"@[\w.$]+\s*")
_LEADING_DECORATOR = re.compile(r"\s*@[\w.$]+\s*")
_CSS_AT_RULE = re.compile(
	r"^\s*@(?:media|supports|container|layer|page|font-face|keyframes|-webkit-keyframes|document|"
	r"include|mixin|function|if|else|each|for|while|use|forward|import|extend|at-root|content|return)\b")
_OBJC_DIRECTIVE = re.compile(r"^@(end|interface|implementation|protocol|property|synthesize|dynamic|class|optional|required|selector|autoreleasepool)\b")
_ATTRIBUTE = re.compile(r"^\[[^\[\]]*(\[[^\]]*\][^\[\]]*)*\]$", re.DOTALL)
#: Attribute groups at the start of a line: C# "[A, B(1)]", C++ "[[nodiscard]]".
_LEADING_ATTRIBUTES = re.compile(r"^\s*(?:\[\[?[^\[\]]*(?:\[[^\]]*\][^\[\]]*)*\]\]?\s*)+")
#: What follows "=" in a function expression: "", "async", "function ...".
_FUNCTION_VALUE = re.compile(r"^(?:async\s*)?(?:<[^>]*>\s*)?(?:function\b.*)?$")
_RUST_ATTRIBUTE = re.compile(r"^#\[.*\]$", re.DOTALL)
_TEMPLATE = re.compile(r"^template\s*<.*>$", re.DOTALL)


class Block(object):
	__slots__ = ("start", "end", "endLine", "indented")

	def __init__(self, start, end, endLine, indented=False):
		#: Where moving to the block start lands: the opening bracket, or the
		#: first character of an indented block's header line.
		self.start = start
		#: Where moving to the block end lands: the closing bracket (None when
		#: never closed), or the first character of the block's last line.
		self.end = end
		self.endLine = endLine
		self.indented = indented

	def ends_at(self, analysis, offset):
		"""True when offset is already at this block's end, so moving to the
		end should go to the next block out."""
		if self.indented:
			return analysis.line_index(offset) == self.endLine
		return self.end == offset


class OutlineItem(object):
	__slots__ = ("line", "kind", "name", "level", "parent", "parentItem", "children", "startLine", "endLine", "column", "hasBody")

	def __init__(self, line, kind, name, level):
		self.line = line
		self.kind = kind
		self.name = name
		self.level = level
		#: Name of the enclosing declaration, or None at the top level.
		self.parent = None
		self.parentItem = None
		self.children = []
		#: First and last line the declaration covers (decorators and body).
		self.startLine = line
		self.endLine = line
		#: Where on its line the declaration starts.
		self.column = 0
		#: False for a declaration without a body (a TypeScript overload
		#: signature, a C prototype); always True in indentation languages.
		self.hasBody = True

	def ancestors(self):
		"""Enclosing declarations, nearest first."""
		items = []
		p = self.parentItem
		while p is not None:
			items.append(p)
			p = p.parentItem
		return items

	def tree_label(self):
		"""Label for a tree view, where the parent is shown by nesting."""
		return _("{name}, {kind}, line {line}").format(
			name=self.name, kind=_(self.kind), line=self.line + 1)

	def label(self):
		# Name first so first-letter navigation in a list works.
		if self.parent:
			return _("{name}, {kind} in {parent}, line {line}").format(
				name=self.name, kind=_(self.kind), parent=self.parent, line=self.line + 1)
		return _("{name}, {kind}, line {line}").format(
			name=self.name, kind=_(self.kind), line=self.line + 1)


_TYPE_KEYWORDS = (
	r"class|struct|enum|interface|protocol|extension|trait|impl|object|record"
	r"|namespace|module|actor|union"
)
_CONTROL = {
	"if", "for", "while", "switch", "catch", "return", "else", "new", "do",
	"sizeof", "typeof", "throw", "await", "case", "foreach", "using", "lock",
	"elif", "with", "guard", "defer", "when", "match", "until", "unless",
	"yield", "delete",
}
_DECLARATION_KEYWORDS = frozenset(("function", "func", "fun", "fn", "def"))
#: Names a keyword pattern ("func name(", "class Name") never declares: the
#: keywords themselves, as in a Go parameter "fn func(int)" or "enum class".
#: Words like new, delete or match are fine there ("fn new" in Rust).
_KEYWORD_NOT_NAMES = frozenset(_DECLARATION_KEYWORDS | set(_TYPE_KEYWORDS.split("|")))
#: Names a pattern without a keyword ("type name(", "name(") never declares:
#: calls such as "return x(", "super(", "base(x)", "go func() {".
#: Go's type words after "func(...)": "func(w []string) map[string]int {".
_GO_NOT_NAMES = frozenset(_KEYWORD_NOT_NAMES | {"map", "chan", "struct", "interface"})
#: A call made by a statement word: Go "go walk(n.Left)", Swift "try fetch(n)".
_CALL_STATEMENT = re.compile(r"^\s*(?:go|try[?!]?)\s+[A-Za-z_$]")
_CALL_NOT_NAMES = frozenset(_CONTROL | _DECLARATION_KEYWORDS | {"base", "this", "super", "self"})
_FIRST_WORD = re.compile(r"^\s*(?:[)\]}]\s*)*([\w$]*)")
_NAME = r"(?P<name>[A-Za-z_$][\w$]*)"
_JS_MODIFIERS = r"(?:(?:async|static|get|set|public|private|protected|readonly|override|abstract)\s+)*"

#: language -> [(kind, pattern, names to ignore)].
_OUTLINE_PATTERNS = {
	"python": [
		("class", re.compile(r"^\s*class\s+" + _NAME), frozenset()),
		("function", re.compile(r"^\s*(?:async\s+)?def\s+" + _NAME), frozenset()),
	],
	"yaml": [],
	"default": [
		# Rust "impl<T: Display> fmt::Display for Wrapper<T>": named after the
		# type it is for.
		("type", re.compile(
			r"^\s*(?:unsafe\s+)?(?P<kind>impl)\b\s*(?:<[^{]*?>)?\s*(?:[\w:]+(?:<[^{]*?>)?\s+for\s+)?(?:\w+::)*" + _NAME),
			_KEYWORD_NOT_NAMES),
		# Go "type Server struct", "type Store interface", "type List[T any] struct".
		("type", re.compile(r"^\s*type\s+" + _NAME + r"(?:\[[^\]]*\])?\s+(?P<kind>struct|interface)\b"), _KEYWORD_NOT_NAMES),
		# "class Name", also "enum class Name"; not "class T" in "template <class T>".
		("type", re.compile(
			r"(?<![<,])(?<![<,]\s)\b(?P<kind>" + _TYPE_KEYWORDS.replace("|impl", "") + r")\s+(?:(?:class|struct)\s+)?" + _NAME),
			_KEYWORD_NOT_NAMES),
		# func / function / fun / fn; a receiver "(r *T)" only after Go's func;
		# Kotlin "fun <T> List<T>.second()", JS "function* gen()", Go "Map[T any](".
		("function", re.compile(r"\bfunc\b\s*(?:\([^)]*\)\s*)?" + _NAME + r"\s*[(<\[]"), _GO_NOT_NAMES),
		("function", re.compile(
			r"\b(?:function\s*\*?|fun|fn|def|sub|proc)\b\s*(?:<(?:[^<>]|<[^<>]*>)*>\s*)?"
			r"(?:[A-Za-z_$][\w$]*(?:<(?:[^<>]|<[^<>]*>)*>)?\??\.)*" + _NAME + r"\s*[(<]"),
			_KEYWORD_NOT_NAMES),
		# JS arrow function assigned to a name.
		("function", re.compile(
			r"\b(?:const|let|var)\s+" + _NAME
			+ r"\s*(?::[^=]+)?=\s*(?:async\s*)?(?:<[^>]*>\s*)?(?:\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>|function\b)"),
			_KEYWORD_NOT_NAMES),
		# The same with its parameters wrapping onto the next lines
		# ("const f = async ("); kept only when "=>" follows the ")".
		("arrowWrap", re.compile(
			r"\b(?:const|let|var)\s+" + _NAME + r"\s*(?::[^=]+)?=\s*(?:async\s*)?(?:<[^>]*>\s*)?\(\s*$"),
			_KEYWORD_NOT_NAMES),
		# C, C++, Java, C# "type name(args)" not ending in ";", also generic
		# "T Find<T>(int id)".
		("function", re.compile(
			r"^\s*(?:[\w$:<>,\[\]*&~?]+\s+)+[*&]*"
			r"(?P<name>[A-Za-z_~$][\w$]*(?:::[A-Za-z_~][\w]*)?)\s*(?:<[^;(){}]*>\s*)?\([^;]*$"),
			_CALL_NOT_NAMES),
		# The same with its body on the line: "int get() const { return x_; }".
		("function", re.compile(
			r"^\s*(?:[\w$:<>,\[\]*&~?]+\s+)+[*&]*"
			r"(?P<name>[A-Za-z_~$][\w$]*(?:::[A-Za-z_~][\w]*)?)\s*(?:<[^;(){}]*>\s*)?\([^;{}]*\)"
			r"\s*(?:(?:const|override|noexcept|final|volatile|throws\s+[\w.]+(?:\s*,\s*[\w.]+)*)\s*)*\{.*\}\s*;?\s*$"),
			_CALL_NOT_NAMES),
		# JS class method "name(args) {".
		("function", re.compile(
			r"^\s*" + _JS_MODIFIERS + _NAME + r"\s*\((?:(?!\bfunction\b)[^;])*\)\s*"
			r"(?::(?:\([^()]*\)\s*=>|(?!=>)[^{])+)?\{\s*$"),
			_CALL_NOT_NAMES),
		# A method whose parameters wrap: "name(" or "name(a," ends its line. Kept only
		# directly inside a class body (checked in _build_outline).
		("method", re.compile(r"^\s*" + _JS_MODIFIERS + _NAME + r"\s*\([^()]*$"), _CALL_NOT_NAMES),
		# A one-line method "get value() { return this._v; }", also only in a
		# class body: elsewhere "repeat(3) { go() }" is a call with a lambda.
		("method", re.compile(
			r"^\s*" + _JS_MODIFIERS + _NAME + r"\s*\([^;{}]*\)\s*(?::(?:\([^()]*\)\s*=>|(?!=>)[^{])+)?\{.*\}\s*;?\s*$"),
			_CALL_NOT_NAMES),
	],
}

_LEADING_WS = re.compile(r"^[ \t]*")


def indent_width(line):
	return len(_LEADING_WS.match(line).group(0).expandtabs(8))


def shorten(text, limit=70):
	text = re.sub(r"\s+", " ", text)
	return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."
