# Dashboard komoditas gratis (Streamlit)

Unggah `app.py` dan `requirements.txt` ke GitHub, lalu deploy `app.py` di Streamlit Community Cloud. Tidak memerlukan API key atau Streamlit Secrets.

Klik **Ambil dari halaman publik**. Program membaca tabel komoditas publik Trading Economics untuk harga, perubahan harian dan bulanan; lalu mencoba membaca perubahan tahunan pada halaman masing-masing komoditas. **Periksa angka, jenis instrumen, tanggal, dan unit** karena halaman publik bisa berubah atau menolak pembacaan otomatis. Jika pembacaan gagal, tabel tetap bisa diedit manual. Rentang 1 tahun, alasan harga, dan link berita dilengkapi manual. ICP diisi dari publikasi bulanan Kementerian ESDM.

Tabel utama dan hasil **Unduh PNG** mengikuti format contoh: empat komoditas, perubahan Day/Month/Year, Reason, indikator Low–High 1 Year, dan ICP. Klik bagian **Edit angka, rentang 1 tahun, alasan dan tautan berita** untuk mengubah nilainya. Apabila kolom pada halaman sumber berubah, aplikasi membiarkan data yang tidak dapat dikenali kosong supaya tidak salah melabeli persentase sebagai tanggal.

Ini bukan API Trading Economics. Program mengirim paling banyak lima permintaan halaman saat tombol ditekan; tanpa penjadwalan otomatis, tanpa bypass proteksi akses. Jika situs tidak lagi membolehkan pembacaan, gunakan versi lokal `Dashboard_Komoditas_Tanpa_API.zip`.
