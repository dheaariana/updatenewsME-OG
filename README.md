# Dashboard komoditas gratis (Streamlit)

Unggah `app.py` dan `requirements.txt` ke GitHub, lalu deploy `app.py` di Streamlit Community Cloud. Tidak memerlukan API key atau Streamlit Secrets.

Saat halaman dibuka ulang, aplikasi langsung membaca data publik. Klik **🔄 Ambil dari halaman publik** untuk memaksa pembacaan baru tanpa membuka ulang halaman. Aplikasi membaca harga dan perubahan dari header halaman detail Trading Economics; teks konteks pasar juga dibaca ulang, tetapi bisa tetap sama bila Trading Economics belum mengubahnya. Tabel edit direset setelah pembacaan berhasil agar nilai lama tidak menimpa nilai baru. Aplikasi kemudian mengunduh berkas **World Bank Pink Sheet bulanan** dan menghitung nilai terendah serta tertinggi dari **12 rata-rata harga bulanan terbaru** untuk Nikel, Brent, Coal Australia, dan Natural Gas AS.

Harga dan Day/Month/Year dari halaman detail dipakai bersama hanya bila keempatnya lengkap dan tanggal pembaruan pada bagian Stats dapat dibaca. Jika halaman detail tidak lengkap, angka tabel daftar tetap digunakan dan status memperingatkan pengguna. Jika harga daftar dan detail berbeda pada tanggal yang sama, status meminta pemeriksaan manual sebelum PNG diunduh. Harga pada halaman publik dapat berubah di tengah proses pembacaan beberapa halaman; pemeriksaan ini tidak menjamin kesamaan detik demi detik.

Rentang tersebut **bukan** titik Low–High 52 minggu pada grafik harian Trading Economics. Instrumen, metode, dan waktunya dapat berbeda. Judul tabel disederhanakan menjadi "Low–High (1 Year)"; sumber dan metode perhitungan tetap dijelaskan pada keterangan aplikasi. Harga harian memiliki tanggal sumber tersendiri. Jika file gagal dibaca atau 12 bulan tidak lengkap, kolom rentang dikosongkan dan peringatan muncul. Aplikasi tidak menyamarkan angka contoh sebagai pembaruan.

ICP Lalang dan Pendalian masih nilai awal dari contoh Agustus 2026. Perbarui angka dan periode setelah publikasi ESDM terbaru. Ringkasan pasar dapat diedit setelah ditinjau; alasan yang diedit manual dipertahankan pada pembacaan berikutnya.

**Reason** diterjemahkan otomatis dari ringkasan halaman detail Trading Economics ke bahasa Indonesia melalui layanan terjemahan MyMemory (tanpa API key). Teks ringkasan publik dikirim ke layanan tersebut, lalu hasil untuk teks yang sama disimpan sementara agar tidak menghabiskan kuota tiap refresh. Tautan penjelasan asli bisa diklik pada tabel. Jika layanan terjemahan gagal atau kuotanya habis, aplikasi memberi status "Terjemahan belum tersedia" dan tautan sumber tetap ada. Tinjau terjemahan sebelum memakai laporan resmi; jika Trading Economics belum mengubah ringkasannya, Reason juga tidak berubah meskipun harga bergerak.

Tabel dan hasil PNG menampilkan empat komoditas, perubahan harga, Reason, rentang bulanan 12 bulan, dan ICP. Harga yang kosong atau tanggal yang terlalu lama akan menonaktifkan unduhan PNG hingga pengguna memeriksa dan mengonfirmasi. Harga publik dapat tertunda; waktu membuat laporan tidak sama dengan waktu harga diperbarui.

Sumber rentang: https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet

Sumber harga harian: https://tradingeconomics.com/commodities
