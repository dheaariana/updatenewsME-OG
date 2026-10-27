# Dashboard Komoditas v27

Upload app.py, report.py, dan requirements.txt ke GitHub. Main file Streamlit: app.py. Tidak membutuhkan API key.
Untuk lokal: pip install -r requirements.txt lalu streamlit run app.py.

Tabel mengikuti referensi: Commodity, Latest Price ($/unit), %Chg Day/Month/Year, Reason rata tengah, Low–High (1 Year) berupa batang dengan harga terbaru. Harga Nikel tetap USD/ton dari sumber, tidak dibagi 1.000. Header Updated adalah waktu pembacaan aplikasi; tanggal kutipan harga tetap ada di setiap baris.

Harga dan ringkasan diambil dari halaman publik TE jika tersedia. Tidak menjamin harga real time. Low–High TE tetap manual; isi angka ekstrem yang terverifikasi untuk seri yang sama. Rentang kosong atau harga di luar rentang ditandai, tidak dibuatkan data. JSON Low–High dapat disimpan dan dipulihkan.

ICP berbentuk tabel bulanan Lalang/Pendalian. Angka Jan–Aug 2026 disalin dari gambar pengguna, bukan hasil scraping atau verifikasi baru. Sep–Dec kosong. Edit angka, tahun, Notes, dan pilih bulan yang ditampilkan. Unduh CSV ICP untuk simpan, lalu unggah kembali untuk pulihkan.

PNG dan CSV tetap dapat diunduh. Reason tidak ditambahkan asumsi atau angka statis dari gambar. Jika scraping/terjemahan gagal, edit Reason setelah memeriksa sumber. Pengaturan tersimpan selama sesi; gunakan JSON/CSV untuk sesi baru.


Perbaikan v30: penjelasan sumber dipecah menjadi permintaan terjemahan maksimal 450 byte UTF-8. Terjemahan yang berhasil disimpan dalam cache. Bila layanan gagal/kuota habis, Reason menampilkan teks asli sumber dalam bahasa Inggris; status terjemahan dapat dilihat pada detail sumber. Klik Ambil dari halaman publik untuk mencoba kembali. Tidak ada penyebab pergerakan harga yang dikarang.


V31: setiap klik Ambil dari halaman publik membaca ulang Summary halaman detail TE dan mengganti Reason, termasuk teks yang sebelumnya diedit manual. Pilihan maksimal dua kalimat dengan faktor pasar diambil dari sumber lalu diterjemahkan ke bahasa Indonesia. Harga dan narasi TE dapat mempunyai waktu pembaruan berbeda; aplikasi tidak menyimpulkan alasan baru dari persentase harga. Jika terjemahan gagal, tampilkan status singkat bahasa Indonesia dan tautan asli, bukan alasan buatan. Low–High manual tetap dipertahankan.


V33: bulan ICP dengan setidaknya satu harga positif otomatis tampil di laporan/PNG. Upload CSV menggunakan buffer baru dan revisi widget sehingga tabel hasil pemulihan tidak ditimpa editor lama. Setelah mengedit, tekan Enter. Unduh CSV untuk menyimpan isian lintas sesi.


V34: isi Tanggal Low dan Tanggal High manual sebagai YYYY-MM-DD pada editor. Keduanya ditampilkan di bawah nilai Low dan High pada laporan dan PNG; disimpan dalam JSON Low–High. JSON lama tetap dapat diunggah. Tanggal tidak otomatis didapat dari Trading Economics, cek sebelum digunakan.


V35: pastikan app.py dan report.py versi 35 diunggah bersama. Tanggal tetap terlihat jika grafik tidak dapat ditampilkan karena harga di luar batas. Harga dan tanggal Low–High tetap perlu dicocokkan dengan sumber.
