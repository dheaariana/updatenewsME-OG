"""Dashboard gratis: baca halaman publik Trading Economics jika tersedia."""
from datetime import datetime
from io import BytesIO
import re
from textwrap import fill
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="Update Komoditas", layout="wide")
st.title("Perubahan Harga Komoditas")
st.caption("Sumber: halaman publik Trading Economics · Tidak menggunakan API key")

URL = "https://tradingeconomics.com"
NAMES = {
    "Nikel": "/commodity/nickel",
    "Brent Oil": "/commodity/brent-crude-oil",
    "Coal": "/commodity/coal",
    "Natural Gas": "/commodity/natural-gas",
}
LABELS = {"Nikel": "nickel", "Brent Oil": "brent", "Coal": "coal", "Natural Gas": "natural gas"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal commodity report)"}
COLS = ["Komoditas", "Latest Price", "Unit", "Day %", "Month %", "Year %",
        "Low 1Y", "High 1Y", "Reason", "Link berita", "Waktu sumber", "Status"]


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    if "captcha" in response.url.lower():
        raise ValueError("Halaman meminta verifikasi browser")
    return BeautifulSoup(response.text, "html.parser")


def clean_num(text):
    match = re.search(r"[-+]?\d[\d,.]*", str(text))
    return match.group(0).replace(",", "") if match else ""


def signed_percent(phrase):
    """Persentase narasi berubah menjadi angka bertanda; ambigu => kosong."""
    value = re.search(r"(\d+(?:\.\d+)?)%", phrase)
    if not value:
        return ""
    before = phrase[:value.start()].lower()
    if re.search(r"\b(fell|fallen|down|dropped|declined|lower|lost|decreased)\b", before):
        return "-" + value.group(1)
    if re.search(r"\b(rose|risen|up|higher|gained|increased|climbed)\b", before):
        return value.group(1)
    return ""


def collect_public():
    """Permintaan rendah: satu halaman daftar dan satu halaman per komoditas."""
    soup = fetch_html(URL + "/commodities")
    data = {}
    for label, path in NAMES.items():
        row = {
            "Komoditas": label, "Latest Price": "", "Unit": "",
            "Day %": "", "Month %": "", "Year %": "", "Low 1Y": "",
            "High 1Y": "", "Reason": "", "Link berita": "",
            "Waktu sumber": "", "Status": "Belum ditemukan",
        }
        anchor = soup.find("a", href=lambda h: bool(h and h.lower().rstrip("/") == path))
        tr = anchor.find_parent("tr") if anchor else None
        if tr:
            cells = tr.find_all("td", recursive=False)
            # Kolom halaman /commodities: Nama+unit | Price | Chg | %Chg | Monthly | Date.
            if len(cells) >= 6:
                row["Latest Price"] = clean_num(cells[1].get_text(" ", strip=True))
                row["Day %"] = clean_num(cells[3].get_text(" ", strip=True))
                row["Month %"] = clean_num(cells[4].get_text(" ", strip=True))
                row["Waktu sumber"] = cells[5].get_text(" ", strip=True)
                # Hilangkan nama instrumen; pertahankan satuan sebagaimana tampak di halaman.
                first = cells[0].get_text(" ", strip=True)
                row["Unit"] = first.replace(anchor.get_text(" ", strip=True), "", 1).strip()
                row["Status"] = "Harga dari halaman publik"
        data[label] = row

    for label, path in NAMES.items():
        try:
            detail = fetch_html(URL + path)
            text = detail.get_text(" ", strip=True)
            # Batasi pencarian pada ringkasan awal yang memuat 'Over the past month'.
            start = re.search(r"Over the past month", text, re.I)
            if not start:
                continue
            excerpt = text[max(0, start.start()-260):start.start()+300]
            yearly = re.search(r"(?:higher|lower|up|down) than a year ago", excerpt, re.I)
            if yearly:
                window = excerpt[max(0, yearly.start()-35):yearly.end()]
                amount = re.search(r"(\d+(?:\.\d+)?)%", window)
                if amount:
                    data[label]["Year %"] = ("-" if "lower" in yearly.group(0).lower() or "down" in yearly.group(0).lower() else "") + amount.group(1)
        except (requests.RequestException, ValueError):
            # Angka dari halaman daftar tetap ditampilkan bila halaman detail gagal.
            pass
    return pd.DataFrame(data.values(), columns=COLS)


def fmt(value, signed=False):
    try:
        number = float(str(value).replace(",", ""))
        return f"{number:+.2f}%" if signed else f"{number:,.2f}"
    except (TypeError, ValueError):
        return "—"


def png(frame, icp_period, lalang, pendalian):
    display = []
    for _, row in frame.iterrows():
        reason = fill(str(row["Reason"] or "—"), 50)
        display.append([
            row["Komoditas"], f"{fmt(row['Latest Price'])} {row['Unit']}",
            fmt(row["Day %"], True), fmt(row["Month %"], True),
            fmt(row["Year %"], True),
            f"{fmt(row['Low 1Y'])} – {fmt(row['High 1Y'])}", reason,
        ])
    fig, ax = plt.subplots(figsize=(19, 7.8), dpi=160)
    ax.axis("off")
    ax.set_title("Perubahan Harga Komoditas", weight="bold", fontsize=18, pad=22)
    table = ax.table(
        cellText=display,
        colLabels=["Komoditas", "Latest Price", "Day", "Month", "Year", "Low–High (1 Year)", "Reason"],
        cellLoc="left", loc="upper center",
        colWidths=[.10, .14, .065, .075, .075, .15, .395],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 4.3)
    for (i, _), cell in table.get_celld().items():
        cell.set_edgecolor("#273447")
        cell.set_facecolor("#3979cb" if i == 0 else "#fffaf6")
        if i == 0:
            cell.set_text_props(color="white", weight="bold")
    fig.text(.07, .13, f"Indonesian Crude Price ({icp_period or 'periode belum diisi'})", fontsize=14, weight="bold")
    fig.text(.07, .09, f"Lalang: {fmt(lalang)} USD/bbl    Pendalian: {fmt(pendalian)} USD/bbl", fontsize=12)
    fig.text(.07, .04, "Sumber harga: Trading Economics | ICP: Kementerian ESDM | Periksa waktu data dan berita", fontsize=9)
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()


if "frame" not in st.session_state:
    st.session_state.frame = pd.DataFrame([{
        "Komoditas": name, "Latest Price": "", "Unit": "", "Day %": "", "Month %": "", "Year %": "",
        "Low 1Y": "", "High 1Y": "", "Reason": "", "Link berita": "", "Waktu sumber": "", "Status": "Belum diambil"
    } for name in NAMES], columns=COLS)

if st.button("🔄 Ambil dari halaman publik"):
    old = st.session_state.frame.set_index("Komoditas")
    try:
        new = collect_public()
        for i, record in new.iterrows():
            label = record["Komoditas"]
            for column in ["Low 1Y", "High 1Y", "Reason", "Link berita"]:
                new.at[i, column] = old.at[label, column]
            for column in ["Latest Price", "Unit", "Day %", "Month %", "Year %", "Waktu sumber"]:
                if not record[column]:
                    new.at[i, column] = old.at[label, column]
        st.session_state.frame = new
        st.success("Pembacaan selesai. Periksa kolom Status dan angka sebelum mengunduh.")
    except (requests.RequestException, ValueError) as exc:
        st.warning(f"Halaman publik tidak dapat dibaca sekarang: {exc}. Isi tabel secara manual.")

st.markdown("[Buka daftar komoditas Trading Economics](https://tradingeconomics.com/commodities)")
for name, path in NAMES.items():
    st.markdown(f"[{name}]({URL + path})", unsafe_allow_html=False)

edited = st.data_editor(
    st.session_state.frame, hide_index=True, use_container_width=True,
    disabled=["Komoditas", "Waktu sumber", "Status"],
    column_config={"Reason": st.column_config.TextColumn("Reason", width="large"),
                   "Link berita": st.column_config.LinkColumn("Link berita")},
    key="editor",
)
st.session_state.frame = edited
st.caption("Kolom Low–High 1Y, Reason, dan link berita dilengkapi setelah mengecek sumber. Jangan gunakan data bertanda 'Belum ditemukan' tanpa pemeriksaan.")

st.subheader("ICP bulanan")
icp_period = st.text_input("Periode", value="")
c1, c2 = st.columns(2)
lalang = c1.number_input("Lalang (USD/bbl)", min_value=0.0, step=.01, value=None)
pendalian = c2.number_input("Pendalian (USD/bbl)", min_value=0.0, step=.01, value=None)

timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d")
st.download_button("⬇️ Unduh PNG", png(edited, icp_period, lalang, pendalian), f"komoditas_{timestamp}.png", "image/png")
st.download_button("⬇️ Unduh CSV", edited.to_csv(index=False).encode("utf-8-sig"), f"komoditas_{timestamp}.csv", "text/csv")
