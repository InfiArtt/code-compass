# Instructions for AI coding agents

This file is read by AI coding agents (Claude Code, Codex, GitHub Copilot, Cursor, Gemini and others) working in this repository. People should start with the README and the [InfiArtt contributing guide](https://github.com/InfiArtt/.github/blob/main/CONTRIBUTING.md).

## About this project

Code Compass is an NVDA add-on (Python, wxPython, NVDA's add-on API) that makes coding in a plain editor work like a code editor such as VS Code, by ear: bracket-level tones, what closing brackets close, where-am-I, moves by level, function and block, an outline, problems (also while typing), editing commands, bookmarks, going back, running Python, reloading files changed on disk, and VS Code's sounds. Its main target is Windows 10's classic Notepad.

## Commands

- Tests: `python -m unittest discover -s tests` (Python 3.13, standard library only).
- Build: `python build.py`, which writes `codeCompass-<version>.nvda-addon`.
- Translations: after adding or changing a message, run `python tools/update_po.py`, add the Indonesian text for any message it reports as missing (in its `NEW` table), and run it again.

Run the tests before committing, and add a test when you fix a bug.

## Rules

- **Accessibility first.** InfiArtt is led by people with disabilities. Every control needs a label that screen readers announce, everything must work with the keyboard alone, and messages should say clearly what happened and what to do next.
- **Never commit secrets**: passwords, API keys, tokens, `.env` files. Push protection blocks known kinds of secrets, but don't rely on it.
- **Don't push to `main`.** Work on a branch and open a pull request.
- **Ask first** before anything that publishes or can't easily be undone: merging, releases, tags, deployments, package uploads, force-pushing, deleting branches or repositories.
- **Never post in other people's repositories** (issues, comments, pull requests, submissions) on the team's behalf. Some communities forbid AI tools from interacting with them; NV Access, for example, bans them from the NVDA Add-on Store repository. Prepare the facts and leave the posting to a person.
- **Be transparent about AI involvement.** Keep `Co-Authored-By` trailers in commits, and don't disguise AI-written text as written by a person.
- Keep changes focused, and match the existing code style, naming and comment density.
- Write code, comments and commit messages in English, with Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `refactor:`). Talk to the team in the language they use with you, often Indonesian.

## Project-specific notes

- `analyzer.py`, `snippets.py`, `editing.py`, `problems.py`, `filepath.py`, `edit_control.py`, `bookmarks.py` and `programs.py` must stay free of NVDA imports so they can be tested directly. NVDA-specific code goes in `__init__.py`.
- The tests run on Linux in CI, so Windows-only calls (ctypes.windll, winreg) must happen only when a function is called, and tests must replace them (see `tests/test_programs.py`).
- `addon/sounds/*.wav` are Visual Studio Code's accessibility signal sounds (MIT, see `addon/sounds/LICENSE-vscode.txt`), converted from MP3 and trimmed. NVDA plays them with `nvwave.playWaveFile`; keep them 16-bit PCM WAV.
- Commands that change text only run in a writable, multi-line Win32 edit control (classic Notepad), through `edit_control.replace`, which uses EM_SETSEL and EM_REPLACESEL (one undo step, offsets in UTF-16 units). Elsewhere their keys pass through unchanged. `tests/test_plugin_v040.py` replaces `edit_control.replace` with a fake that edits the test editor's text.
- wxPython in NVDA lacks some methods (for example `StdDialogButtonSizer.GetAffirmativeButton`); check new wx calls against NVDA's own wx before relying on them. Dialogs go through `_run_dialog`, which brings them in front of the editor.
- The smoke tests in `tests/test_plugin_smoke.py` replace NVDA and wx with stub modules. A new NVDA module or wx class used by the plugin needs a stub there.
- User-facing strings go through `_()`. The plugin's `_` follows the "Language of Code Compass messages" setting, not only NVDA's language, and `analyzer._` is set to it. `tests/test_translations.py` fails when a message has no Indonesian translation or a translation drops a `{placeholder}`.
- Generated files are not committed: `addon/manifest.ini`, `addon/doc/*/*.html` and `*.mo` all come from `build.py`.
- Releases: CI (`.github/workflows/build_addon.yml`) publishes a GitHub Release when `main` gets an `addon_version` in `buildVars.py` that has no tag yet. That version needs a `## Version X.Y.Z` section in `CHANGELOG.md`, which becomes the release notes.
- Offsets: the analyzer works on Python string offsets. NVDA text infos may count UTF-16 units (Notepad) or UTF-8 bytes (Scintilla); convert with the helpers in `__init__.py` (`_caret_offset`, `_range_info`, `_selection_offsets`).
