"""Dashboard gratis: baca halaman publik Trading Economics jika tersedia."""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from html import escape, unescape
import re
from textwrap import fill
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import json
import math
import requests
from bs4 import BeautifulSoup
import streamlit as st
from report import preview, png, MONTHS

st.set_page_config(page_title="Update Komoditas", layout="wide")
st.title("Perubahan Harga Komoditas")
st.caption("Tabel laporan harian · Sumber harga: halaman publik Trading Economics")

URL = "https://tradingeconomics.com"
NAMES = {
    "Nikel": "/commodity/nickel",
    "Brent Oil": "/commodity/brent-crude-oil",
    "Coal": "/commodity/coal",
    "Natural Gas": "/commodity/natural-gas",
}
LABELS = {"Nikel": "nickel", "Brent Oil": "brent oil", "Coal": "coal", "Natural Gas": "natural gas"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal commodity report)"}
COLS = ["Komoditas", "Latest Price", "Unit", "Day %", "Month %", "Year %",
        "Low 1Y", "High 1Y", "Reason", "Link berita", "Waktu sumber", "Acuan rentang", "Tanggal cek Low-High", "Status"]
TODAY = datetime.now(ZoneInfo("Asia/Jakarta")).date()


def quote_date(raw):
    """Tanggal kutipan; format TE pada tabel biasanya Sep/25."""
    text = str(raw or "").strip()
    if not text or "%" in text:
        return None
    for pattern in ("%Y-%m-%d", "%b/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    try:
        month_day = datetime.strptime(text, "%b/%d").date()
        parsed = month_day.replace(year=TODAY.year)
        return parsed if parsed <= TODAY + timedelta(days=1) else parsed.replace(year=TODAY.year-1)
    except ValueError:
        return None


def trading_days_old(when):
    if when is None or when > TODAY:
        return None
    return sum((when + timedelta(days=i)).weekday() < 5 for i in range(1, (TODAY-when).days+1))


def is_fresh(raw):
    age = trading_days_old(quote_date(raw))
    return age is not None and age <= 1


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    if "captcha" in response.url.lower():
        raise ValueError("Halaman meminta verifikasi browser")
    return BeautifulSoup(response.text, "html.parser")


def clean_num(text):
    match = re.search(r"[-+]?\d[\d,.]*", str(text))
    return match.group(0).replace(",", "") if match else ""


def detail_fields(text, label):
    """Ambil Yearly dan ringkasan beratribusi dari halaman detail publik."""
    yearly = re.search(r"\bYearly\s+([+-]?\d+(?:\.\d+)?)%", text, re.I)
    summary = re.search(rf"{re.escape(LABELS[label])}\s*-\s*Summary\s+(.+?)\s+{re.escape(LABELS[label])}\s*-\s*Stats", text, re.I | re.S)
    paragraph = re.sub(r"\s+", " ", summary.group(1)).strip() if summary else ""
    # Potong pada akhir kalimat agar tidak ada fragmen yang tampak sebagai kesimpulan.
    if len(paragraph) > 330:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        paragraph = ""
        for sentence in sentences:
            if len(paragraph) + len(sentence) > 330:
                break
            paragraph += (" " if paragraph else "") + sentence
    return (yearly.group(1) if yearly else "", paragraph)


def detail_market_fields(soup):
    """Angka pada header halaman detail, dengan presisi sesuai yang diterbitkan."""
    grid = soup.select_one("#market_stats_grid")
    if not grid:
        return {}
    result = {}
    last = grid.select_one("#market_last")
    day = grid.select_one("#market_daily_Pchg")
    if last:
        result["Latest Price"] = clean_num(last.get_text(" ", strip=True))
    if day:
        result["Day %"] = clean_num(day.get_text(" ", strip=True))
    for block in grid.select(".market-header-value"):
        header = block.select_one(".te-market-header")
        if not header:
            continue
        name = header.get_text(" ", strip=True).lower()
        key = {"monthly": "Month %", "yearly": "Year %"}.get(name)
        if key:
            match = re.search(r"[+-]?\d+(?:\.\d+)?%", block.get_text(" ", strip=True))
            if match:
                result[key] = clean_num(match.group(0))
    return result


def detail_update_date(text, label):
    """Tanggal *kutipan harga* pada Stats, bukan tanggal halaman terakhir diedit."""
    match = re.search(
        rf"{re.escape(LABELS[label])}\s*-\s*Stats\b(.+?){re.escape(LABELS[label])}\s*-\s*Forecast\b",
        text, re.I | re.S,
    )
    if not match:
        return None
    stats = match.group(1).split("Historically", 1)[0]
    dates = re.findall(r"\b(?:rose|fell|climbed|dropped|declined|increased|decreased|traded|stood)\b.{0,120}?\bon\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(?:of\s+)?\d{4})", stats, re.I)
    if not dates:
        return None
    normalized = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", dates[0], flags=re.I).replace(",", "")
    normalized = re.sub(r"\s+of\s+", " ", normalized, flags=re.I)
    try:
        return datetime.strptime(normalized, "%B %d %Y").date()
    except ValueError:
        return None


RANGE_FIELDS = ("Komoditas", "Low 1Y", "High 1Y", "Tanggal cek Low-High")


def setting_text(value):
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "nat") else text


def export_ranges(frame):
    return json.dumps([{key: setting_text(row.get(key, "")) for key in RANGE_FIELDS}
                       for _, row in frame.iterrows()], ensure_ascii=False, indent=2)


def restore_ranges(frame, records):
    if not isinstance(records, list):
        raise ValueError("Gunakan file low_high_te.json yang diunduh dari aplikasi")
    restored = frame.copy()
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Setiap baris pengaturan harus berupa objek")
        label = setting_text(record.get("Komoditas"))
        if label not in NAMES or label in seen:
            raise ValueError(f"Komoditas tidak dikenal atau berulang: {label}")
        seen.add(label)
        values = {key: setting_text(record.get(key)) for key in RANGE_FIELDS[1:]}
        for key in ("Low 1Y", "High 1Y"):
            if values[key]:
                try:
                    number = float(values[key].replace(",", ""))
                except ValueError:
                    raise ValueError(f"{label}: {key} harus berupa angka") from None
                if not math.isfinite(number) or number <= 0:
                    raise ValueError(f"{label}: {key} harus berupa angka positif")
                values[key] = str(number)
        if values["Low 1Y"] and values["High 1Y"] and float(values["Low 1Y"]) >= float(values["High 1Y"]):
            raise ValueError(f"{label}: Low harus lebih kecil dari High")
        date_text = values["Tanggal cek Low-High"]
        if date_text:
            try:
                checked = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"{label}: gunakan tanggal YYYY-MM-DD") from None
            if checked > TODAY:
                raise ValueError(f"{label}: tanggal cek tidak boleh di masa depan")
            values["Tanggal cek Low-High"] = checked.isoformat()
        mask = restored["Komoditas"] == label
        for key, value in values.items():
            restored.loc[mask, key] = value
    return restored


def compact_dollars(value):
    return re.sub(r"\$\s+(?=\d)", "$", str(value or ""))


def translation_chunks(text, limit=450):
    """Batas layanan dihitung dalam byte UTF-8, bukan panjang paragraf."""
    chunks, current = [], ""
    for word in str(text).split():
        candidate = (current + " " + word).strip()
        if len(candidate.encode("utf-8")) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # Pecah token panjang juga agar setiap permintaan memenuhi batas.
        for char in word:
            if len((current + char).encode("utf-8")) > limit:
                chunks.append(current)
                current = ""
            current += char
    if current:
        chunks.append(current)
    return chunks


@st.cache_data(ttl=86400, show_spinner=False)
def translate_chunk(english):
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": english, "langpair": "en|id"}, timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    translated = unescape(str(payload.get("responseData", {}).get("translatedText", ""))).strip()
    if payload.get("quotaFinished") or str(payload.get("responseStatus")) != "200" or not translated or translated.casefold() == english.casefold():
        raise ValueError("Layanan terjemahan tidak memberikan hasil bahasa Indonesia")
    return compact_dollars(translated)


def translate_summary(english):
    # Kesalahan tidak disimpan dalam cache; klik ambil data akan mencoba lagi.
    return " ".join(translate_chunk(chunk) for chunk in translation_chunks(english))


def collect_public():
    """Permintaan rendah: satu halaman daftar dan satu halaman per komoditas."""
    soup = fetch_html(URL + "/commodities")
    data = {}
    for label, path in NAMES.items():
        row = {
            "Komoditas": label, "Latest Price": "", "Unit": "",
            "Day %": "", "Month %": "", "Year %": "", "Low 1Y": "",
            "High 1Y": "", "Reason": "", "Link berita": "",
            "Waktu sumber": "", "Acuan rentang": "", "Status": "Belum ditemukan",
        }
        anchor = soup.find("a", href=lambda h: bool(h and h.lower().rstrip("/") == path))
        tr = anchor.find_parent("tr") if anchor else None
        if tr:
            cells = tr.find_all("td", recursive=False)
            # Baca judul kolom pada tabel yang sama. Posisi kolom dapat berubah.
            table = tr.find_parent("table")
            header_row = table.find("tr") if table else None
            headers = [h.get_text(" ", strip=True).lower() for h in header_row.find_all(["th", "td"], recursive=False)] if header_row else []
            def cell_for(*names):
                for j, title in enumerate(headers):
                    if any(n in title for n in names) and j < len(cells):
                        return cells[j].get_text(" ", strip=True)
                return ""
            price = cell_for("price")
            day = cell_for("%chg", "% chg", "daily", "day %")
            month = cell_for("monthly", "month %")
            year = cell_for("yearly", "year %")
            date = cell_for("date")
            if price and day and month:
                row["Latest Price"] = clean_num(price)
                row["Day %"] = clean_num(day)
                row["Month %"] = clean_num(month)
                row["Year %"] = clean_num(year) if "%" in year else ""
                parsed = quote_date(date)
                row["Waktu sumber"] = parsed.isoformat() if parsed else ""
                # Hilangkan nama instrumen; pertahankan satuan sebagaimana tampak di halaman.
                first = cells[0].get_text(" ", strip=True)
                row["Unit"] = first.replace(anchor.get_text(" ", strip=True), "", 1).strip()
                row["Status"] = "Tanggal terverifikasi" if is_fresh(row["Waktu sumber"]) else "Tanggal usang/tidak terbaca"
        data[label] = row

    summaries = {}
    for label, path in NAMES.items():
        try:
            detail = fetch_html(URL + path)
            text = detail.get_text(" ", strip=True)
            live_fields = detail_market_fields(detail)
            required = ("Latest Price", "Day %", "Month %", "Year %")
            if all(live_fields.get(k) for k in required):
                detail_date = detail_update_date(text, label)
                if detail_date:
                    list_price = data[label]["Latest Price"]
                    list_date = quote_date(data[label]["Waktu sumber"])
                    data[label].update(live_fields)
                    data[label]["Waktu sumber"] = detail_date.isoformat()
                    if list_price and list_date == detail_date and abs(float(list_price) - float(live_fields["Latest Price"])) > max(0.01, float(live_fields["Latest Price"]) * 0.0001):
                        data[label]["Status"] = "Harga daftar/detail berbeda; cek sumber"
                    else:
                        if detail_date < TODAY:
                            data[label]["Status"] = "Kutipan terakhir " + detail_date.strftime("%d/%m/%Y") + "; belum ada harga baru"
                        else:
                            data[label]["Status"] = "Detail terverifikasi" if is_fresh(data[label]["Waktu sumber"]) else "Tanggal detail usang"
                else:
                    data[label]["Status"] = "Tanggal detail tidak terbaca; memakai daftar"
            else:
                data[label]["Status"] += "; detail tidak lengkap"
            yearly, summary = detail_fields(text, label)
            if yearly and not data[label]["Year %"] and not data[label]["Latest Price"]:
                data[label]["Year %"] = yearly
            if summary:
                summaries[label] = summary
                data[label]["Link berita"] = URL + path
        except (requests.RequestException, ValueError):
            # Angka dari halaman daftar tetap ditampilkan bila halaman detail gagal.
            pass
    if summaries:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {label: pool.submit(translate_summary, summary) for label, summary in summaries.items()}
            for label, job in jobs.items():
                try:
                    data[label]["Reason"] = job.result()
                except (requests.RequestException, ValueError, KeyError):
                    data[label]["Reason"] = compact_dollars(summaries[label])
                    data[label]["Status"] += "; terjemahan gagal, penjelasan asli ditampilkan"
    for label in NAMES:
        if not data[label]["Reason"]:
            data[label]["Reason"] = "Penjelasan sumber belum berhasil dibaca; periksa halaman komoditas."
            data[label]["Link berita"] = URL + NAMES[label]
    return pd.DataFrame(data.values(), columns=COLS)


def fmt(value, signed=False):
    try:
        number = float(str(value).replace(",", ""))
        return f"{number:+.2f}%" if signed else f"{number:,.2f}"
    except (TypeError, ValueError):
        return "—"


def fmt_price(value, commodity):
    try:
        digits = {"Nikel": 2, "Brent Oil": 3, "Coal": 2, "Natural Gas": 4}[commodity]
        return f"{float(str(value).replace(',', '')):,.{digits}f}"
    except (TypeError, ValueError, KeyError):
        return "—"


def fmt_range(value, commodity):
    try:
        return f"{float(str(value).replace(',', '')):,.{3 if commodity == 'Natural Gas' else 2}f}"
    except (TypeError, ValueError):
        return "—"


first_load = "frame" not in st.session_state
if first_load:
    st.session_state.frame = pd.DataFrame([{
        "Komoditas": name, "Latest Price": "", "Unit": "", "Day %": "", "Month %": "", "Year %": "",
        "Low 1Y": "", "High 1Y": "",
        "Reason": "", "Link berita": "", "Waktu sumber": "", "Acuan rentang": "TE 1 Year · input manual", "Tanggal cek Low-High": "", "Status": "Belum diambil"
    } for name in NAMES], columns=COLS)
    st.session_state.editor_revision = 0
    st.session_state.auto_reason = {}
if "editor_revision" not in st.session_state:
    st.session_state.editor_revision = 0
if "auto_reason" not in st.session_state:
    st.session_state.auto_reason = {}

refresh_clicked = st.button("🔄 Ambil dari halaman publik")
if first_load or refresh_clicked:
    old = st.session_state.frame.set_index("Komoditas")
    try:
        new = collect_public()
        generated_reason = {record["Komoditas"]: record["Reason"] for _, record in new.iterrows()}
        for i, record in new.iterrows():
            label = record["Komoditas"]
            for field in ("Low 1Y", "High 1Y", "Acuan rentang", "Tanggal cek Low-High"):
                new.at[i, field] = old.at[label, field]
            old_reason = str(old.at[label, "Reason"] or "")
            auto_prefixes = ("Konteks pasar TE:", "Ringkasan TE (terjemahan otomatis):", "Terjemahan belum tersedia.", "Contoh 28/09/2026:")
            if old_reason and old_reason != st.session_state.auto_reason.get(label) and not old_reason.startswith(auto_prefixes):
                new.at[i, "Reason"] = old.at[label, "Reason"]
                new.at[i, "Link berita"] = old.at[label, "Link berita"]
            # Jangan tampilkan harga lama seolah hasil pembacaan baru.
        st.session_state.frame = new
        st.session_state.auto_reason = generated_reason
        st.session_state.editor_revision += 1
        st.session_state.last_refresh = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M GMT+7")
    except (requests.RequestException, ValueError) as exc:
        st.warning(f"Halaman publik tidak dapat dibaca sekarang: {exc}. Isi tabel secara manual.")

if "last_refresh" in st.session_state:
    st.caption(f"Terakhir dibaca aplikasi: {st.session_state.last_refresh}. Tanggal harga per komoditas tertera di tabel.")

with st.expander("✏️ Isi Low–High TE 1 Year, tanggal cek, dan edit laporan"):
    edited = st.data_editor(
        st.session_state.frame, hide_index=True, use_container_width=True,
        disabled=["Komoditas", "Status", "Acuan rentang"],
        column_config={"Reason": st.column_config.TextColumn("Reason", width="large"),
                       "Link berita": st.column_config.LinkColumn("Link berita"),
                       "Tanggal cek Low-High": st.column_config.TextColumn("Tanggal cek Low-High (YYYY-MM-DD)")},
        key=f"editor_{st.session_state.editor_revision}",
    )
    edited["Reason"] = edited["Reason"].map(compact_dollars)
    st.session_state.frame = edited
    st.caption("Isi Low 1Y dan High 1Y dari angka terverifikasi pada seri TE yang sama, periode 1 Year; jangan memakai label sumbu grafik sebagai titik ekstrem. Isi tanggal cek dengan YYYY-MM-DD. Angka manual tetap tersimpan selama sesi meskipun harga diperbarui.")

if "icp_monthly" not in st.session_state:
    initial_icp = pd.DataFrame([
        {"Crude": "Lalang", "Notes": "Ref. untuk debitur a.n ITA", **dict(zip(MONTHS[:8], [67.67,72.43,105.28,121.72,109.84,87.97,85.48,93.15]))},
        {"Crude": "Pendalian", "Notes": "Ref. untuk debitur a.n APG West Kampar", **dict(zip(MONTHS[:8], [65.47,70.23,103.08,119.52,107.64,85.77,83.28,90.95]))}
    ])
    for month in MONTHS[8:]: initial_icp[month] = float("nan")
    st.session_state.icp_monthly = initial_icp
with st.expander("✏️ Edit ICP per bulan"):
    icp_year = st.number_input("Tahun ICP", min_value=2000, max_value=2100, value=2026, step=1)
    selected_months = st.multiselect("Bulan yang ditampilkan", MONTHS, default=MONTHS[:8])
    st.caption("Isian awal Januari–Agustus disalin dari gambar Anda, belum diverifikasi ulang terhadap rilis ESDM. Lengkapi bulan berikutnya saat tersedia.")
    icp_edited = st.data_editor(st.session_state.icp_monthly, hide_index=True, use_container_width=True,
        disabled=["Crude"], column_config={month: st.column_config.NumberColumn(month, min_value=0.0, format="%.2f") for month in MONTHS}, key="icp_editor")
    st.session_state.icp_monthly = icp_edited
    st.download_button("Unduh CSV ICP", icp_edited.to_csv(index=False).encode("utf-8-sig"), "icp_bulanan.csv", "text/csv")
    icp_upload = st.file_uploader("Pulihkan CSV ICP yang pernah disimpan", type=["csv"], key="icp_upload")
    if icp_upload is not None and st.button("Terapkan CSV ICP"):
        try:
            restored_icp = pd.read_csv(icp_upload).fillna("")
            if len(restored_icp) != 2 or list(restored_icp["Crude"]) != ["Lalang", "Pendalian"]:
                raise ValueError("Gunakan CSV ICP yang diunduh dari aplikasi")
            for month in MONTHS:
                restored_icp[month] = pd.to_numeric(restored_icp[month], errors="raise").replace("", float("nan"))
                if (restored_icp[month].dropna() < 0).any(): raise ValueError("Harga ICP harus positif")
            st.session_state.icp_monthly = restored_icp[["Crude", "Notes"] + MONTHS]
            del st.session_state["icp_editor"]
            st.rerun()
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"CSV ICP tidak dapat dipakai: {exc}")
icp_selected = icp_edited[["Crude", "Notes"] + [m for m in MONTHS if m in selected_months]]
updated = st.session_state.get("last_refresh", "belum dibaca")
st.caption("Updated menunjukkan waktu aplikasi membaca halaman; tanggal kutipan tiap harga tetap tertera. Low–High TE diisi manual.")
with st.expander("💾 Simpan / pulihkan Low–High"):
    st.download_button("Unduh pengaturan Low–High", export_ranges(edited), "low_high_te.json", "application/json")
    uploaded = st.file_uploader("Unggah pengaturan yang pernah disimpan", type=["json"])
    if uploaded is not None and st.button("Terapkan pengaturan"):
        try:
            records = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            restored = restore_ranges(edited, records)
            st.session_state.frame = restored
            st.session_state.editor_revision += 1
            st.session_state.range_upload_ok = True
            st.rerun()
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
            st.error(f"Pengaturan tidak dapat dipakai: {exc}")
    if st.session_state.pop("range_upload_ok", False):
        st.success("Pengaturan berhasil diterapkan. Angka kosong dapat dilengkapi melalui tabel edit.")

st.markdown("### Tampilan laporan")
st.markdown(preview(edited, icp_year, icp_selected, updated), unsafe_allow_html=True)
with st.expander("Sumber dan status pembacaan"):
    st.dataframe(edited[["Komoditas", "Waktu sumber", "Tanggal cek Low-High", "Acuan rentang", "Status", "Link berita"]], hide_index=True, use_container_width=True)

timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d")
missing_year = [str(row["Komoditas"]) for _,row in edited.iterrows() if not row["Year %"]]
if missing_year:
    st.warning("Year % belum terambil untuk: " + ", ".join(missing_year) + ". Isi setelah mencocokkan halaman detail sumber.")

st.download_button("⬇️ Unduh PNG", png(edited, icp_year, icp_selected, updated),
                   f"komoditas_{timestamp}.png", "image/png")
st.download_button("⬇️ Unduh CSV", edited.to_csv(index=False).encode("utf-8-sig"), f"komoditas_{timestamp}.csv", "text/csv")
