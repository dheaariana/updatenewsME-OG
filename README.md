# Dashboard Harga Komoditas

Web Streamlit untuk Nikel, Brent Oil, Coal, dan Natural Gas. Harga dan persentase perubahan berasal dari Trading Economics API. Low–High 1Y dihitung dari nilai Low dan High historis selama 365 hari terakhir. Kolom Reason dan link berita perlu diisi setelah ditinjau. Catatan ICP merupakan isian bulanan terpisah.

## Cara memakai

1. Ekstrak ZIP ini dan unggah `app.py` serta `requirements.txt` ke GitHub.
2. Buat aplikasi baru di Streamlit Community Cloud, pilih repositori itu dan `app.py` sebagai main file.
3. Pada **App settings → Secrets**, masukkan:

   ```toml
   TRADING_ECONOMICS_API_KEY = "ISI_API_KEY_ANDA"
   ```

4. Buka webnya, tekan **Ambil data terbaru**, isi Reason dan link berita, lalu unduh PNG atau CSV.

API key Trading Economics diperoleh melalui paket aksesnya. Jangan menaruh API key di GitHub. Jika paket API tidak memuat data historis setahun, kolom Low–High ditampilkan `—` dan aplikasi tetap dapat menampilkan harga terkini. Cocokkan jenis kontrak, unit, dan waktu data dengan laman sumber sebelum memakai laporan.

Catatan ICP pada versi ini belum tersimpan permanen atau masuk ke PNG; isian tersedia sebagai tempat pengecekan data bulanan. Reason disimpan selama sesi browser Streamlit masih aktif.
