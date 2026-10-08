# Code Compass
[![Build & Release Addon](https://github.com/InfiArtt/code-compass/actions/workflows/build_addon.yml/badge.svg)](https://github.com/InfiArtt/code-compass/actions/workflows/build_addon.yml)
[![Latest Release](https://img.shields.io/github/v/release/InfiArtt/code-compass)](https://github.com/InfiArtt/code-compass/releases/latest)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/gpl-2.0.html)

**Code in Notepad like in a code editor, by ear, with NVDA.**

Reading code line by line tells you what each line says, but not where you are. Code Compass, an add-on for the NVDA screen reader, adds the structure and the tools of a code editor such as VS Code: how deep you are in brackets, what a closing bracket closes, which function you are in, where the problems are, and the editing keys you would expect. It works best in Windows 10's Notepad.

## Features

Hearing the structure:

- **A tone for every line's bracket level** as you move up and down: higher for deeper levels, silent at the top level, shorter inside parentheses. It can be spoken instead ("level 2"), or both.
- **Closing brackets say what they close**, when you reach them and when you type them, for example "closes func viewDidLoad()".
- **The current function is announced** when the caret moves into another one, like VS Code's breadcrumbs. **Where am I** lists every block around the caret.
- **Visual Studio Code's own sounds** for lines with an error, a warning or a bookmark, saving, and program runs (or simple beeps, if you prefer).

Moving around:

- Next or previous line at the same level, function, parent and child function, block start and end, all on alt and arrow keys.
- **F12** to a declaration, **shift+F12** for every use of a name, an **outline** tree (control+shift+O), and an **Explorer** of the project's files (control+shift+E).
- A **command palette** (control+shift+P) with every command and its keys.
- **Bookmarks** (control+alt+K, then control+alt+L and J to jump between them), kept per file and following their line through edits.
- **Reload** a file another program changed, automatically when you have no unsaved changes, like VS Code.
- **Go back** to where you were before a jump with control+alt+backspace, and forward again with control+alt+shift+backspace, like VS Code. Notepad's own **control+G** says where you landed.

Problems and running:

- Syntax errors in Python and JSON, and unbalanced brackets in every language, found without running anything, also while you type. **F8** goes to the next one, Visual Studio Code's error sound marks problem lines, and saving reports them.
- Python lines mixing tabs and spaces, and functions declared twice, are problems too.
- **control+F5** runs a Python file in a console window and says how long it ran; F8 then goes to the line it stopped on. Python is found even when NVDA started before it was installed.

Editing in Windows 10 Notepad:

- **Automatic indentation** on Enter and closing brackets, **Tab and shift+Tab** on several lines, **control+/** to comment.
- **control+space** completion from the file's names, **control+shift+space** for a function's parameters.
- **Delete, move and duplicate lines**, and **F2** to rename a name across the file.
- **Snippets**: save code you reuse and insert it later, indented to fit.

Comments and strings are ignored when counting brackets; Python and YAML blocks also follow indentation. Messages are in English or Indonesian, chosen separately from NVDA's language. NVDA+shift+K then H lists the commands that work in any editor.

## Requirements

- Windows with NVDA 2024.1 or later.
- Notepad (Windows 10's classic Notepad is the main target) or Notepad++ for the level tones and quick keys. The NVDA+shift+K commands work in any text editor.
- Python, from python.org or the Python install manager, to run programs with control+F5.

Windows 11's Notepad is a different program: hearing the structure, moving around, problems and running work there, but the commands that change text do not. It has not been tested much yet; reports are welcome.

## Installation

Download the `.nvda-addon` file from [GitHub Releases](https://github.com/InfiArtt/code-compass/releases/latest), open it, confirm the installation and restart NVDA.

## Getting started

1. Open a code file in Notepad, for example [samples/latihan.py](samples/latihan.py) from this repository. Its first lines say what to try where.
2. Move up and down with the arrow keys and listen to the tones rise and fall.
3. Press NVDA+shift+K, then W, to hear where you are. NVDA+shift+K, then H, lists every command, and control+shift+P lists them with their keys.
4. Press control+F5 to run it.

The full guide is in [addon/doc/en/readme.md](addon/doc/en/readme.md) (Indonesian: [addon/doc/id/readme.md](addon/doc/id/readme.md)), and NVDA opens it from the Add-on Store too (Installed add-ons, Actions, Help).

## Building from source

You need Python 3.13. From the repository folder:

```bash
python -m unittest discover -s tests
```

```bash
python build.py
```

The build writes `codeCompass-<version>.nvda-addon`. It needs no SCons or gettext: `build.py` writes the manifest, compiles the translations and the documentation, and packages the add-on.

## Project layout

- `addon/globalPlugins/codeCompass/analyzer.py`: the code analysis (brackets, scopes, outline). Plain Python with no NVDA imports, so it is tested directly.
- `addon/globalPlugins/codeCompass/snippets.py`: snippet files and indentation.
- `addon/globalPlugins/codeCompass/editing.py`: what the editing commands change (indentation, comments, completion, lines, rename), as plain Python.
- `addon/globalPlugins/codeCompass/problems.py`: syntax and bracket problems, without running code.
- `addon/globalPlugins/codeCompass/edit_control.py`: changing text in Notepad's edit control directly, as one undoable step.
- `addon/globalPlugins/codeCompass/filepath.py`: finding the file an editor has open, reading files the way Notepad does, the project folder, and the Recycle Bin.
- `addon/globalPlugins/codeCompass/bookmarks.py`: bookmarks, and following lines through edits (also used for going back and reloading).
- `addon/globalPlugins/codeCompass/programs.py`: finding Python, and the user's current environment for programs started from NVDA.
- `addon/runner/run_python.py`: runs a program in a console window and reports the line of an uncaught error.
- `addon/globalPlugins/codeCompass/__init__.py`: the NVDA part: line reports, sounds, quick keys, command layer, dialogs and settings.
- `addon/sounds/`: Visual Studio Code's accessibility signal sounds, as WAV files.
- `addon/locale/id/LC_MESSAGES/nvda.po`: the Indonesian translation. `tools/update_po.py` rewrites it to match the messages in the code, and a test fails when a message has no translation.
- `tests/`: analyzer tests, translation checks and tests of the plugin against stubbed NVDA and wx modules.
- `samples/`: files to try the add-on with: `latihan.py` walks through the features, `rusak.js` is broken on purpose.

## Contributing

See the [InfiArtt contributing guide](https://github.com/InfiArtt/.github/blob/main/CONTRIBUTING.md). Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

GNU General Public License, version 2. See [LICENSE](LICENSE).

The sounds in `addon/sounds` are Visual Studio Code's accessibility signal sounds, copyright Microsoft Corporation, used under the MIT License (see [addon/sounds/LICENSE-vscode.txt](addon/sounds/LICENSE-vscode.txt)).
