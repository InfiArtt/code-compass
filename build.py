#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Standalone builder for the Code Compass add-on.

Produces a ready-to-install .nvda-addon without needing SCons or the gettext
SCons tool. Run from the project root:

    python build.py

Output: codeCompass-<version>.nvda-addon in this directory.
"""

import ast
from html import escape as html_escape
import io
import os
import re
import struct
import zipfile

import buildVars

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.join(HERE, "addon")

OPTIONAL = {
	"addon_url": "url",
	"addon_sourceURL": "sourceURL",
	"addon_license": "license",
	"addon_licenseURL": "licenseURL",
	"addon_updateChannel": "updateChannel",
}


def generate_manifest():
	info = dict(buildVars.addon_info)
	for key in OPTIONAL:
		commentKey = key + "Comment"
		if info.get(key):
			info[commentKey] = ""
		else:
			info[commentKey] = "# "
			info[key] = "None"
	with io.open(os.path.join(HERE, "manifest.ini.tpl"), "r", encoding="utf-8") as f:
		tpl = f.read()
	manifest = tpl.format(**info)
	out = os.path.join(ADDON_DIR, "manifest.ini")
	with io.open(out, "w", encoding="utf-8") as f:
		f.write(manifest)
	return out


_CODE_SPAN = re.compile(r"(``.+?``|`[^`]+`)")
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>])")


def inline_markdown(text):
	"""Escape HTML, then turn `code` and **bold** spans into tags, so the help
	page does not make NVDA read backticks and asterisks aloud. Code spans
	are taken first, so nothing inside them changes."""
	# Backslash-escaped characters become placeholders first, so an escaped
	# backtick or asterisk cannot start a span; they come back as plain text.
	escaped = []

	def hold(m):
		escaped.append(m.group(1))
		return chr(0xE000 + len(escaped) - 1)

	text = _ESCAPED.sub(hold, text)
	parts = []
	for i, piece in enumerate(_CODE_SPAN.split(text)):
		if i % 2:
			inner = piece[2:-2].strip() if piece.startswith("``") else piece[1:-1]
			parts.append("<code>%s</code>" % html_escape(inner, quote=False))
			continue
		piece = html_escape(piece, quote=False)
		parts.append(re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", piece))
	result = "".join(parts)
	for n, ch in enumerate(escaped):
		result = result.replace(chr(0xE000 + n), html_escape(ch, quote=False))
	return result


def tiny_markdown(text):
	"""Very small Markdown -> HTML fallback when the markdown module is absent.

	Handles headings, blank-line paragraphs, bullet lists, code and bold spans
	well enough for the add-on help page.
	"""
	lines = text.replace("[[!meta title=\"", "").replace("\"]]", "").splitlines()
	html = []
	in_list = False
	para = []

	def flush_para():
		if para:
			html.append("<p>" + inline_markdown(" ".join(para).strip()) + "</p>")
			del para[:]

	def close_list():
		nonlocal in_list
		if in_list:
			html.append("</ul>")
			in_list = False

	for line in lines:
		s = line.strip()
		if not s:
			flush_para()
			close_list()
			continue
		m = re.match(r"^(#{1,6})\s+(.*)$", s)
		if m:
			flush_para()
			close_list()
			level = len(m.group(1))
			html.append("<h%d>%s</h%d>" % (level, inline_markdown(m.group(2)), level))
			continue
		if s.startswith("* ") or s.startswith("- "):
			flush_para()
			if not in_list:
				html.append("<ul>")
				in_list = True
			html.append("<li>%s</li>" % inline_markdown(s[2:].strip()))
			continue
		para.append(s)
	flush_para()
	close_list()
	return "\n".join(html)


def build_docs():
	docRoot = os.path.join(ADDON_DIR, "doc")
	if not os.path.isdir(docRoot):
		return
	try:
		import markdown as _md

		def convert(t):
			return _md.markdown(t, extensions=buildVars.markdownExtensions)
	except ImportError:
		convert = tiny_markdown
	for lang in os.listdir(docRoot):
		langDir = os.path.join(docRoot, lang)
		if not os.path.isdir(langDir):
			continue
		for name in os.listdir(langDir):
			if not name.endswith(".md"):
				continue
			src = os.path.join(langDir, name)
			with io.open(src, "r", encoding="utf-8") as f:
				md = f.read()
			title = "%s %s" % (
				buildVars.addon_info["addon_summary"],
				buildVars.addon_info["addon_version"],
			)
			body = convert(md)
			htmlPath = os.path.join(langDir, name[:-3] + ".html")
			with io.open(htmlPath, "w", encoding="utf-8") as f:
				f.write(
					"<!DOCTYPE html>\n<html lang=\"%s\">\n<head>\n"
					"<meta charset=\"UTF-8\">\n<title>%s</title>\n</head>\n"
					"<body>\n%s\n</body>\n</html>\n" % (lang.replace("_", "-"), title, body)
				)


def read_po(path):
	"""Parse a .po file into {msgid: msgstr}, skipping fuzzy and empty
	entries. Handles multi-line strings; plural forms are not used."""
	messages = {}
	msgid = msgstr = None
	section = None
	fuzzy = False

	def flush():
		if msgid is not None and msgstr and not fuzzy:
			messages[msgid] = msgstr

	with io.open(path, "r", encoding="utf-8") as f:
		for raw in f:
			line = raw.strip()
			if line.startswith("#,") and "fuzzy" in line:
				fuzzy = True
			elif line.startswith("msgid "):
				flush()
				msgid, msgstr, section, fuzzy = ast.literal_eval(line[6:]), None, "id", False
			elif line.startswith("msgstr "):
				msgstr, section = ast.literal_eval(line[7:]), "str"
			elif line.startswith('"'):
				if section == "id":
					msgid += ast.literal_eval(line)
				elif section == "str":
					msgstr += ast.literal_eval(line)
		flush()
	return messages


def write_mo(messages, path):
	"""Write a GNU .mo catalog (same layout as CPython's msgfmt.py)."""
	keys = sorted(messages)
	ids = b""
	strs = b""
	offsets = []
	for k in keys:
		kb = k.encode("utf-8")
		vb = messages[k].encode("utf-8")
		offsets.append((len(ids), len(kb), len(strs), len(vb)))
		ids += kb + b"\0"
		strs += vb + b"\0"
	n = len(keys)
	keyStart = 7 * 4 + 16 * n
	valueStart = keyStart + len(ids)
	table = []
	for o1, l1, _o2, _l2 in offsets:
		table += [l1, o1 + keyStart]
	for _o1, _l1, o2, l2 in offsets:
		table += [l2, o2 + valueStart]
	header = struct.pack("<7I", 0x950412DE, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
	with open(path, "wb") as f:
		f.write(header + struct.pack("<%dI" % len(table), *table) + ids + strs)


def build_translations():
	localeRoot = os.path.join(ADDON_DIR, "locale")
	if not os.path.isdir(localeRoot):
		return
	for lang in os.listdir(localeRoot):
		po = os.path.join(localeRoot, lang, "LC_MESSAGES", "nvda.po")
		if os.path.isfile(po):
			write_mo(read_po(po), po[:-3] + ".mo")


def bundle():
	version = buildVars.addon_info["addon_version"]
	name = buildVars.addon_info["addon_name"]
	dest = os.path.join(HERE, "%s-%s.nvda-addon" % (name, version))
	with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
		for root, _dirs, files in os.walk(ADDON_DIR):
			for fn in files:
				abs_path = os.path.join(root, fn)
				rel = os.path.relpath(abs_path, ADDON_DIR)
				if rel in buildVars.excludedFiles:
					continue
				if fn.endswith((".pyc", ".po")) or "__pycache__" in rel:
					continue
				z.write(abs_path, rel)
	return dest


def main():
	generate_manifest()
	build_translations()
	build_docs()
	dest = bundle()
	print("Built: %s" % dest)


if __name__ == "__main__":
	main()
