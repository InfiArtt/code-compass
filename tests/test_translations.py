# -*- coding: UTF-8 -*-
# Every translatable message must have an Indonesian translation, and the
# compiled catalog must load with gettext.

import ast
import gettext
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import build  # noqa: E402

SOURCES = [
	os.path.join(ROOT, "addon", "globalPlugins", "codeCompass", "__init__.py"),
	os.path.join(ROOT, "addon", "globalPlugins", "codeCompass", "analyzer.py"),
	os.path.join(ROOT, "addon", "globalPlugins", "codeCompass", "problems.py"),
]
PO = os.path.join(ROOT, "addon", "locale", "id", "LC_MESSAGES", "nvda.po")
#: Messages translated through a variable rather than a literal.
DYNAMIC = ["brace", "paren", "bracket", "function", "class"]


def source_msgids():
	ids = []
	for path in SOURCES:
		with open(path, encoding="utf-8") as f:
			tree = ast.parse(f.read())
		for node in ast.walk(tree):
			if (
				isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
				and node.func.id == "_" and node.args
				and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
			):
				ids.append(node.args[0].value)
	return ids + DYNAMIC


class TranslationTests(unittest.TestCase):
	def test_every_message_translated(self):
		catalog = build.read_po(PO)
		missing = [m for m in source_msgids() if m not in catalog]
		self.assertEqual(missing, [])

	def test_placeholders_kept(self):
		import re
		for msgid, msgstr in build.read_po(PO).items():
			if not msgid:
				continue
			self.assertEqual(
				sorted(re.findall(r"\{\w+\}", msgid)), sorted(re.findall(r"\{\w+\}", msgstr)), msgid)

	def test_compiled_catalog_loads(self):
		build.build_translations()
		t = gettext.translation("nvda", localedir=os.path.join(ROOT, "addon", "locale"), languages=["id"])
		self.assertEqual(t.gettext("End of block"), "Akhir blok")
		self.assertEqual(t.gettext("closes {what}"), "tutup {what}")


if __name__ == "__main__":
	unittest.main()
