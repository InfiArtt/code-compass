# Code Compass

Code Compass makes coding in Notepad feel closer to a code editor, by ear. It tells you how deep you are in brackets, what a closing bracket closes and which function you are in; it finds problems, runs Python, browses the project's files, and adds the editing keys you know from VS Code.

It works best in Windows 10's Notepad. Notepad++ is also enabled by default. Commands that change text (automatic indentation, comments, line moves, completion, rename) work in Windows 10's Notepad only; Notepad++ has its own versions of them, so those keys keep doing what Notepad++ does. So do F8, shift+F8, F12, control+shift+P and control+shift+space, which Notepad++ uses for its own commands: there, reach Code Compass's versions with NVDA+shift+K (shift+P opens the command palette).

## While moving by line

### Bracket level

When you move up or down by line, a short tone plays. Each level is higher in pitch, so a deeper line sounds higher. Lines at the top level (outside every bracket) are silent. Lines inside parentheses or square brackets, such as the continuation of a long call, get a shorter tone than lines inside braces.

The level is the number of brackets still open at the start of the line. A line that starts with a closing bracket counts at the outer level, the same way indentation would show it. Brackets in strings and comments are ignored.

In the settings you can choose a tone, speech ("level 2"), both, or off. You can also report the level only when it changes; in that mode, returning to the top level is announced too, with a low tone or "level 0".

If NVDA's own line indentation report is set to tones, the two tones can cut each other off. Set NVDA's indentation report to speech (Document Formatting settings), or set Code Compass to speech.

### Closing brackets

On a line that starts with a closing bracket, Code Compass says what it closes after the line is read, for example "closes func viewDidLoad()". The same happens when you type a closing bracket; if it is the wrong kind, you hear which bracket is still open and on which line.

### Current function

When the caret moves into another function or class, Code Compass says so once, for example "in function load", like the breadcrumbs in VS Code. Leaving every function says "top level".

### Problems

A line with a problem plays a low buzz after its level tone. See Problems below.

## Editing in Windows 10 Notepad

- **Automatic indentation**: Enter keeps the line's indentation, adds a level after an opening bracket (or `:` in Python), and goes back a level after `return`, `pass`, `break`, `continue` or `raise` in Python. Enter between a pair such as `{}` puts the closing bracket on its own line and the caret on the line between. A closing bracket typed first on a line moves back to line up with its opening bracket.
- **Closing brackets and quotes** (off by default, see Settings): typing `(` adds `)` after the caret; typing the closing one over it does not double it.
- **Tab and shift+Tab** with several lines selected indent or outdent them. Shift+Tab with nothing selected outdents the caret's line. A plain Tab still types a tab.
- **control+/** comments or uncomments the selected lines, or the caret's line, with the language's comment (`#`, `//`, `--`).
- **control+space** completes the word you are typing. The first suggestion is put in at once and spoken with its place, for example "currentUser, 1 of 3"; press control+space again for the next one. After the last one, what you typed comes back. Suggestions are names from the file, nearest first, then the language's keywords; after `self.` or `user.`, the names used after it in the file.
- **control+shift+space** reads the parameters of the function whose parentheses hold the caret, when that function is declared in the file, and which argument you are on. The caret may also be on the function's name, on its opening parenthesis, or just after its closing one. For a Python method, self is left out.
- **control+shift+K** deletes the selected lines, or the caret's line. **control+shift+up and down arrow** move them. **control+shift+D** copies them below.
- **F2** renames the name at the caret everywhere in the file, but not in comments and strings. It is one change, so control+Z undoes all of it.

## Moving around

These keys work in Notepad and Notepad++:

- alt+down arrow and alt+up arrow: next or previous line at the same level, skipping nested blocks. The move stops at the edge of the block ("End of block", "Start of block").
- alt+page down and alt+page up: next or previous function or class.
- alt+left arrow: up to the parent function or class. alt+right arrow: down to the first one inside.
- alt+home and alt+end: start or end of the block around the caret. Press again to go outward.
- F12: the declaration of the function or class named at the caret (in Notepad++, F12 stays Notepad++'s own; reach it there from the command palette: NVDA+shift+K, then shift+P). shift+F12: a list of every line that uses that name.
- control+shift+O: the outline, a tree of functions and classes.
- control+alt+backspace: back to where the caret was before the last jump (F12, F8, a bookmark, the outline or one of the lists, control+G, and the bracket and block keys). Press again to go further back. control+alt+shift+backspace goes forward again. Small steps such as alt+down arrow are not remembered.
- control+G (Notepad's own Go To): after the jump, Code Compass says where you landed, for example "line 40, in function load". control+alt+backspace brings you back.

## Bookmarks

Bookmarks mark lines to come back to, like the Bookmarks extension in VS Code. They work in Notepad and Notepad++.

- control+alt+K: add a bookmark on the caret's line, or remove the one there.
- control+alt+L and control+alt+J: next and previous bookmark. Where it is comes first, for example "line 40, in function load", then the line. Past the last bookmark you go back to the first one, and Code Compass says "back to the top" (or "back to the bottom").
- NVDA+shift+K, then shift+B: a list of the bookmarks. Enter moves there, Delete removes one.
- A short high note plays when the caret reaches a bookmarked line. It can be turned off in the settings.

Bookmarks are kept per file, also after closing Notepad or restarting NVDA. Each one remembers its line's text too, so it stays on that line when you add or remove lines above it. A new document's bookmarks move with it when you save it. To remove every bookmark in a file, use "Removes every bookmark in the file" in the command palette.

## Files changed by other programs

When you come back to Notepad and another program (an editor, a code generator, Git) has changed the open file, Code Compass notices:

- With no unsaved changes, the file is reloaded right away and Code Compass says what changed, for example "latihan.py changed on disk and was reloaded: 1 line changed, 2 lines added". The caret stays on its line and bookmarks follow their lines.
- With unsaved changes, nothing is replaced: Code Compass tells you, and NVDA+shift+K then R reloads the file when you choose to. It asks first, and control+Z undoes the reload.
- NVDA+shift+K then R also reloads at any time. Saving in Notepad does not count as a change.
- Notepad++ watches its files itself (File, Reload from Disk), so Code Compass leaves it to Notepad++.

## Problems

Code Compass finds problems without running anything: syntax errors in Python (checked by NVDA's own Python) and JSON files, and unclosed or extra brackets in every language. After a program run (see below), the error it stopped on is a problem too.

- While you type: about a second after you stop, Code Compass checks again, and a problem your typing just made (an unclosed bracket, a Python syntax error) plays the error sound right away. The settings can also have it read, or turn this off. Plain text files are not checked while typing.
- F8 and shift+F8: next and previous problem. The problem is read, then its line.
- control+shift+M: a list of every problem; Enter moves there.
- control+S saves as usual, then reports problems, or says "Saved, no problems".
- In Python, a line indented with tabs in a file indented with spaces (or the other way round), or mixing both, is a problem: it sounds right but Python reads it differently.
- In Python and JavaScript, a function or class declared twice in the same place is a problem, because the second one silently replaces the first. Property setters, overloads, getters and setters, and alternatives in if and else are fine.
- A function declared inside a function of the same name (a `def main()` indented inside `def main()`) is allowed, but it is most likely a paste or indentation slip, so it is listed as a warning: "line 19, warning: main is declared inside main, a function with the same name".

## Running Python

control+F5 saves the file and runs it with Python in a Command Prompt window, so the program can print and ask for input. When it ends, the window waits for Enter. If the program stopped on an error in the file, Code Compass tells you the line and the error, and F8 goes straight there. Otherwise it tells you how long the program ran, for example "The program finished in 1.3 seconds, exit code 0".

Python must be installed, from python.org or with the Python install manager. When several versions are installed, Code Compass uses the newest one. It finds Python even when NVDA started before Python was installed, or from the sign-in screen, and the Command Prompt from control+` also gets your current PATH. Notepad does not tell other programs where a file is saved, so Code Compass looks for it in Notepad's command line and in Windows' Recent items, and checks that the file holds what Notepad shows (so another project's file with the same name is not run). If it cannot tell, it asks where the file is.

control+` (the key above Tab) opens a Command Prompt in the file's folder.

## Explorer

control+shift+E shows the project's files and folders as a tree, like VS Code's Explorer. The project is the nearest folder above the file that holds a `.git` folder, `package.json`, `pyproject.toml` or a similar marker, or else the file's own folder. The current file is selected.

- Enter on a file opens it in the same editor (a new Notepad window, or a new tab in Notepad++). Enter on the file you already have open just says so. Enter on a folder opens or closes it, as do the left and right arrows.
- F2 renames, Delete moves to the Recycle Bin (after asking), Backspace goes up one folder, up to the top of the drive.
- On a drive without a Recycle Bin (a network share or a USB drive), Delete says so and asks before deleting permanently.
- Buttons: New file (opens it right away), New folder, Rename, Delete, Copy path, Up one folder, Choose folder, Show in Windows Explorer, Command prompt here.
- `.git`, `__pycache__` and hidden files are left out.

## Command palette

control+shift+P lists every Code Compass command with its keys. Type words to filter the list, press down arrow to reach it, and Enter to run a command.

## Commands after NVDA+shift+K

These work in any text editor. Press NVDA+shift+K, then:

- W: where am I. The blocks around the caret, outermost first, for example "class Profile; func load(), 42 lines; if user != nil". shift+W: the same, with line numbers, in a window you can review.
- F: family. The function or class at the caret, what it is inside, and what it contains, and how many lines it has, for example "function add, 3 lines, in class Shop" or "class Shop, 12 lines, top level. Contains 2: `__init__`, add".
- D: the bracket level at the caret and which brackets are open.
- M: the bracket matching the one at or just before the caret.
- B and E: start and end of the block. Press again to go outward.
- S: select the whole lines of the block around the caret. Repeat to select the next block out.
- N and P: next and previous function or class.
- O: outline. shift+E: explorer. shift+P: command palette.
- C: check brackets. shift+C: list of problems. shift+T: TODO, FIXME and similar notes in comments (not in strings).
- R: reload the file from disk.
- shift+B: list of bookmarks. Backspace: back to where you were before the last jump; shift+Backspace: forward again.
- A: save a snippet. I: insert a snippet.
- T: change the level report: off, tone, speech, both.
- H: list these commands.

Escape cancels. Every command can also get its own key in NVDA's Input Gestures dialog, under Code Compass.

## Snippets

A snippet is a piece of code saved for reuse: a few lines, a function, a class or a file skeleton.

- Save (NVDA+shift+K, then A): with text selected, the selection is saved. Without a selection, the function or class at the caret is saved, with its decorators and body. You are asked for a name, prefilled with the function's name. Shared indentation is removed, so a method from inside a class is stored starting at column 0.
- Insert (NVDA+shift+K, then I): a list of snippets, those in the current file's language first. Tab to the Preview box to read one. Enter inserts it at the caret. When the caret sits at a line's indentation, every line of the snippet gets that indentation.
- The dialog also has Delete and Open snippets folder buttons.

Each snippet is a plain file in the `codeCompass\snippets` folder inside NVDA's configuration folder (usually `%APPDATA%\nvda\codeCompass\snippets`). The file name is the snippet's name and the extension its language, for example `fetchJson.js`, so snippets can also be added, edited or renamed with Explorer and Notepad.

In Windows 10's Notepad, the snippet is put in directly, without touching the clipboard, and control+Z undoes it. Other editors get it through the clipboard: text that was on the clipboard is put back afterwards, but other content, such as files or an image you copied, is replaced by the snippet.

## Languages

The language is guessed from the file name in the window title.

- Python and YAML: blocks also follow indentation.
- C, C++, C#, Java, Rust, Go, Kotlin, JavaScript, TypeScript, Swift, PHP, CSS, Ruby, shell, Lua and SQL are recognized.
- Unsaved or unknown files use a general mode with `//` and `/* */` comments.

Code Compass messages can be in Indonesian even when NVDA is in English: see "Language of Code Compass messages" in the settings.

## Settings

NVDA menu, Preferences, Settings, Code Compass:

- Report bracket level when moving by line: off, tone, speech, tone and speech.
- Only report when the level changes.
- Shorter tone inside parentheses and square brackets.
- Say what closing brackets close.
- Check for problems when saving.
- Play a sound on lines with a problem.
- Play a sound on bookmarked lines.
- Sound style: VS Code sounds (the default) or beeps. With VS Code sounds, lines with an error or a warning, bookmarked lines, saving, finished and failed program runs, and renaming play the same sounds as Visual Studio Code. The bracket level stays a tone, because its pitch tells the level.
- Examine code while typing: off, play a sound for new problems (the default), or play a sound and say them.
- Say the function or class the caret moves into.
- Automatic indentation on Enter and closing brackets (Windows 10 Notepad).
- Add closing brackets and quotes automatically (Windows 10 Notepad). Off by default. Typing the closing character yourself types over the one that was added, and Backspace right after an opening bracket removes both.
- Tone pitch for level 1, and how many semitones higher each level is.
- Applications with level tones and quick keys. The NVDA+shift+K commands work in any text editor.
- Language of Code Compass messages: same as NVDA, Indonesian or English.

## Known limits

- Windows 11's Notepad is a different program: level tones, navigation and reading commands work there, but commands that change text do not.
- VS Code only exposes part of a file to screen readers, so levels there can be wrong. VS Code is not enabled by default.
- The outline and function moves find declarations with patterns, not a full parser. Unusual code styles may be missed.
- Notepad keeps only one step of undo: control+Z undoes the last Code Compass change, not the one before.
- Python syntax errors come from Python's own parser, which reports only the first one in a file.
- Code inside strings is understood for Python f-strings, JavaScript template literals and Swift's \\( ). In other languages' interpolated strings, such as C#'s `$"{name}"` or Kotlin's and Dart's `"${name}"`, the name is text: rename, uses and completion skip it there.
