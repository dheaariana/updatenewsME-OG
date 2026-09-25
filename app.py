"""Dashboard harian komoditas dari Trading Economics API."""

from datetime import datetime, timedelta
from io import BytesIO
from textwrap import fill
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st


TZ = ZoneInfo("Asia/Jakarta")
API = "https://api.tradingeconomics.com"
# Cocokkan berdasarkan URL halaman, bukan urutan respons API.
COMMODITIES = {
    "Nikel": ("nickel", "/commodity/nickel"),
    "Brent Oil": ("brent", "/commodity/brent-crude-oil"),
    "Coal": ("coal", "/commodity/coal"),
    "Natural Gas": ("natural-gas", "/commodity/natural-gas"),
}

st.set_page_config(page_title="Perubahan Harga Komoditas", layout="wide")
st.title("Perubahan Harga Komoditas")
st.caption("Sumber harga: Trading Economics · Zona waktu tampilan: WIB")

try:
    api_key = st.secrets["TRADING_ECONOMICS_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("Tambahkan TRADING_ECONOMICS_API_KEY ke Streamlit Secrets.")
    st.stop()


def fetch(path, params=None):
    response = requests.get(
        API + path,
        params=params,
        headers={"Authorization": api_key},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Respons API tidak berupa daftar: {str(data)[:180]}")
    return data


@st.cache_data(ttl=3600)
def quotes():
    return fetch("/markets/commodities")


@st.cache_data(ttl=3600)
def yearly_range(symbol):
    end = datetime.now(TZ).date()
    start = end - timedelta(days=365)
    history = fetch(
        f"/markets/historical/{symbol}",
        {"d1": start.isoformat(), "d2": end.isoformat()},
    )
    lows = pd.to_numeric(
        pd.Series([row.get("Low") for row in history], dtype="object"),
        errors="coerce",
    ).dropna()
    highs = pd.to_numeric(
        pd.Series([row.get("High") for row in history], dtype="object"),
        errors="coerce",
    ).dropna()
    if lows.empty or highs.empty:
        return None, None
    return float(lows.min()), float(highs.max())


def fmt(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def pct(value):
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "—"


def as_png(frame, timestamp):
    headers = ["Komoditas", "Latest Price", "Day", "Month", "Year",
               "Low 1Y", "High 1Y", "Reason"]
    values = []
    for _, row in frame.iterrows():
        reason = str(row["Reason"] or "—")
        values.append([str(row[c]) for c in headers[:-1]] + [fill(reason, 48)])

    fig, ax = plt.subplots(figsize=(18, 2.4 + len(values) * 1.15), dpi=160)
    ax.axis("off")
    ax.set_title("Perubahan Harga Komoditas", fontsize=18, weight="bold", pad=28)
    table = ax.table(
        cellText=values,
        colLabels=headers,
        cellLoc="left",
        loc="center",
        colWidths=[.105, .115, .065, .075, .075, .085, .085, .395],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 4)
    for (r, _), cell in table.get_celld().items():
        cell.set_edgecolor("#263443")
        cell.set_facecolor("#3b76c8" if r == 0 else "#fffaf6")
        if r == 0:
            cell.set_text_props(weight="bold", color="white")
    fig.text(.02, .04, f"Dibuat: {timestamp} WIB | Sumber harga: Trading Economics",
             fontsize=9)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=.25)
    plt.close(fig)
    return buffer.getvalue()


if st.button("🔄 Ambil data terbaru"):
    quotes.clear()
    yearly_range.clear()

try:
    snapshot = quotes()
except (requests.RequestException, ValueError) as exc:
    st.error(f"Data harga belum dapat diambil: {exc}")
    st.stop()

rows = []
for name, (slug, page) in COMMODITIES.items():
    item = next(
        (q for q in snapshot if str(q.get("URL", "")).lower().rstrip("/") == page),
        None,
    )
    if item is None:
        # Beberapa respons TE memakai URL Brent dengan slug sedikit berbeda.
        item = next(
            (q for q in snapshot if slug in str(q.get("URL", "")).lower()
             and (name != "Coal" or str(q.get("Name", "")).lower() == "coal")),
            None,
        )
    if item is None:
        st.warning(f"{name} tidak ditemukan. Periksa URL instrumen pada respons API.")
        continue

    try:
        low, high = yearly_range(item["Symbol"])
    except (requests.RequestException, ValueError):
        low, high = None, None
        st.warning(f"Rentang 1 tahun {name} belum tersedia pada akses API ini.")

    source_url = "https://tradingeconomics.com" + str(item.get("URL") or page)
    rows.append({
        "Komoditas": name,
        "Latest Price": f"{fmt(item.get('Last'))} {item.get('unit') or ''}",
        "Day": pct(item.get("DailyPercentualChange")),
        "Month": pct(item.get("MonthlyPercentualChange")),
        "Year": pct(item.get("YearlyPercentualChange")),
        "Low 1Y": fmt(low),
        "High 1Y": fmt(high),
        "Reason": st.session_state.get(f"reason_{name}", ""),
        "Link berita": st.session_state.get(f"news_{name}", ""),
        "Waktu data TE": str(item.get("LastUpdate") or item.get("Date") or ""),
        "Sumber harga": source_url,
    })

if not rows:
    st.error("Keempat komoditas tidak ditemukan pada respons API.")
    st.stop()

st.info("Reason dan link berita diisi setelah verifikasi. Keduanya tidak dihasilkan dari perubahan harga semata.")
frame = pd.DataFrame(rows)
edited = st.data_editor(
    frame,
    hide_index=True,
    use_container_width=True,
    disabled=[c for c in frame.columns if c not in ("Reason", "Link berita")],
    column_config={
        "Reason": st.column_config.TextColumn("Reason", width="large"),
        "Link berita": st.column_config.LinkColumn("Link berita", width="medium"),
        "Sumber harga": st.column_config.LinkColumn("Sumber harga"),
    },
)
for _, row in edited.iterrows():
    st.session_state[f"reason_{row['Komoditas']}"] = row["Reason"]
    st.session_state[f"news_{row['Komoditas']}"] = row["Link berita"]

timestamp = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
st.caption("Lihat kolom 'Waktu data TE': waktu pembaruan tiap komoditas dapat berbeda.")
col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "⬇️ Unduh PNG",
        data=as_png(edited, timestamp),
        file_name=f"komoditas_{datetime.now(TZ):%Y%m%d}.png",
        mime="image/png",
    )
with col2:
    st.download_button(
        "⬇️ Unduh CSV",
        data=edited.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"komoditas_{datetime.now(TZ):%Y%m%d}.csv",
        mime="text/csv",
    )

st.divider()
st.subheader("Indonesian Crude Price (ICP)")
st.caption("ICP Lal ang dan Pendalian diterbitkan bulanan; masukkan angka dari publikasi Kementerian ESDM setelah terbit.")
with st.expander("Catatan ICP bulanan"):
    st.text_input("Periode ICP", placeholder="Contoh: Agustus 2026")
    st.number_input("Lalang (USD/bbl)", min_value=0.0, step=0.01)
    st.number_input("Pendalian (USD/bbl)", min_value=0.0, step=0.01)
    st.text_input("Tautan publikasi ESDM")
