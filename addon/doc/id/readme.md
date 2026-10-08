# Code Compass

Code Compass bikin ngoding di Notepad kerasa lebih mirip editor kode, lewat suara. Dia ngasih tahu seberapa dalam posisimu di dalam kurung, kurung tutup itu nutup apa, dan kamu lagi di fungsi mana. Dia juga nemuin masalah di kode, jalanin Python, nampilin file-file proyek, dan nambahin tombol-tombol edit yang biasa ada di VS Code.

Paling enak dipakai di Notepad Windows 10. Notepad++ juga aktif secara default. Perintah yang ngubah teks (indentasi otomatis, komentar, mindahin baris, autocomplete, ganti nama) cuma jalan di Notepad Windows 10. Notepad++ udah punya versinya sendiri, jadi tombol-tombol itu tetap ngejalanin perintah Notepad++. Begitu juga F8, shift+F8, F12, control+shift+P, dan control+shift+space, yang dipakai Notepad++ buat perintahnya sendiri: di sana, versi Code Compass bisa dipanggil lewat NVDA+shift+K (shift+P buka Command Palette).

## Waktu pindah baris

### Level kurung

Tiap pindah baris ke atas atau ke bawah, ada nada pendek. Makin dalam level kurungnya, makin tinggi nadanya. Baris di level paling luar (di luar semua kurung) nggak bunyi. Baris yang ada di dalam kurung biasa atau kurung siku, misalnya lanjutan pemanggilan fungsi yang panjang, bunyinya lebih pendek dari baris di dalam kurung kurawal.

Level itu jumlah kurung yang masih kebuka di awal baris. Baris yang diawali kurung tutup dihitung di level luarnya, sama kayak indentasi. Kurung di dalam string dan komentar nggak dihitung.

Di pengaturan bisa pilih nada, ucapan ("level 2"), dua-duanya, atau mati. Bisa juga diatur supaya cuma dilaporin kalau levelnya berubah. Di mode itu, balik ke level paling luar juga dilaporin, pakai nada rendah atau "level 0".

Kalau laporan indentasi NVDA diset ke nada, dua nadanya bisa saling motong. Ubah laporan indentasi NVDA ke ucapan (di pengaturan Document Formatting), atau ubah Code Compass ke ucapan.

### Kurung tutup

Di baris yang diawali kurung tutup, sesudah barisnya dibacain, Code Compass nyebut kurung itu nutup apa, misalnya "tutup func viewDidLoad()". Waktu ngetik kurung tutup juga sama. Kalau jenis kurungnya salah, kamu dikasih tahu kurung mana yang masih kebuka dan di baris berapa.

### Fungsi yang lagi dimasuki

Waktu kursor masuk ke fungsi atau class lain, Code Compass nyebut sekali, misalnya "di fungsi load", mirip breadcrumb di VS Code. Kalau keluar dari semua fungsi, dia bilang "level paling luar".

### Masalah

Baris yang ada masalahnya bunyi dengung rendah sesudah nada levelnya. Lihat bagian Masalah di bawah.

## Ngedit di Notepad Windows 10

- **Indentasi otomatis**: Enter ngikutin indentasi baris sekarang, nambah satu level sesudah kurung buka (atau `:` di Python), dan mundur satu level sesudah `return`, `pass`, `break`, `continue`, atau `raise` di Python. Enter di antara pasangan kayak `{}` naruh kurung tutupnya di baris sendiri, dan kursornya di baris tengah. Kurung tutup yang diketik paling awal di sebuah baris otomatis mundur sejajar sama kurung bukanya.
- **Undo dan redo berkali-kali**: control+Z mundur satu langkah, sejauh yang kamu mau, dan control+Y (atau control+shift+Z) maju lagi. Satu langkah itu satu rombongan ketikan (selesai kalau kamu berhenti sedetik atau pindah baris), atau satu perintah Code Compass, misalnya pindah baris, komentar, atau rename. Baris yang berubah dibacain. Kalau balik ke teks yang udah disimpan, tanda "*" di judul ilang. Langkah-langkahnya ada selama file-nya kebuka; Notepad sendiri cuma nyimpen satu.
- **Kurung tutup dan kutip otomatis** (mati secara default, lihat Pengaturan): ngetik `(` langsung nambah `)` sesudah kursor, dan ngetik kurung tutupnya nggak bikin dobel.
- **Tab dan shift+Tab** pas beberapa baris dipilih: nambah atau ngurangin indentasi baris-baris itu. Shift+Tab tanpa pilihan ngurangin indentasi baris kursor. Tab biasa tetap ngetik tab.
- **control+/**: ngomentarin atau batalin komentar di baris yang dipilih, atau di baris kursor, pakai tanda komentar bahasanya (`#`, `//`, `--`).
- **control+space**: ngelengkapin kata yang lagi kamu ketik. Saran pertama langsung dimasukin dan disebut urutannya, misalnya "currentUser, 1 dari 3". Tekan control+space lagi buat saran berikutnya. Sesudah saran terakhir, ketikanmu yang asli balik lagi. Sarannya dari nama-nama di file itu (yang paling dekat duluan), lalu kata kunci bahasanya. Sesudah `self.` atau `user.`, sarannya nama-nama yang pernah dipakai sesudah itu di file.
- **control+shift+space**: bacain parameter fungsi yang kurungnya berisi kursor (kalau fungsinya dideklarasikan di file itu), plus kamu lagi di argumen ke berapa. Kursornya boleh juga di nama fungsinya, di kurung bukanya, atau persis setelah kurung tutupnya. Buat method Python, self nggak ikut dibacain.
- **control+shift+K** ngehapus baris yang dipilih atau baris kursor. **control+shift+panah atas/bawah** mindahin baris itu. **control+shift+D** nyalin baris itu ke bawahnya.
- **F2**: ganti nama yang ada di kursor di seluruh file, kecuali di komentar dan string. Gantinya satu langkah, jadi control+Z bisa balikin semuanya.

## Pindah-pindah

Tombol-tombol ini jalan di Notepad dan Notepad++:

- alt+panah bawah dan alt+panah atas: baris berikutnya atau sebelumnya yang levelnya sama. Isi blok di dalamnya dilewatin, dan berhenti di batas blok ("Akhir blok", "Awal blok").
- alt+page down dan alt+page up: fungsi atau class berikutnya atau sebelumnya.
- alt+panah kiri: naik ke fungsi atau class induk. alt+panah kanan: turun ke yang pertama di dalamnya.
- alt+home dan alt+end: awal atau akhir blok di sekitar kursor. Tekan lagi buat naik ke blok luarnya.
- F12: deklarasi fungsi atau class yang namanya ada di kursor (di Notepad++, F12 tetap jadi perintah Notepad++; di sana panggil lewat Command Palette: NVDA+shift+K, lalu shift+P). shift+F12: daftar semua baris yang make nama itu.
- control+shift+O: outline, yaitu tree fungsi dan class.
- control+alt+backspace: balik ke posisi kursor sebelum lompatan terakhir (F12, F8, bookmark, outline atau salah satu daftar, control+G, dan tombol kurung dan blok). Tekan lagi buat mundur lebih jauh. control+alt+shift+backspace buat maju lagi. Langkah kecil kayak alt+panah bawah nggak dicatat.
- control+G (Go To bawaan Notepad): habis lompat, Code Compass ngasih tahu kamu nyampe di mana, misalnya "baris 40, di fungsi load". control+alt+backspace bawa kamu balik.

## Bookmark

Bookmark nandain baris yang mau kamu datangin lagi, kayak ekstensi Bookmarks di VS Code. Jalan di Notepad dan Notepad++.

- control+alt+K: pasang bookmark di baris kursor, atau lepas bookmark yang ada di situ.
- control+alt+L dan control+alt+J: bookmark berikutnya dan sebelumnya. Yang dibacain duluan letaknya, misalnya "baris 40, di fungsi load", baru barisnya. Lewat dari bookmark terakhir, kamu balik ke bookmark pertama, dan Code Compass bilang "balik ke atas" (atau "balik ke bawah").
- NVDA+shift+K, lalu shift+B: daftar bookmark. Enter buat lompat ke sana, Delete buat hapus satu.
- Ada nada tinggi pendek waktu kursor nyampe di baris yang ada bookmark-nya. Bisa dimatiin di pengaturan.

Bookmark disimpan per file, tetap ada walaupun Notepad ditutup atau NVDA di-restart. Tiap bookmark juga ingat isi barisnya, jadi dia tetap nempel di baris itu walaupun kamu nambah atau ngapus baris di atasnya. Bookmark di dokumen baru ikut pindah waktu dokumennya kamu simpan. Buat ngapus semua bookmark di satu file, pakai "Menghapus semua bookmark di file ini" di Command Palette.

## File yang diubah program lain

Waktu kamu balik ke Notepad dan file yang kebuka udah diubah program lain (editor lain, generator kode, Git), Code Compass langsung tahu:

- Kalau nggak ada perubahan yang belum disimpan, file-nya langsung dimuat ulang dan Code Compass ngasih tahu apa yang berubah, misalnya "latihan.py berubah di disk dan sudah dimuat ulang: 1 baris berubah, 2 baris ditambah". Kursor tetap di barisnya, dan bookmark ngikutin barisnya.
- Kalau ada perubahan yang belum disimpan, nggak ada yang diganti: Code Compass cuma ngasih tahu, dan NVDA+shift+K lalu R buat muat ulang kalau kamu mau. Dia nanya dulu, dan control+Z ngebatalin pemuatan ulangnya.
- NVDA+shift+K lalu R juga bisa dipakai kapan aja. Nyimpen di Notepad nggak dihitung sebagai perubahan.
- Notepad++ udah ngawasin file-nya sendiri (File, Reload from Disk), jadi Code Compass nyerahin ke Notepad++.

## Masalah

Code Compass nemuin masalah tanpa ngejalanin kodenya: error sintaks di file Python (dicek pakai Python bawaan NVDA) dan JSON, plus kurung yang belum ketutup atau berlebih di semua bahasa. Sesudah program dijalanin (lihat di bawah), error tempat program berhenti juga ikut jadi masalah.

- Waktu ngetik: sekitar satu detik setelah kamu berhenti ngetik, ngapus, nempel (paste), atau make perintah kayak shift+Tab, Code Compass ngecek lagi. Masalah yang baru aja muncul gara-gara perubahan itu (kurung belum ketutup, error sintaks Python) langsung dibunyiin pakai suara error. Di pengaturan, masalahnya bisa sekalian dibacain, atau fitur ini dimatiin. File teks biasa nggak dicek waktu ngetik.
- F8 dan shift+F8: masalah berikutnya dan sebelumnya. Masalahnya dibacain dulu, baru barisnya.
- control+shift+M: daftar semua masalah, Enter buat lompat ke sana.
- control+S nyimpen kayak biasa, terus ngelaporin masalah, atau bilang "Tersimpan, tidak ada masalah".
- Di Python, baris yang indentasinya pakai tab padahal file-nya pakai spasi (atau sebaliknya), atau nyampur dua-duanya, dihitung masalah: kedengerannya bener, tapi Python bacanya beda.
- Di Python dan JavaScript, fungsi atau class yang dideklarasiin dua kali di tempat yang sama dihitung masalah, soalnya yang kedua diam-diam nimpa yang pertama. Property setter, overload, getter dan setter, dan alternatif di if dan else aman.
- Fungsi yang dideklarasiin di dalam fungsi yang namanya sama (`def main()` yang keindentasi di dalam `def main()`) itu boleh, tapi hampir pasti salah tempel atau salah indentasi, jadi dicatat sebagai peringatan: "baris 19, peringatan: main dideklarasikan di dalam main, fungsi yang namanya sama".

## Jalanin Python

control+F5 nyimpen file terus ngejalaninnya pakai Python di jendela Command Prompt, jadi programnya bisa nampilin tulisan dan minta input. Pas selesai, jendelanya nunggu kamu tekan Enter. Kalau program berhenti gara-gara error di file itu, Code Compass ngasih tahu baris dan error-nya, dan F8 langsung lompat ke sana. Kalau nggak, dia ngasih tahu berapa lama programnya jalan, misalnya "Program selesai dalam 1,3 detik, kode keluar 0".

Python harus udah terpasang, dari python.org atau pakai Python install manager. Kalau ada beberapa versi, Code Compass pakai yang paling baru. Python tetap ketemu walaupun NVDA jalan duluan sebelum Python di-install, atau dijalanin dari layar login, dan Command Prompt dari control+` juga dapet PATH kamu yang terbaru. Notepad nggak ngasih tahu program lain di mana filenya disimpan, jadi Code Compass nyarinya dari command line Notepad dan daftar Recent Windows, terus ngecek isi file itu sama dengan yang tampil di Notepad (biar file bernama sama dari proyek lain nggak kejalan). Kalau masih ragu, dia nanya di mana filenya.

control+` (tombol di atas Tab) buka Command Prompt di folder file itu.

## Explorer

control+shift+E nampilin file dan folder proyek sebagai tree, kayak Explorer di VS Code. Proyeknya itu folder terdekat di atas file yang punya folder `.git`, file `package.json`, `pyproject.toml`, atau penanda sejenis. Kalau nggak ada, foldernya file itu sendiri. File yang lagi dibuka langsung kepilih.

- Enter di file: buka file itu di editor yang sama (jendela Notepad baru, atau tab baru di Notepad++). Enter di file yang lagi kebuka cuma ngasih tahu kalau file itu udah kebuka. Enter di folder: buka atau tutup folder itu, sama kayak panah kiri dan kanan.
- F2 buat ganti nama, Delete buat mindahin ke Recycle Bin (ditanya dulu), Backspace buat naik satu folder, sampai puncak drive.
- Di drive tanpa Recycle Bin (drive jaringan atau flashdisk), Delete ngasih tahu dulu dan nanya sebelum ngehapus permanen.
- Tombol-tombolnya: File baru (langsung kebuka), Folder baru, Ganti nama, Hapus, Salin path, Naik satu folder, Pilih folder, Tampilkan di Windows Explorer, Command Prompt di sini.
- Folder `.git`, `__pycache__`, dan file tersembunyi nggak ditampilin.

## Command Palette

control+shift+P nampilin semua perintah Code Compass beserta tombolnya. Ketik kata buat nyaring, tekan panah bawah buat masuk ke daftarnya, terus Enter buat jalanin perintahnya.

## Perintah lewat NVDA+shift+K

Perintah-perintah ini jalan di semua editor teks. Tekan NVDA+shift+K, lalu:

- W: aku di mana. Blok-blok yang ngebungkus kursor, dari yang paling luar, misalnya "class Profile; func load(), 42 baris; if user != nil". shift+W: sama, plus nomor baris, di jendela yang bisa ditelusuri.
- F: silsilah. Fungsi atau class di kursor, dia ada di dalam apa, dan isinya apa aja, plus berapa barisnya, misalnya "fungsi add, 3 baris, di dalam class Shop" atau "class Shop, 12 baris, di level paling luar. Berisi 2: `__init__`, add".
- D: level kurung di kursor dan kurung apa aja yang lagi kebuka.
- M: pasangan kurung yang ada di kursor atau persis sebelum kursor.
- B dan E: awal dan akhir blok. Tekan lagi buat naik ke blok luarnya.
- S: pilih seluruh baris blok di sekitar kursor. Ulangi buat milih blok luarnya.
- N dan P: fungsi atau class berikutnya dan sebelumnya.
- O: outline. shift+E: explorer. shift+P: Command Palette.
- C: cek kurung. shift+C: daftar masalah. shift+T: catatan TODO, FIXME, dan sejenisnya di komentar (bukan di string).
- R: muat ulang file dari disk.
- shift+B: daftar bookmark. Backspace: balik ke tempat sebelum lompatan terakhir; shift+Backspace: maju lagi.
- A: simpan snippet. I: sisipkan snippet.
- T: ganti mode laporan level: mati, nada, ucapan, dua-duanya.
- H: bacain daftar perintah ini.

Escape buat batal. Tiap perintah juga bisa dikasih tombol sendiri lewat dialog Input Gestures NVDA, di kategori Code Compass.

## Snippet

Snippet itu potongan kode yang disimpan buat dipakai lagi: beberapa baris, satu fungsi, satu class, atau kerangka file.

- Simpan (NVDA+shift+K lalu A): kalau ada teks yang dipilih, yang disimpan pilihan itu. Kalau nggak ada, yang disimpan fungsi atau class tempat kursor berada, lengkap sama dekorator dan isinya. Habis itu ditanya namanya, dan nama fungsinya udah keisi duluan. Indentasi bersama dibuang, jadi method dari dalam class disimpan mulai dari kolom 0.
- Sisipkan (NVDA+shift+K lalu I): daftar snippet muncul, dan snippet yang bahasanya sama dengan file yang lagi dibuka ada di atas. Tab ke kotak Pratinjau buat baca isinya. Enter buat nyisipin di kursor. Kalau kursor ada di indentasi baris, semua baris snippet ikut diindentasi segitu.
- Di dialog itu juga ada tombol Hapus dan Buka folder snippet.

Tiap snippet disimpan sebagai file biasa di folder `codeCompass\snippets` di dalam folder konfigurasi NVDA (biasanya `%APPDATA%\nvda\codeCompass\snippets`). Nama file jadi nama snippet, ekstensinya jadi bahasanya, misalnya `fetchJson.js`. Jadi snippet bisa juga ditambah, diedit, atau diganti namanya lewat Explorer dan Notepad.

Di Notepad Windows 10, snippet langsung dimasukin tanpa nyentuh clipboard, dan bisa dibatalin pakai control+Z. Editor lain dapat snippet lewat clipboard: teks yang tadinya ada di clipboard dibalikin lagi sesudahnya, tapi isi lain, misalnya file atau gambar yang kamu copy, bakal ketimpa snippet.

## Bahasa

Bahasa pemrograman ditebak dari nama file di judul jendela.

- Python dan YAML: blok juga ngikutin indentasi.
- C, C++, C#, Java, Rust, Go, Kotlin, JavaScript, TypeScript, Swift, PHP, CSS, Ruby, shell, Lua, dan SQL dikenali.
- File yang belum disimpan atau nggak dikenal pakai mode umum dengan komentar `//` dan `/* */`.

Pesan Code Compass bisa pakai bahasa Indonesia walaupun NVDA-nya bahasa Inggris. Atur di pilihan "Language of Code Compass messages".

## Pengaturan

Menu NVDA, Preferences, Settings, Code Compass:

- Laporan level kurung waktu pindah baris: mati, nada, ucapan, nada dan ucapan.
- Cuma laporin kalau levelnya berubah.
- Nada lebih pendek di dalam kurung biasa dan kurung siku.
- Sebutin kurung tutup nutup apa.
- Cek masalah waktu nyimpen.
- Bunyiin suara di baris yang ada masalahnya.
- Bunyiin nada di baris yang ada bookmark-nya.
- Gaya suara: suara VS Code (default) atau bip. Pakai suara VS Code, baris yang ada error atau peringatan, baris yang ada bookmark-nya, nyimpen, program yang selesai atau gagal, dan rename bunyinya sama kayak di Visual Studio Code. Level kurung tetap pakai nada, soalnya tinggi nadanya yang ngasih tahu levelnya.
- Periksa kode saat mengetik: mati, bunyiin suara buat masalah baru (default), atau bunyiin suara sekalian dibacain.
- Sebutin fungsi atau class yang dimasuki kursor.
- Indentasi otomatis saat Enter dan kurung tutup (Notepad Windows 10).
- Undo dan redo berkali-kali dengan control+Z dan control+Y (Notepad Windows 10). Nyala secara default.
- Tambahin kurung tutup dan kutip otomatis (Notepad Windows 10). Mati secara default. Kalau kamu ngetik sendiri karakter penutupnya, yang tadi ditambahin bakal ditimpa, dan Backspace persis setelah kurung buka ngapus dua-duanya.
- Tinggi nada level 1, dan berapa semitone naiknya tiap level.
- Aplikasi yang dapat nada level dan tombol cepat. Perintah lewat NVDA+shift+K jalan di semua editor teks.
- Bahasa pesan Code Compass: ikut NVDA, Indonesia, atau Inggris.

## Batasan

- Notepad Windows 11 itu program yang beda: nada level, navigasi, dan perintah yang cuma baca jalan di sana, tapi perintah yang ngubah teks nggak.
- VS Code cuma ngasih sebagian isi file ke screen reader, jadi levelnya bisa salah di sana. VS Code nggak aktif secara default.
- Outline dan lompat per fungsi nyari deklarasi pakai pola, bukan parser lengkap. Gaya penulisan kode yang nggak biasa bisa kelewat.
- Langkah undo disimpan selama NVDA jalan: habis NVDA di-restart, atau kalau pengaturannya dimatiin, control+Z balik jadi undo bawaan Notepad yang cuma satu langkah.
- Error sintaks Python dicek pakai compiler Python sendiri (kodenya nggak dijalanin), yang cuma ngelaporin error pertama di satu file. Baris yang memang sengaja dikeluarin dari blok itu Python yang sah, jadi nggak dihitung masalah; kamu dengernya sebagai perubahan nada level.
- Kode di dalam string dikenali buat f-string Python, template literal JavaScript, dan \\( ) di Swift. Di string interpolasi bahasa lain, misalnya `$"{name}"` di C# atau `"${name}"` di Kotlin dan Dart, namanya dianggap teks: rename, daftar pemakaian, dan autocomplete ngelewatin nama di situ.
