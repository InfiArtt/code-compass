# -*- coding: UTF-8 -*-
"""Rewrite the Indonesian catalog in source order: keep translations of
messages still in use, drop unused ones, add NEW below, and list anything
left untranslated. Run from the project root:

    py -3.13 tools/update_po.py
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import build  # noqa: E402
from test_translations import PO, source_msgids  # noqa: E402

NEW = {
	"&Snippets:": "&Snippet:",
	"&Preview:": "&Pratinjau:",
	"&Insert": "&Sisipkan",
	"Delete snippet": "Hapus snippet",
	", top level": ", di level paling luar",
	"Reports the function or class at the caret, what it is inside, and what it contains":
		"Membacakan fungsi atau class di kursor, ada di dalam apa, dan isinya apa saja",
	"Moves to the function or class around the caret, or to its parent when already on it":
		"Pindah ke fungsi atau class di sekitar kursor, atau ke induknya kalau sudah di situ",
	"Moves to the first function or class inside the one at the caret":
		"Pindah ke fungsi atau class pertama di dalam yang ada di kursor",
	"Shows functions and classes as a tree; Enter moves to the selected one":
		"Menampilkan fungsi dan class sebagai tree; Enter untuk pindah ke yang dipilih",
	"Saves the selected code as a snippet, or the function or class at the caret when nothing is selected":
		"Menyimpan kode yang dipilih sebagai snippet, atau fungsi atau class di kursor kalau tidak ada yang dipilih",
	"Lists saved snippets; Enter inserts the selected one at the caret":
		"Daftar snippet tersimpan; Enter untuk menyisipkan yang dipilih di kursor",
	"After NVDA+shift+K: W where am I, shift+W details, F function family, D level, "
	"M matching bracket, B block start, E block end, S select block, N next function, "
	"P previous function, O outline, A save snippet, I insert snippet, C check brackets, "
	"T level report mode. In Notepad: alt+up and down arrow move by same level, alt+left "
	"and right arrow to parent and child function, alt+page up and page down by function, "
	"alt+home and end to block start and end.":
		"Setelah NVDA+shift+K: W aku di mana, shift+W detail, F silsilah fungsi, D level, "
		"M pasangan kurung, B awal blok, E akhir blok, S pilih blok, N fungsi berikutnya, "
		"P fungsi sebelumnya, O outline, A simpan snippet, I sisipkan snippet, C cek kurung, "
		"T mode laporan level. Di Notepad: alt+panah atas dan bawah pindah per level yang sama, "
		"alt+panah kiri dan kanan ke fungsi induk dan anak, alt+page up dan page down per fungsi, "
		"alt+home dan end ke awal dan akhir blok.",
	"1 bracket problem: {list}": "1 masalah kurung: {list}",
	"Snippets": "Snippet",
	"De&lete": "&Hapus",
	"Open snippets &folder": "Buka &folder snippet",
	"Not inside a function or class": "Tidak di dalam fungsi atau class",
	"{kind} {name}": "{kind} {name}",
	"No snippets yet. Select code, then press NVDA+shift+K and A to save one":
		"Belum ada snippet. Pilih kode, lalu tekan NVDA+shift+K dan A untuk menyimpan",
	"Could not insert the snippet": "Snippet tidak bisa disisipkan",
	"Saved, but: {problems}": "Tersimpan, tapi: {problems}",
	"Delete snippet {name}?": "Hapus snippet {name}?",
	", in {kind} {name}": ", di dalam {kind} {name}",
	"Select some code first, or put the caret inside a function or class":
		"Pilih kode dulu, atau taruh kursor di dalam fungsi atau class",
	"Snippet not saved: the name is empty": "Snippet tidak disimpan: namanya kosong",
	"Save snippet": "Simpan snippet",
	"Inserted snippet {name}": "Snippet {name} disisipkan",
	"Contains {count}: {names}": "Berisi {count}: {names}",
	"Nothing declared inside {name}": "Tidak ada fungsi atau class di dalam {name}",
	"Snippet saved: {name}": "Snippet tersimpan: {name}",
	"Selected 1 line: {header}": "1 baris dipilih: {header}",
	"Name for the {ext} snippet:": "Nama snippet {ext}:",
	"A snippet named {name} already exists. Replace it?":
		"Snippet bernama {name} sudah ada. Timpa?",
	"Could not read snippet {name}": "Snippet {name} tidak bisa dibaca",
	"Inserted snippet {name}. The clipboard now holds the snippet":
		"Snippet {name} disisipkan. Clipboard sekarang berisi snippet itu",
	# 0.4.0
	"top level": "level paling luar",
	"\nThe program finished (exit code {status}). Press Enter to close this window.":
		"\nProgram selesai (kode keluar {status}). Tekan Enter untuk menutup jendela ini.",
	"in {kind} {name}": "di {kind} {name}",
	"line {line}: {message}": "baris {line}: {message}",
	"{count} problems: {list}": "{count} masalah: {list}",
	"1 problem: {list}": "1 masalah: {list}",
	"&Search commands:": "&Cari perintah:",
	"&Commands:": "&Perintah:",
	"Code Compass commands": "Perintah Code Compass",
	"&Files and folders:": "&File dan folder:",
	"&Open": "&Buka",
	"Close": "Tutup",
	"New file": "File baru",
	"New folder": "Folder baru",
	"Rename": "Ganti nama",
	"Choose a folder to explore": "Pilih folder untuk dijelajahi",
	"Save the file first": "Simpan filenya dulu",
	"Comments or uncomments the selected lines, or the caret's line":
		"Mengomentari atau membatalkan komentar baris yang dipilih, atau baris kursor",
	"Completes the word at the caret with names from the file; press again for the next suggestion":
		"Melengkapi kata di kursor dengan nama dari file ini; tekan lagi untuk saran berikutnya",
	"Reports the parameters of the function whose parentheses hold the caret":
		"Membacakan parameter fungsi yang kurungnya berisi kursor",
	"Deleted": "Dihapus",
	"Deletes the selected lines, or the caret's line": "Menghapus baris yang dipilih, atau baris kursor",
	"Moves the selected lines, or the caret's line, up": "Memindahkan baris yang dipilih, atau baris kursor, ke atas",
	"Moves the selected lines, or the caret's line, down": "Memindahkan baris yang dipilih, atau baris kursor, ke bawah",
	"Duplicated": "Diduplikat",
	"Copies the selected lines, or the caret's line, below themselves":
		"Menyalin baris yang dipilih, atau baris kursor, ke bawahnya",
	"Moves to the declaration of the function or class named at the caret":
		"Pindah ke deklarasi fungsi atau class yang namanya ada di kursor",
	"Lists every line that uses the name at the caret; Enter moves there":
		"Daftar semua baris yang memakai nama di kursor; Enter untuk pindah ke sana",
	"Renames the name at the caret everywhere in the file, outside comments and strings":
		"Mengganti nama di kursor di seluruh file, kecuali di komentar dan string",
	"Moves to the next problem: a syntax error, an unbalanced bracket or the last run's error":
		"Pindah ke masalah berikutnya: error sintaks, kurung tidak seimbang, atau error saat terakhir dijalankan",
	"Moves to the previous problem": "Pindah ke masalah sebelumnya",
	"Lists every problem in the file; Enter moves there": "Daftar semua masalah di file ini; Enter untuk pindah ke sana",
	"Lists TODO, FIXME and similar notes in comments; Enter moves there":
		"Daftar catatan TODO, FIXME, dan sejenisnya di komentar; Enter untuk pindah ke sana",
	"Saves and runs the Python file in a console window; F8 then goes to the error it stopped on":
		"Menyimpan dan menjalankan file Python di jendela console; lalu F8 pindah ke error tempat program berhenti",
	"Opens a Command Prompt in the file's folder": "Membuka Command Prompt di folder file ini",
	"Shows the project's files and folders as a tree; Enter opens a file":
		"Menampilkan file dan folder proyek sebagai tree; Enter untuk membuka file",
	"Lists every Code Compass command with its keys; type to filter, Enter runs one":
		"Daftar semua perintah Code Compass beserta tombolnya; ketik untuk menyaring, Enter untuk menjalankan",
	"After NVDA+shift+K: W where am I, shift+W details, F function family, D level, "
	"M matching bracket, B block start, E block end, S select block, N next function, "
	"P previous function, O outline, shift+E explorer, A save snippet, I insert snippet, "
	"C check brackets, shift+C problems, shift+T TODO notes, shift+B bookmarks, backspace back to where you were, "
	"shift+backspace forward again, "
	"R reload from disk, shift+P all commands, T level report mode. In Notepad, control+shift+P lists every command and its keys.":
		"Setelah NVDA+shift+K: W aku di mana, shift+W detail, F silsilah fungsi, D level, "
		"M pasangan kurung, B awal blok, E akhir blok, S pilih blok, N fungsi berikutnya, "
		"P fungsi sebelumnya, O outline, shift+E explorer, A simpan snippet, I sisipkan snippet, "
		"C cek kurung, shift+C daftar masalah, shift+T catatan TODO, shift+B daftar bookmark, "
		"backspace balik ke tempat sebelumnya, shift+backspace maju lagi, R muat ulang dari disk, shift+P semua perintah, "
		"T mode laporan level. Di Notepad, control+shift+P menampilkan semua perintah dan tombolnya.",
	"New &file": "&File baru",
	"New f&older": "F&older baru",
	"&Rename": "&Ganti nama",
	"&Delete": "&Hapus",
	"Copy &path": "Salin &path",
	"&Up one folder": "&Naik satu folder",
	"&Choose folder...": "&Pilih folder...",
	"Show in &Windows Explorer": "Tampilkan di &Windows Explorer",
	"Command pro&mpt here": "Command pro&mpt di sini",
	"Explorer: {folder}": "Explorer: {folder}",
	"Delete": "Hapus",
	"Could not open a command prompt": "Command Prompt tidak bisa dibuka",
	"This command changes text only in Windows 10 Notepad": "Perintah ini hanya mengubah teks di Notepad Windows 10",
	"No indentation to remove": "Tidak ada indentasi untuk dikurangi",
	"Nothing to comment": "Tidak ada yang bisa dikomentari",
	"No parameters found in this file": "Parameter tidak ditemukan di file ini",
	"Cannot move further": "Tidak bisa pindah lagi",
	"No name at the caret": "Tidak ada nama di kursor",
	"The file changed; rename again": "Filenya berubah; ulangi ganti nama",
	"No problems found": "Tidak ada masalah",
	"No TODO notes found": "Tidak ada catatan TODO",
	"Running works for Python files": "Menjalankan kode hanya untuk file Python",
	"The file is not saved yet": "Filenya belum tersimpan",
	"Python was not found. Install it from python.org, then try again":
		"Python tidak ditemukan. Pasang dari python.org, lalu coba lagi",
	"The program window was closed": "Jendela program ditutup",
	'A name cannot contain any of these characters: < > : " / \\ | ? *':
		'Nama tidak boleh berisi karakter ini: < > : " / \\ | ? *',
	"Name of the new file in {folder}:": "Nama file baru di {folder}:",
	"Name of the new folder in {folder}:": "Nama folder baru di {folder}:",
	"New name for {name}:": "Nama baru untuk {name}:",
	"Outdented": "Indentasi dikurangi",
	"Commented": "Dikomentari",
	"Uncommented": "Komentar dibatalkan",
	"No suggestions": "Tidak ada saran",
	"as typed": "seperti yang diketik",
	"{signature}, argument {number}": "{signature}, argumen ke-{number}",
	"line {line}: {text}": "baris {line}: {text}",
	"&Uses:": "&Pemakaian:",
	"&Problems:": "&Masalah:",
	"line {line}, {kind}: {text}": "baris {line}, {kind}: {text}",
	"&Notes:": "&Catatan:",
	"Running {name}": "Menjalankan {name}",
	"Check for problems when &saving": "Cek masalah saat menyi&mpan",
	"Play a sound on lines with a &problem": "Bunyikan suara di baris yang ada &masalahnya",
	"Say the &function or class the caret moves into": "Sebutkan &fungsi atau class yang dimasuki kursor",
	"Automatic &indentation on Enter and closing brackets (Windows 10 Notepad)":
		"&Indentasi otomatis saat Enter dan kurung tutup (Notepad Windows 10)",
	"Add closing brackets and &quotes automatically (Windows 10 Notepad)":
		"Tambahkan kurung tutup dan &kutip otomatis (Notepad Windows 10)",
	"{name} already exists.": "{name} sudah ada.",
	"Move {name} to the Recycle Bin?": "Pindahkan {name} ke Recycle Bin?",
	"Could not move {name} to the Recycle Bin.": "{name} tidak bisa dipindahkan ke Recycle Bin.",
	"Copied {path}": "Disalin: {path}",
	"Where is {name} saved?": "{name} disimpan di mana?",
	"Could not open {name}": "{name} tidak bisa dibuka",
	"Indented {count} lines": "{count} baris diindentasi",
	"Outdented {count} lines": "Indentasi {count} baris dikurangi",
	"{word}, {index} of {count}": "{word}, {index} dari {count}",
	"{name} is not declared in this file": "{name} tidak dideklarasikan di file ini",
	"This is where {name} is declared": "Di sinilah {name} dideklarasikan",
	"Renamed {count} places to {name}. Control+Z undoes it":
		"{count} tempat diganti menjadi {name}. Control+Z untuk membatalkan",
	"The program stopped on line {line}: {message}. Press F8 to go there":
		"Program berhenti di baris {line}: {message}. Tekan F8 untuk ke sana",
	"{count} lines commented": "{count} baris dikomentari",
	"{count} lines uncommented": "Komentar {count} baris dibatalkan",
	"{word}, as typed": "{word}, seperti yang diketik",
	"Uses of {name}: {count}": "Pemakaian {name}: {count}",
	"{name} is not a valid name": "{name} bukan nama yang valid",
	"Rename {name} ({count} places) to:": "Ganti nama {name} ({count} tempat) menjadi:",
	"Problems: {count}": "Masalah: {count}",
	"TODO notes: {count}": "Catatan TODO: {count}",
	"The program stopped: {message}": "Program berhenti: {message}",
	"The program finished, exit code {status}": "Program selesai, kode keluar {status}",
	# 0.4.0 review: unique access keys per dialog.
	"&Only report when the level changes": "Hanya laporkan saat level &berubah",
	"Play a sound on lines with a p&roblem": "Bunyikan suara di baris yang ada masala&hnya",
	"Tone pitc&h for level 1 (Hz):": "Tinggi nada level &1 (Hz):",
	"Semi&tones higher per level:": "&Semitone naik per level:",
	"Lan&guage of Code Compass messages:": "Bahasa p&esan Code Compass:",
	"Add closing brackets and &quotes automatically (Windows 10 Notepad)":
		"Tambahkan kurung tutup dan k&utip otomatis (Notepad Windows 10)",
	"New fi&le": "File bar&u",
	"New fol&der": "F&older baru",
	"Dele&te": "&Hapus",
	"Copy &path": "Salin pa&th",
	"&Choose folder...": "P&ilih folder...",
	"&Insert": "S&isipkan",
	"Top of the drive": "Sudah di puncak drive",
	"{name} is on a drive with no Recycle Bin. Delete it permanently? This cannot be undone.":
		"{name} ada di drive tanpa Recycle Bin. Hapus permanen? Ini tidak bisa dibatalkan.",
	"{name} was not deleted.": "{name} tidak dihapus.",
	"{name} is already open": "{name} sudah terbuka",
	# 0.4.0 review round 3: access keys no NVDA settings panel uses.
	"Shorter tone insi&de parentheses and square brackets": "Nada lebih &pendek di dalam kurung biasa dan kurung siku",
	"Sa&y what closing brackets close": "Sebutkan apa yang ditutup oleh kurung &tutup",
	"Check for problems &when saving": "Cek masalah saat menyi&mpan",
	"Applications with level tones and quick keys (co&mma separated):":
		"Aplikasi dengan nada level dan tombol cepat (pisahkan &dengan koma):",
	"Indented": "Diindentasi",
	"The program stopped on line {line}: {message}. NVDA+shift+K, then shift+C lists it":
		"Program berhenti di baris {line}: {message}. NVDA+shift+K, lalu shift+C untuk melihatnya",
	# Bookmarks.
	"line {line}": "baris {line}",
	"Removed": "Dihapus",
	"Adds a bookmark on the caret's line, or removes the one there":
		"Menambahkan bookmark di baris kursor, atau menghapus bookmark yang ada di sana",
	"Moves to the next bookmark": "Pindah ke bookmark berikutnya",
	"Moves to the previous bookmark": "Pindah ke bookmark sebelumnya",
	"Lists the bookmarks in the file; Enter moves there, Delete removes one":
		"Daftar bookmark di file ini; Enter untuk pindah ke sana, Delete untuk menghapus",
	"Removes every bookmark in the file": "Menghapus semua bookmark di file ini",
	"No bookmarks in this file": "Tidak ada bookmark di file ini",
	"This is the only bookmark": "Ini satu-satunya bookmark",
	"Removed 1 bookmark": "1 bookmark dihapus",
	"Removed {count} bookmarks": "{count} bookmark dihapus",
	"back to the top": "balik ke atas",
	"back to the bottom": "balik ke bawah",
	"&Bookmarks:": "&Bookmark:",
	"Play a sound on bookmarked li&nes": "Bu&nyikan nada di baris yang ada bookmark-nya",
	"Bookmark added, line {line}": "Bookmark ditambahkan, baris {line}",
	"Bookmark removed, line {line}": "Bookmark dihapus, baris {line}",
	"Bookmarks: {count}": "Bookmark: {count}",
	# Small touches.
	"1 line": "1 baris",
	"{count} lines": "{count} baris",
	"under 0.1 seconds": "kurang dari 0,1 detik",
	"1 minute": "1 menit",
	"{minutes} minutes": "{minutes} menit",
	"1 second": "1 detik",
	"line {line}, warning: {message}": "baris {line}, peringatan: {message}",
	"Put the caret inside the parentheses of a call": "Taruh kursor di dalam kurung pemanggilan fungsi",
	# Reload.
	"only spacing changed": "cuma spasi yang berubah",
	"Reloads the file from disk, after asking when it has unsaved changes":
		"Memuat ulang file dari disk, dengan bertanya dulu kalau ada perubahan yang belum disimpan",
	"1 line changed": "1 baris berubah",
	"{count} lines changed": "{count} baris berubah",
	"1 line added": "1 baris ditambah",
	"{count} lines added": "{count} baris ditambah",
	"1 line removed": "1 baris dihapus",
	"{count} lines removed": "{count} baris dihapus",
	"Notepad++ reloads files itself: File, Reload from Disk":
		"Notepad++ memuat ulang file sendiri: File, Reload from Disk",
	"Could not find the file on disk": "File-nya tidak ditemukan di disk",
	"Reload": "Muat ulang",
	"{name} is no longer on disk": "{name} sudah tidak ada di disk",
	"{name} changed on disk": "{name} berubah di disk",
	"Could not reload {name}": "{name} tidak bisa dimuat ulang",
	"{name} changed on disk, and you have unsaved changes. NVDA+shift+K, then R reloads it":
		"{name} berubah di disk, dan kamu punya perubahan yang belum disimpan. NVDA+shift+K, lalu R untuk memuat ulang",
	"{name} changed on disk and was reloaded: {changes}": "{name} berubah di disk dan sudah dimuat ulang: {changes}",
	"{name} is the same as on disk": "{name} sudah sama dengan yang di disk",
	"Reloaded {name}: {changes}": "{name} dimuat ulang: {changes}",
	"{name} has changes you have not saved. Reload it from disk anyway? Control+Z undoes the reload.":
		"{name} punya perubahan yang belum disimpan. Tetap muat ulang dari disk? Control+Z membatalkan pemuatan ulang.",
	# Sounds.
	"VS Code sounds": "Suara VS Code",
	"Beeps": "Bip",
	"Play a sound for new problems": "Bunyikan suara untuk masalah baru",
	"Play a sound and say new problems": "Bunyikan suara dan bacakan masalah baru",
	"Sound styl&e:": "&Gaya suara:",
	"E&xamine code while typing:": "Pe&riksa kode saat mengetik:",
	"{name} is declared inside {name}, a function with the same name":
		"{name} dideklarasikan di dalam {name}, fungsi yang namanya sama",
	"{seconds} seconds": "{seconds} detik",
	".": ",",
	"Saved, no problems": "Tersimpan, tidak ada masalah",
	"Goes back to where the caret was before the last jump": "Kembali ke posisi kursor sebelum lompatan terakhir",
	"Goes forward again after going back": "Maju lagi setelah kembali",
	"No earlier place to go back to": "Tidak ada posisi sebelumnya untuk dituju",
	"No later place to go forward to": "Tidak ada posisi berikutnya untuk dituju",
	"The program finished in {time}, exit code {status}": "Program selesai dalam {time}, kode keluar {status}",
	"{name} is declared again; the one on line {line} no longer counts":
		"{name} dideklarasikan lagi; yang di baris {line} jadi tidak berlaku",
	"tabs and spaces mixed in the indentation": "tab dan spasi bercampur di indentasi",
	"indented with spaces, the rest of the file uses tabs": "indentasi pakai spasi, bagian lain file pakai tab",
	"indented with tabs, the rest of the file uses spaces": "indentasi pakai tab, bagian lain file pakai spasi",
}

HEADER = (
	'# Indonesian translation for Code Compass.\n'
	'msgid ""\n'
	'msgstr ""\n'
	'"Project-Id-Version: codeCompass\\n"\n'
	'"Language: id\\n"\n'
	'"MIME-Version: 1.0\\n"\n'
	'"Content-Type: text/plain; charset=UTF-8\\n"\n'
	'"Content-Transfer-Encoding: 8bit\\n"\n'
)


def quote(s):
	return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def main():
	old = build.read_po(PO)
	old.update(NEW)
	seen = []
	for msgid in source_msgids():
		if msgid not in seen:
			seen.append(msgid)
	out = [HEADER]
	missing = []
	for msgid in seen:
		msgstr = old.get(msgid)
		if not msgstr:
			missing.append(msgid)
			continue
		out.append("msgid %s\nmsgstr %s\n" % (quote(msgid), quote(msgstr)))
	with open(PO, "w", encoding="utf-8", newline="\n") as f:
		f.write("\n".join(out))
	print("%d messages, %d missing" % (len(seen), len(missing)))
	for m in missing:
		print("  missing:", m)


if __name__ == "__main__":
	main()
