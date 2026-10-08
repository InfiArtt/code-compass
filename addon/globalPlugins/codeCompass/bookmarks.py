# -*- coding: UTF-8 -*-
# Code Compass - bookmarks: lines to jump back to, kept per file across
# NVDA restarts. While a document is edited, each bookmark follows its line
# by comparing the text before and after the change; a bookmark also keeps
# its line's text, to find the line again after the file was closed.
# No NVDA imports.

import difflib
import json
import os

#: Files with bookmarks kept on disk; the ones used longest ago go first.
MAX_FILES = 200
#: Changed regions larger than this (lines) skip the line-by-line diff:
#: moved lines are still found by their text, the rest keep their place.
_DIFF_LIMIT = 300


class Bookmark(object):
	__slots__ = ("line", "text", "detached")

	def __init__(self, line, text):
		#: 0-based line index, as of the last time the text was seen.
		self.line = line
		#: The line's text without surrounding blanks.
		self.text = text
		#: True while its line is gone (deleted, or the whole text replaced):
		#: hidden, not saved, and back if the line returns (control+Z).
		self.detached = False


def visible(marks):
	"""The bookmarks whose line exists, in line order."""
	return [m for m in marks if not m.detached]


def line_map(oldLines, newLines):
	"""A function from a line index in oldLines to its index in newLines, or
	None for a line that was deleted. Lines before and after the changed part
	shift by the number of lines added or removed; inside it, unchanged lines
	are matched and edited lines keep their place."""
	nOld, nNew = len(oldLines), len(newLines)
	prefix = 0
	while prefix < nOld and prefix < nNew and oldLines[prefix] == newLines[prefix]:
		prefix += 1
	suffix = 0
	while (
		suffix < nOld - prefix and suffix < nNew - prefix
		and oldLines[nOld - 1 - suffix] == newLines[nNew - 1 - suffix]
	):
		suffix += 1
	oldMid = oldLines[prefix:nOld - suffix]
	newMid = newLines[prefix:nNew - suffix]
	# Unchanged lines first (a diff for small changes), then moved lines by
	# their text (control+shift+arrows, cut and paste), then edited lines by
	# their place in the changed block.
	table = {}
	replaced = []
	if len(oldMid) <= _DIFF_LIMIT and len(newMid) <= _DIFF_LIMIT:
		opcodes = difflib.SequenceMatcher(None, oldMid, newMid, autojunk=False).get_opcodes()
	else:
		opcodes = [("replace", 0, len(oldMid), 0, len(newMid))]
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			for i in range(i1, i2):
				table[i] = j1 + (i - i1)
		elif tag == "replace":
			replaced.append((i1, i2, j1, j2))
	usedNew = set(table.values())
	# Lines with the same text pair up in order: the first unmatched old one
	# with the first unmatched new one, and so on (a moved block keeps its
	# order). Linear, even with thousands of identical lines.
	freeOld = {}
	for i, text in enumerate(oldMid):
		if i not in table and text.strip():
			freeOld.setdefault(text, []).append(i)
	freeNew = {}
	for j, text in enumerate(newMid):
		if j not in usedNew and text.strip():
			freeNew.setdefault(text, []).append(j)
	for text, olds in freeOld.items():
		for i, j in zip(olds, freeNew.get(text, ())):
			table[i] = j
			usedNew.add(j)
	for i1, i2, j1, j2 in replaced:
		for i in range(i1, i2):
			j = j1 + (i - i1)
			if i not in table and j < j2 and j not in usedNew:
				table[i] = j
				usedNew.add(j)
	table = {prefix + i: prefix + j for i, j in table.items()}

	def mapping(index):
		if index < prefix:
			return index
		if index >= nOld - suffix:
			return index + nNew - nOld
		return table.get(index)
	return mapping


def reanchor(marks, lines, oldLines=None):
	"""Move the bookmarks to their lines in lines (the document now).

	With oldLines (the text they were last matched against), each follows
	its line through the change (see line_map). Without it (just loaded
	from disk), a bookmark stays where its line still has its text, else
	goes to the nearest free line with that text, else keeps its number.
	A bookmark whose line is gone, or whose place another one already
	holds, is detached rather than dropped; a detached one comes back when
	its line does. Each bookmark then remembers its line's current text.
	Returns True when anything changed."""
	count = len(lines)
	changed = False
	taken = set()
	mapping = line_map(oldLines, lines) if oldLines is not None else None
	inserted = None
	if mapping is not None:
		# New lines no old line became: where a detached bookmark's line may
		# have come back (pasted, or restored by control+Z).
		targets = {mapping(i) for i in range(len(oldLines))}
		inserted = [j for j in range(count) if j not in targets]
	wasDetached = [m for m in marks if m.detached]
	ordered = sorted(visible(marks), key=lambda m: m.line)
	if mapping is None:
		# First the bookmarks whose line still reads the same, so another one
		# looking for its text cannot take their line.
		for mark in ordered:
			if mark.line < count and lines[mark.line].strip() == mark.text:
				taken.add(mark.line)
	for mark in ordered:
		if mapping is not None:
			line = mapping(mark.line)
			if line is not None and not 0 <= line < count:
				line = None
		elif mark.line < count and lines[mark.line].strip() == mark.text:
			taken.discard(mark.line)
			line = mark.line
		else:
			line = _nearest(lines, mark.text, mark.line, taken) if mark.text else None
			if line is None and count:
				line = min(mark.line, count - 1)
		if line is None or line in taken:
			mark.detached = True
			changed = True
			continue
		taken.add(line)
		text = lines[line].strip()
		if line != mark.line or text != mark.text:
			mark.line, mark.text = line, text
			changed = True
	# Bookmarks detached earlier come back when their line does: on a newly
	# inserted line with their text (nearest first), or, without the old
	# text, on their own line number. One detached just now stays so.
	for mark in sorted(wasDetached, key=lambda m: m.line):
		if inserted is not None:
			free = [j for j in inserted if j not in taken and lines[j].strip() == mark.text]
			line = min(free, key=lambda j: abs(j - mark.line)) if free else None
		elif mark.line < count and mark.line not in taken and lines[mark.line].strip() == mark.text:
			line = mark.line
		else:
			line = None
		if line is not None:
			mark.detached = False
			mark.line = line
			taken.add(line)
			changed = True
	marks.sort(key=lambda m: m.line)
	return changed


def _nearest(lines, text, line, taken=()):
	"""Index of the free line closest to line whose stripped text is text."""
	count = len(lines)
	for distance in range(0, count):
		for candidate in ((line,) if distance == 0 else (line + distance, line - distance)):
			if 0 <= candidate < count and candidate not in taken and lines[candidate].strip() == text:
				return candidate
		if line - distance < 0 and line + distance >= count:
			break
	return None


def toggle(marks, line, text):
	"""Add a bookmark on line (whose text is text), or remove the one there.
	True when added."""
	here = [m for m in marks if m.line == line]
	for mark in here:
		marks.remove(mark)
	if any(not m.detached for m in here):
		return False
	marks.append(Bookmark(line, text.strip()))
	marks.sort(key=lambda m: m.line)
	return True


def neighbour(marks, line, step):
	"""(bookmark, wrapped): the next visible bookmark after line (step 1) or
	before it (step -1), going round past the end. (None, False) without any."""
	marks = visible(marks)
	if not marks:
		return None, False
	if step > 0:
		for mark in marks:
			if mark.line > line:
				return mark, False
		return marks[0], True
	for mark in reversed(marks):
		if mark.line < line:
			return mark, False
	return marks[-1], True


class Store(object):
	"""Bookmarks per file path, saved as JSON. Documents that have no file
	(never saved) get theirs in memory only, under any other key."""

	def __init__(self, path):
		self.path = path
		#: key -> list of Bookmark.
		self.files = {}
		self.dirty = False
		self._load()

	def _load(self):
		try:
			with open(self.path, encoding="utf-8") as f:
				data = json.load(f)
		except (OSError, ValueError):
			return
		if not isinstance(data, dict):
			return
		for key, entries in data.items():
			marks = []
			for entry in entries if isinstance(entries, list) else ():
				try:
					line, text = int(entry[0]), str(entry[1])
				except (TypeError, ValueError, IndexError, KeyError):
					continue
				if line >= 0:
					marks.append(Bookmark(line, text))
			if marks:
				marks.sort(key=lambda m: m.line)
				self.files[key] = marks

	def get(self, key):
		"""The bookmark list for key (created empty when missing)."""
		marks = self.files.get(key)
		if marks is None:
			marks = self.files[key] = []
		return marks

	def has(self, key):
		"""True when key has bookmarks, detached ones included (they may
		come back)."""
		return bool(self.files.get(key))

	def touch(self, key):
		"""Mark key as just used (kept longest) and the store as changed."""
		marks = self.files.pop(key, None)
		if marks is not None:
			self.files[key] = marks
		self.dirty = True

	def move(self, old, new):
		"""Give old's bookmarks to new: a document saved under a name (also
		over an existing file, whose old bookmarks no longer fit)."""
		marks = self.files.pop(old, None)
		if marks:
			self.files[new] = marks
			self.dirty = True

	def drop(self, key):
		if self.files.pop(key, None):
			self.dirty = True

	def save(self):
		"""Write the visible bookmarks of files (string keys) to disk if
		anything changed. Returns False when writing failed."""
		if not self.dirty:
			return True
		data = {}
		for key, marks in self.files.items():
			shown = visible(marks)
			if isinstance(key, str) and shown:
				data[key] = [[m.line, m.text] for m in shown]
		keys = list(data)
		for key in keys[:max(0, len(keys) - MAX_FILES)]:
			del data[key]
		temp = self.path + ".tmp"
		try:
			folder = os.path.dirname(self.path)
			if folder and not os.path.isdir(folder):
				os.makedirs(folder)
			# ASCII escapes keep any text writable, even half an emoji.
			with open(temp, "w", encoding="utf-8") as f:
				json.dump(data, f)
			os.replace(temp, self.path)
		except (OSError, ValueError):
			try:
				os.remove(temp)
			except OSError:
				pass
			return False
		self.dirty = False
		return True
