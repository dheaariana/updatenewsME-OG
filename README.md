# Dashboard Komoditas v21

Jalankan `pip install -r requirements.txt` lalu `streamlit run app.py`.
Untuk Streamlit Community Cloud: unggah app.py dan requirements.txt ke GitHub, pilih app.py sebagai main file. Tidak memerlukan API key.

1. Klik Ambil dari halaman publik. Harga, persentase perubahan, dan Reason diambil jika halaman TE dapat dibaca. Scraping tidak menjamin data real time; periksa tanggal sumber dan status.
2. Buka Isi Low–High. Isi Low 1Y dan High 1Y terverifikasi dari seri TE yang sama untuk periode 1 Year. Label sumbu grafik bukan angka minimum/maksimum yang pasti. Jangan menebak angkanya.
3. Isi Tanggal cek Low-High format YYYY-MM-DD, sesuai hari pemeriksaan. Cek ulang tiap laporan harian.
4. Low–High tidak tertimpa saat klik Ambil dari halaman publik. Grafik hanya ditampilkan jika harga berada dalam rentang valid. Jika harga keluar, periksa ulang rentang; aplikasi tidak mengubah High mengikuti Latest Price.
5. Unduh pengaturan Low–High sebagai JSON untuk dipakai ulang setelah sesi berakhir. Unggah kembali dan klik Terapkan pengaturan.
6. Unduh PNG setelah rentang valid dan tanggal cek hari ini terisi untuk semua komoditas. CSV tetap dapat diunduh untuk penyimpanan.

Kolom Low–High memakai input manual TE; tidak memakai World Bank. Harga terbaru dan Reason tetap bersumber dari halaman publik. Ini pembaruan sebagian otomatis, bukan akses API historis gratis. ICP merupakan contoh yang perlu diedit.
