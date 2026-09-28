# Dashboard komoditas gratis (Streamlit)

Unggah `app.py` dan `requirements.txt` ke GitHub, lalu deploy `app.py` di Streamlit Community Cloud. Tidak memerlukan API key atau Streamlit Secrets.

Klik **Ambil dari halaman publik**. Program membaca tabel komoditas publik Trading Economics untuk harga, perubahan harian dan bulanan; lalu mencoba membaca perubahan tahunan pada halaman masing-masing komoditas. **Periksa angka, jenis instrumen, tanggal, dan unit** karena halaman publik bisa berubah atau menolak pembacaan otomatis. Jika pembacaan gagal, tabel tetap bisa diedit manual. Rentang 1 tahun, alasan harga, dan link berita dilengkapi manual. ICP diisi dari publikasi bulanan Kementerian ESDM.

Tabel utama dan hasil **Unduh PNG** mengikuti format contoh: empat komoditas, perubahan Day/Month/Year, Reason, indikator Low–High 1 Year, dan ICP. Klik bagian **Edit angka, rentang 1 tahun, alasan dan tautan berita** untuk mengubah nilainya. Apabila kolom pada halaman sumber berubah, aplikasi membiarkan data yang tidak dapat dikenali kosong supaya tidak salah melabeli persentase sebagai tanggal.

Format versi ini mengikuti gambar terbaru: judul **Changes in Commodity Prices**, catatan waktu laporan GMT+7, serta kolom Notes untuk ICP Lalang dan Pendalian. Waktu laporan dan tanggal harga merupakan hal yang berbeda; tanggal sumber tiap harga tampil di bawah angkanya.

Versi berikutnya mencoba membaca **Yearly** dan ringkasan pasar dari masing-masing halaman detail Trading Economics. Ringkasan TE ditampilkan sebagai konteks pasar berbahasa Inggris, bisa diedit ke Bahasa Indonesia setelah ditinjau. Jika Yearly gagal dibaca, aplikasi menandainya kosong; jangan menyalin angka dari tanggal lain. Low–High memiliki nilai awal dari gambar contoh 28 September 2026 dan menampilkan tanggal acuannya. ICP Lalang 93,15 dan Pendalian 90,95 merupakan nilai awal contoh periode Agustus 2026, bukan pembaruan otomatis. Ubah nilai awal saat sumber baru terbit.

Ini bukan API Trading Economics. Program mengirim paling banyak lima permintaan halaman saat tombol ditekan; tanpa penjadwalan otomatis, tanpa bypass proteksi akses. Jika situs tidak lagi membolehkan pembacaan, gunakan versi lokal `Dashboard_Komoditas_Tanpa_API.zip`.

## Ketepatan waktu harga

Tekan **Ambil dari halaman publik** setiap kali membuat laporan. Tanggal sumber ditampilkan per komoditas pada tabel dan PNG. Jika tanggal tidak dapat dibaca atau sudah lebih dari satu hari perdagangan, unduhan PNG dinonaktifkan sampai pengguna memeriksa harga dan tanggal pada halaman sumber serta mencentang konfirmasi. Tanggal yang diedit manual memakai format `YYYY-MM-DD`. Waktu pembuatan PNG bukan waktu pembaruan harga. Harga dari halaman publik dapat tertunda atau berbeda pada saat pembacaan karena pasar dan halaman sumber terus bergerak.
