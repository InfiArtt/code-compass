# Changelog

## Version 0.4.2

### 🛠️ Fixed

- Removing a line's indentation in Python so that `return` or `break` ends up outside its function or loop is now a problem: Python code is compiled (still without running anything), not only parsed.
- The check for new problems also runs after deleting (Delete, Backspace, control+Backspace, control+Delete), cutting and pasting, and after Code Compass's own commands such as shift+Tab or moving lines, not only after typing a character.

## Version 0.4.1

### 🎉 New

- **Undo and redo many steps in Windows 10's Notepad**, like in VS Code. Notepad itself keeps only one step, and its second control+Z brings the change back. Now **control+Z** goes back step by step and **control+Y** (or control+shift+Z) forward again. A step is a run of typing (it ends when you pause or move to another line) or one Code Compass command, such as a line move or a rename. The changed line is read, and going back to the saved text clears the "*" in the title. It can be turned off in the settings.

## Version 0.4.0

The first public release. Coding in Notepad now works much more like a code editor such as VS Code.

### 🎉 New: editing in Windows 10 Notepad

- **Automatic indentation**: Enter keeps the indentation, adds a level after an opening bracket (or `:` in Python) and goes back a level after `return`, `pass`, `break`, `continue` or `raise` in Python. Enter between `{}` puts the closing bracket on its own line. A closing bracket typed first on a line lines up with its opening bracket.
- **Tab and shift+Tab** indent and outdent the selected lines; shift+Tab alone outdents the caret's line.
- **control+/** comments or uncomments lines.
- **control+space** completes the word at the caret with names from the file and the language's keywords, one suggestion at a time, spoken with its place ("currentUser, 1 of 3"). **control+shift+space** reads the parameters of the function you are calling.
- **control+shift+K** deletes lines, **control+shift+up and down arrow** move them, **control+shift+D** duplicates them.
- **F2** renames a name everywhere in the file, outside comments and strings, in one step that control+Z undoes.
- **Closing brackets and quotes can be added automatically** (off by default).
- Text is changed directly in Notepad, without the clipboard or simulated typing.

### 🎉 New: moving around and finding problems

- **Problems**: syntax errors in Python and JSON files are found without running anything, along with unbalanced brackets. **F8** and **shift+F8** go to the next and previous problem, **control+shift+M** lists them, a sound marks lines with a problem, and control+S reports them after saving.
- **Run Python with control+F5**: the file is saved and run in a Command Prompt window, where it can ask for input. If it stops on an error, Code Compass tells you the line and F8 goes there. **control+`** opens a Command Prompt in the file's folder.
- **Explorer (control+shift+E)**: the project's files and folders as a tree. Open files, and create, rename and delete (to the Recycle Bin) files and folders.
- **Command palette (control+shift+P)**: every command with its keys; type to filter.
- **F12** goes to the declaration of the name at the caret; **shift+F12** lists every line that uses it.
- **The current function is announced** when the caret moves into another one, like VS Code's breadcrumbs.
- **TODO notes**: NVDA+shift+K then shift+T lists TODO, FIXME and similar notes in comments.
- **Bookmarks**: **control+alt+K** marks a line, **control+alt+L** and **control+alt+J** go to the next and previous one, and NVDA+shift+K then shift+B lists them. A short note plays on bookmarked lines. Bookmarks are kept per file across NVDA restarts and stay on their line when lines are added or removed above it.
- **Going back**: **control+alt+backspace** returns to where the caret was before a jump (F12, F8, bookmarks, lists, control+G), **control+alt+shift+backspace** goes forward again.
- **control+G** (Notepad's Go To) now says where you landed, such as "line 40, in function load".
- **control+S** says "Saved, no problems" when the check finds nothing.
- **Visual Studio Code's sounds** for lines with an error, a warning or a bookmark, saving, program runs and renaming (beeps remain as an option).
- **Files changed on disk**: when another program changes the open file, Notepad reloads it on your return (or, with unsaved changes, tells you), and says what changed. NVDA+shift+K then R reloads at any time.
- **Problems while typing**: a second after you stop typing, a new problem plays the error sound, and can be read too.
- Python is found through Windows' list of installed Pythons (the newest one is used), so running works even when NVDA started without your PATH, for example from the sign-in screen. The Command Prompt from control+` gets your current PATH too.
- New problems: Python lines indented with tabs where the file uses spaces (or mixing both), and functions or classes declared twice in Python and JavaScript. A function declared inside a function of the same name is listed as a warning.
- Where am I and family say how many lines a function or class has, and a finished program says how long it ran.
- **control+shift+space** also works with the caret on the function's name or its parentheses, and leaves `self` out for Python methods.
- Backspace right after an opening bracket that auto-close completed removes both.

### 🛠️ Fixed

- Finding a declaration's body is much more reliable: functions with parameters on several lines, generic types such as `Component<Props>`, Rust `where` clauses, `throws` or `extends` on the next line, functions passed as arguments (React `forwardRef`, Express, mocha), bodies wrapped in parentheses, and declarations without a body all work.
- Decorators, annotations and attributes (`@dataclass`, `@Override`, `[HttpGet]`, `#[derive]`, `template<>`) belong to the declaration below them, also with a comment or blank line in between.
- A declaration after the end of a class is no longer counted as part of it, and an unclosed bracket while typing no longer nests every later function inside the one before it.
- A Python string with lines at column 0 no longer ends its function early.
- Snippets: Notepad gets snippets without the clipboard; files saved as ANSI or UTF-16 in Notepad can be inserted; names Windows reserves (such as "nul") and hidden files are handled; the snippets dialog no longer fails on a file that cannot be read.
- Messages say "1 problem" and "Selected 1 line" instead of plural forms.
- Names inside Python f-strings, JavaScript template literals and Swift interpolation count for rename, uses (shift+F12) and completion.
- A half-typed f-string field, a JavaScript regex holding a quote or backtick, and Swift raw strings (`#"..."#`) no longer hide the rest of the file from the outline and bracket checks.
- The outline also finds one-line methods, methods with an annotation on the same line (`@Override public String toString() {`), Go types and generic functions, Rust `impl<T> ... for Type`, generic C# methods and Kotlin extension functions. A parameter named `record` or typed `object` no longer turns calls into functions.
- Single-line fields in the editor's own dialogs (Save As, Find) keep their keys, such as alt+up arrow.

## Version 0.3.0

### 🎉 New

- **Snippets**: save a piece of code and insert it again later. NVDA+shift+K then A saves the selected code, or, with nothing selected, the function or class at the caret, body included; you name it in a dialog that already holds the function's name. Shared indentation is removed, so a method from inside a class is stored starting at column 0. NVDA+shift+K then I lists your snippets, those in the current file's language first, with a read-only preview; Enter inserts the selected one at the caret, indented to match the line. Each snippet is a plain file in `%APPDATA%\nvda\codeCompass\snippets`, so you can also edit them with Notepad.
- **Function family** (NVDA+shift+K then F): the function or class at the caret, what it is inside up to the top level, and what it contains, for example "function add, in class Shop" or "class Shop, top level. Contains 2: `__init__`, add".
- **Alt+left arrow and alt+right arrow** in Notepad move to the parent function or class and to the first one inside it.
- **The outline (O) is a tree**: methods sit under their class, so NVDA reports their level, and left and right arrows collapse and expand. It opens on the function the caret is in.

### 🛠️ Fixed

- "1 bracket problems" now reads "1 bracket problem", and "Selected 1 lines" reads "Selected 1 line".

## Version 0.2.0

### 🎉 New

- **Closing brackets say what they close**: moving to a line that starts with a closing bracket, or typing one, reports what it closes, for example "closes func viewDidLoad()". If the bracket is the wrong kind, Code Compass says which bracket is still open and on which line.
- **Quick keys in Notepad**: alt+up and alt+down arrow move to the next or previous line at the same level, skipping nested blocks; alt+page up and alt+page down move by function or class; alt+home and alt+end move to the start and end of the block.
- **Check on save**: control+S saves as usual, then reports unclosed or extra brackets. Nothing is said when all is well.
- **Select a block** (NVDA+shift+K then S); repeat to select the next block out.
- **Next and previous function** in the command layer (N and P).
- **A shorter tone** for lines inside parentheses or square brackets.
- **Indonesian translation**, with its own setting, so Code Compass can speak Indonesian while NVDA stays in another language.

## Version 0.1.1

### 🛠️ Fixed

- **shift+W closed the command layer**: pressing shift on its own ended the layer before W arrived.
- **The outline sometimes opened behind Notepad**, so it could not be found.
- **Block start and end (B and E) in Python** only followed brackets and said "Top level"; they now follow indented blocks too.

## Version 0.1.0

First version.

- A tone for the bracket level of each line when moving by line, higher for deeper levels and silent at the top level. It can also be spoken, or both.
- Command layer on NVDA+shift+K: where am I (W, and shift+W with line numbers), bracket level at the caret (D), matching bracket (M), block start and end (B, E), outline (O), check brackets (C), level report mode (T) and help (H).
- Comments and strings are ignored when counting brackets. The language is taken from the file name in the window title; Python and YAML scopes also follow indentation.
