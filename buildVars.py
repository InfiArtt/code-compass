# -*- coding: UTF-8 -*-
# Build customizations for Code Compass.
# Follows the structure of the NVDA community add-on template.

_ = lambda x: x

addon_info = {
	# add-on Name/identifier, internal for NVDA
	"addon_name": "codeCompass",
	# Add-on summary, usually the user visible name of the addon.
	"addon_summary": _("Code Compass"),
	# Add-on description
	"addon_description": _(
		"Makes coding in Notepad feel like a code editor, by ear: a tone for "
		"each line's bracket level, what closing brackets close, the current "
		"function, problems and F8, running Python, an explorer of the "
		"project's files, a command palette, and VS Code's editing keys "
		"(automatic indentation, comments, completion, line moves, rename)."
	),
	# version
	"addon_version": "0.4.2",
	# Author(s)
	"addon_author": "Rafli I. <rafli08523717409@gmail.com>",
	# URL for the add-on documentation support
	"addon_url": "https://github.com/InfiArtt/code-compass",
	# URL for the add-on repository where the source code can be found
	"addon_sourceURL": "https://github.com/InfiArtt/code-compass",
	# Documentation file name
	"addon_docFileName": "readme.html",
	# Minimum NVDA version supported (e.g. "2018.3.0", minor version is optional)
	"addon_minimumNVDAVersion": "2024.1",
	# Last NVDA version supported/tested (e.g. "2018.4.0", ideally more recent than minimum version)
	"addon_lastTestedNVDAVersion": "2026.2",
	# Add-on update channel (default is None, denoting stable releases,
	# and for development releases, use "dev".)
	"addon_updateChannel": None,
	# Add-on license such as GPL 2
	"addon_license": "GPL v2",
	# URL for the license document the ADDON is licensed under
	"addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
}

pythonSources = ["addon/globalPlugins/codeCompass/*.py"]

i18nSources = pythonSources + ["buildVars.py"]

# Paths relative to the addon directory that are left out of the package.
excludedFiles = []

baseLanguage = "en"

markdownExtensions = []

brailleTables = {}
