# -*- coding: UTF-8 -*-
"""Code Compass runner.

Runs a Python program in this console window, so it can print and read input
as in a terminal. When the program stops on an uncaught error, the error and
its line are written to a small report file for Code Compass, which then
offers F8 to go to that line. The window stays open until Enter is pressed.

Usage: python run_python.py PROGRAM REPORT_FILE [PROMPT]
PROMPT may contain {status}, the program's exit code.

The runner avoids the traceback and linecache modules' line lookups when it
locates the error, so a program that shadows a standard module (a token.py
next to it) still gets its report.
"""

import json
import os
import runpy
import sys
import threading
import time

#: Files whose frames are the runner's own or Python's runpy.
_OWN_FILES = ("runpy.py", os.path.basename(__file__))


def _same_file(a, b):
	return bool(a) and bool(b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _own_frame(filename):
	return filename.endswith(_OWN_FILES) or filename.startswith("<frozen")


def _frames(exc):
	"""(filename, line, function) for each traceback frame, oldest first,
	read without the traceback module."""
	out = []
	tb = exc.__traceback__
	while tb is not None:
		code = tb.tb_frame.f_code
		out.append((code.co_filename, tb.tb_lineno, code.co_name))
		tb = tb.tb_next
	return out


def _message(exc):
	"""One line: the exception's type and the first line of its message."""
	try:
		text = exc.msg if isinstance(exc, SyntaxError) and exc.msg else str(exc)
	except Exception:
		text = "<exception str() failed>"
	text = (text or "").strip()
	first = text.splitlines()[0] if text else ""
	name = type(exc).__qualname__
	return "%s: %s" % (name, first) if first else name


def locate(exc, program):
	"""The program's line where exc happened, and a one-line message. When the
	error is in another file of the program's folder (an imported module),
	the message names that file and line; the line is where the program
	called into it. Library files are not named."""
	message = _message(exc)
	frames = _frames(exc)
	folder = os.path.normcase(os.path.dirname(os.path.abspath(program)))
	line = None
	for filename, lineno, _name in frames:
		if _same_file(filename, program):
			line = lineno
	if isinstance(exc, SyntaxError) and exc.filename:
		if _same_file(exc.filename, program):
			return {"line": exc.lineno or 1, "message": message}
		where = (exc.filename, exc.lineno)
	else:
		where = None
		for filename, lineno, _name in reversed(frames):
			if _same_file(filename, program):
				break
			if not _own_frame(filename) and os.path.normcase(os.path.dirname(os.path.abspath(filename))) == folder:
				where = (filename, lineno)
				break
	if where and os.path.normcase(os.path.dirname(os.path.abspath(where[0]))) == folder:
		message = "%s line %s: %s" % (os.path.basename(where[0]), where[1], message)
	return {"line": line, "message": message}


def _console_err(order=("__stderr__", "__stdout__")):
	"""A stream to write to, even if the program closed its own."""
	for stream in (getattr(sys, name) for name in order):
		if stream is not None and not getattr(stream, "closed", True):
			return stream
	try:
		return open("CONOUT$", "w", encoding="utf-8", errors="replace")
	except OSError:
		return None


def print_error(exc, out):
	"""The traceback without the runner's own frames. Uses the traceback
	module when it works, and a plain listing when it does not (a module the
	program shadows can break it)."""
	try:
		import traceback
		tbe = traceback.TracebackException.from_exception(exc)
		tbe.stack = traceback.StackSummary.from_list([f for f in tbe.stack if not _own_frame(f.filename)])
		out.write("".join(tbe.format()))
		return
	except Exception:
		pass
	out.write("Traceback (most recent call last):\n")
	for filename, lineno, name in _frames(exc):
		if not _own_frame(filename):
			out.write('  File "%s", line %s, in %s\n' % (filename, lineno, name))
	out.write(_message(exc) + "\n")


def _read_enter():
	"""Wait for Enter on the console, even if the program closed stdin."""
	stream = sys.__stdin__
	if stream is not None and not getattr(stream, "closed", True):
		stream.readline()
		return
	with open("CONIN$", "r") as console:
		console.readline()


def main():
	program, report = sys.argv[1], sys.argv[2]
	prompt = sys.argv[3] if len(sys.argv) > 3 else "\nThe program finished (exit code {status}). Press Enter to close this window."
	folder = os.path.dirname(os.path.abspath(program))
	sys.argv = [program]
	sys.path.insert(0, folder)
	status = 0
	error = None
	started = time.perf_counter()
	try:
		try:
			runpy.run_path(program, run_name="__main__")
		except SystemExit as e:
			if e.code is None:
				status = 0
			elif isinstance(e.code, int):
				# bool is an int too: sys.exit(True) exits with 1.
				status = int(e.code)
			else:
				out = _console_err()
				if out is not None:
					out.write("%s\n" % e.code)
				status = 1
		except BaseException as e:
			status = 1
			# Print and locate without the program's folder on sys.path, so
			# its own token.py or ast.py cannot break the traceback.
			savedPath = list(sys.path)
			sys.path[:] = [p for p in sys.path if not _same_file(p or ".", folder)]
			try:
				out = _console_err()
				if out is not None:
					print_error(e, out)
			except Exception:
				pass
			try:
				error = locate(e, program)
			except Exception:
				error = {"line": None, "message": type(e).__name__}
			sys.path[:] = savedPath
		# What Python does at exit: wait for the program's non-daemon threads
		# (thread pools included, through threading's own atexit hooks), then
		# run its atexit handlers, so their output shows before the prompt.
		try:
			threading._shutdown()
		except BaseException:
			pass
		try:
			import atexit
			atexit._run_exitfuncs()
		except BaseException:
			pass
	finally:
		try:
			with open(report, "w", encoding="utf-8") as f:
				json.dump({"status": status, "error": error, "seconds": round(time.perf_counter() - started, 3)}, f)
		except OSError:
			pass
		out = _console_err(("__stdout__", "__stderr__"))
		for stream in (sys.stdout, sys.stderr):
			try:
				stream.flush()
			except Exception:
				pass
		try:
			if out is not None:
				out.write(prompt.format(status=status))
				out.flush()
		except Exception:
			pass
		try:
			_read_enter()
		except Exception:
			pass


if __name__ == "__main__":
	main()
