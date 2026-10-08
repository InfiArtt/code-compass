# -*- coding: UTF-8 -*-
# Code Compass - undo and redo many steps. Windows 10's Notepad keeps only
# one step (its second control+Z redoes the first). Code Compass records the
# document's text at undo stops (a pause in typing, a caret move to another
# line, its own commands) and keeps only what changed between two stops.
# No NVDA imports.

#: Steps kept per document; the oldest go first.
MAX_STEPS = 300
#: Characters kept in all steps of a document together.
MAX_CHARS = 20 * 1000 * 1000


class Step(object):
	"""One change: text[start:start + len(old)] became new."""
	__slots__ = ("start", "old", "new")

	def __init__(self, start, old, new):
		self.start = start
		self.old = old
		self.new = new


def diff(before, after):
	"""The Step that turns before into after (the part between their common
	start and end), or None when they are equal."""
	if before == after:
		return None
	n = min(len(before), len(after))
	prefix = _common_prefix(before, after, n)
	suffix = _common_suffix(before, after, n - prefix)
	# Keep a "\r\n" whole: a step never starts or ends between its halves.
	while prefix and before[prefix - 1] == "\r" and before[prefix:prefix + 1] == "\n":
		prefix -= 1
	return Step(prefix, before[prefix:len(before) - suffix], after[prefix:len(after) - suffix])


_BLOCK = 4096


def _common_prefix(a, b, n):
	"""Length of the common start of a and b (at most n), comparing whole
	blocks first so a large file costs little."""
	i = 0
	while i + _BLOCK <= n and a[i:i + _BLOCK] == b[i:i + _BLOCK]:
		i += _BLOCK
	while i < n and a[i] == b[i]:
		i += 1
	return i


def _common_suffix(a, b, n):
	"""Length of the common end of a and b (at most n)."""
	la, lb = len(a), len(b)
	i = 0
	while i + _BLOCK <= n and a[la - i - _BLOCK:la - i] == b[lb - i - _BLOCK:lb - i]:
		i += _BLOCK
	while i < n and a[la - 1 - i] == b[lb - 1 - i]:
		i += 1
	return i


class History(object):
	"""The undo steps of one document. base is the text as of the last
	stop; steps[:index] can be undone, steps[index:] redone."""

	def __init__(self, text):
		self.base = text
		self.steps = []
		self.index = 0

	def reset(self, text):
		self.base = text
		self.steps = []
		self.index = 0

	def record(self, text):
		"""An undo stop: text is the document now. True when it changed."""
		step = diff(self.base, text)
		if step is None:
			return False
		del self.steps[self.index:]
		self.steps.append(step)
		self.index = len(self.steps)
		self.base = text
		self._trim()
		return True

	def _trim(self):
		size = sum(len(s.old) + len(s.new) for s in self.steps)
		while self.steps and (len(self.steps) > MAX_STEPS or size > MAX_CHARS):
			first = self.steps.pop(0)
			size -= len(first.old) + len(first.new)
			self.index -= 1

	def can_undo(self):
		return self.index > 0

	def can_redo(self):
		return self.index < len(self.steps)

	def undo(self, text):
		"""Undo one step from text (the document now; typing since the last
		stop becomes a step of its own first). Returns (start, end,
		replacement): replace text[start:end] with replacement. None when
		there is nothing to undo."""
		self.record(text)
		if not self.index:
			return None
		step = self.steps[self.index - 1]
		end = step.start + len(step.new)
		if self.base[step.start:end] != step.new:
			# The text no longer matches the history: start over.
			self.reset(self.base)
			return None
		self.index -= 1
		self.base = self.base[:step.start] + step.old + self.base[end:]
		return step.start, end, step.old

	def redo(self, text):
		"""Redo one step, like undo. None when there is nothing to redo, or
		when the text changed since the last undo (which ends redoing)."""
		if text != self.base:
			self.record(text)
			return None
		if self.index >= len(self.steps):
			return None
		step = self.steps[self.index]
		end = step.start + len(step.old)
		if self.base[step.start:end] != step.old:
			self.reset(self.base)
			return None
		self.index += 1
		self.base = self.base[:step.start] + step.new + self.base[end:]
		return step.start, end, step.new
