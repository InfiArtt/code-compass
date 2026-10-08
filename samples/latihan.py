# Latihan Code Compass. Buka di Notepad, lalu coba hal-hal di bawah ini.
#
# Ctrl+Shift+Space (petunjuk parameter): taruh kursor di dalam kurung
#   pemanggilan fungsi, misalnya di "15000" atau "diskon=10" pada baris
#   hitung_total(...) di fungsi main, lalu tekan Ctrl+Shift+Space.
#   Code Compass membacakan parameternya dan argumen keberapa yang kamu isi.
#   Coba juga di dalam Toko("Toko Rafli", ...) dan toko.tambah_barang(...).
# Ctrl+Space: ketik "hit" di baris kosong, lalu Ctrl+Space berkali-kali.
# F12: kursor di nama fungsi yang dipanggil, misalnya "hitung_total",
#   lompat ke deklarasinya. Ctrl+Alt+Backspace untuk kembali.
# Shift+F12: daftar semua baris yang memakai nama itu.
# F2: ganti nama, misalnya "harga" di fungsi hitung_total.
# Alt+PageDown / Alt+PageUp: pindah per fungsi. Alt+Panah kiri: ke induknya.
# Ctrl+Shift+O: outline. NVDA+Shift+K lalu F: silsilah fungsi di kursor.
# Ctrl+Alt+K: pasang bookmark, Ctrl+Alt+L / Ctrl+Alt+J: lompat antar bookmark.
# NVDA+Shift+K lalu Shift+T: daftar catatan to-do dan fixme di komentar.
# Ctrl+F5: jalankan file ini. Ctrl+S: simpan dan cek masalah.
# Mau coba suara error? Hapus satu tanda ")" di mana saja, tunggu sedetik.


def hitung_total(harga, jumlah, diskon=0):
    """Harga total setelah diskon (dalam persen)."""
    kotor = harga * jumlah
    potongan = kotor * diskon / 100
    return kotor - potongan


def format_rupiah(angka, pakai_simbol=True):
    """Angka jadi teks rupiah, misalnya 45000 -> "Rp45.000"."""
    teks = f"{int(angka):,}".replace(",", ".")
    return f"Rp{teks}" if pakai_simbol else teks


def hitung_pajak(harga, persen=11):
    """Pajak dari harga, misalnya PPN 11 persen."""
    return harga * persen / 100


class Barang:
    def __init__(self, nama, harga, stok=1):
        self.nama = nama
        self.harga = harga
        self.stok = stok

    def tersedia(self):
        return self.stok > 0


class Toko:
    """Toko kecil dengan daftar barang."""

    def __init__(self, nama, kota, pemilik="Rafli"):
        self.nama = nama
        self.kota = kota
        self.pemilik = pemilik
        self.barang = []

    def tambah_barang(self, nama, harga, stok=1):
        barang = Barang(nama, harga, stok)
        self.barang.append(barang)
        return barang

    def cari(self, kata, hanya_tersedia=False):
        hasil = []
        for barang in self.barang:
            if kata.lower() in barang.nama.lower():
                if hanya_tersedia and not barang.tersedia():
                    continue
                hasil.append(barang)
        return hasil

    def laporan(self):
        # TODO: urutkan barang dari yang paling mahal
        baris = [f"{self.nama} di {self.kota}, pemilik {self.pemilik}"]
        for nomor, barang in enumerate(self.barang, start=1):
            status = "ada" if barang.tersedia() else "habis"
            baris.append(f"  {nomor}. {barang.nama}: {format_rupiah(barang.harga)} ({status})")
        return "\n".join(baris)


def bagi_rata(total, orang):
    """Bagi total ke beberapa orang; orang tidak boleh nol."""
    try:
        return total / orang
    except ZeroDivisionError:
        # FIXME: beri tahu pengguna dengan pesan yang lebih jelas
        return 0


def main():
    toko = Toko("Toko Rafli", "Bandung", pemilik="Rafli")
    toko.tambah_barang("Kopi Arabika", 45000, stok=3)
    toko.tambah_barang("Teh Melati", 22000, stok=5)
    toko.tambah_barang("Gula Aren", 15000, stok=0)

    print(toko.laporan())
    print()

    total = hitung_total(15000, 3, diskon=10)
    print("Total belanja:", format_rupiah(total))
    print("Per orang:", format_rupiah(bagi_rata(total, 2)))

    for barang in toko.cari("te", hanya_tersedia=True):
        print("Ketemu:", barang.nama)

    # Hapus tanda # di baris bawah untuk mencoba error saat dijalankan (Ctrl+F5),
    # lalu tekan F8 untuk lompat ke baris error-nya.
    # print(hitung_total(10000, "dua"))


if __name__ == "__main__":
    main()
