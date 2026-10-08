# Dashboard Komoditas v27

Upload app.py, report.py, dan requirements.txt ke GitHub. Main file Streamlit: app.py. Tidak membutuhkan API key.
Untuk lokal: pip install -r requirements.txt lalu streamlit run app.py.

Tabel mengikuti referensi: Commodity, Latest Price ($/unit), %Chg Day/Month/Year, Reason rata tengah, Low–High (1 Year) berupa batang dengan harga terbaru. Harga Nikel tetap USD/ton dari sumber, tidak dibagi 1.000. Header Updated adalah waktu pembacaan aplikasi; tanggal kutipan harga tetap ada di setiap baris.

Harga dan ringkasan diambil dari halaman publik TE jika tersedia. Tidak menjamin harga real time. Low–High TE tetap manual; isi angka ekstrem yang terverifikasi untuk seri yang sama. Rentang kosong atau harga di luar rentang ditandai, tidak dibuatkan data. JSON Low–High dapat disimpan dan dipulihkan.

ICP berbentuk tabel bulanan Lalang/Pendalian. Angka Jan–Aug 2026 disalin dari gambar pengguna, bukan hasil scraping atau verifikasi baru. Sep–Dec kosong. Edit angka, tahun, Notes, dan pilih bulan yang ditampilkan. Unduh CSV ICP untuk simpan, lalu unggah kembali untuk pulihkan.

PNG dan CSV tetap dapat diunduh. Reason tidak ditambahkan asumsi atau angka statis dari gambar. Jika scraping/terjemahan gagal, edit Reason setelah memeriksa sumber. Pengaturan tersimpan selama sesi; gunakan JSON/CSV untuk sesi baru.
