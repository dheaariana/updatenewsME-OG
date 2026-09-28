"""Dashboard gratis: baca halaman publik Trading Economics jika tersedia."""
from datetime import datetime, timedelta
from io import BytesIO
from html import escape
import re
from textwrap import fill
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import openpyxl
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="Update Komoditas", layout="wide")
st.title("Perubahan Harga Komoditas")
st.caption("Tabel laporan harian · Sumber harga: halaman publik Trading Economics")

URL = "https://tradingeconomics.com"
WB_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
WB_SERIES = {
    "Nikel": "Nickel", "Brent Oil": "Crude oil, Brent",
    "Coal": "Coal, Australian", "Natural Gas": "Natural gas, US",
}
NAMES = {
    "Nikel": "/commodity/nickel",
    "Brent Oil": "/commodity/brent-crude-oil",
    "Coal": "/commodity/coal",
    "Natural Gas": "/commodity/natural-gas",
}
LABELS = {"Nikel": "nickel", "Brent Oil": "brent oil", "Coal": "coal", "Natural Gas": "natural gas"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal commodity report)"}
COLS = ["Komoditas", "Latest Price", "Unit", "Day %", "Month %", "Year %",
        "Low 1Y", "High 1Y", "Reason", "Link berita", "Waktu sumber", "Acuan rentang", "Status"]
TODAY = datetime.now(ZoneInfo("Asia/Jakarta")).date()
REFERENCE_REASON_20260928 = {
    "Nikel": "Lemahnya permintaan downstream China dan tingginya inventori, di tengah kekhawatiran surplus pasokan global.",
    "Brent Oil": "Kekhawatiran gangguan pasokan akibat konflik Timur Tengah dan ketidakpastian akses Selat Hormuz.",
    "Coal": "Permintaan pembangkit listrik tetap kuat ketika harga LNG tinggi dan pasokan energi global terganggu.",
    "Natural Gas": "Pasokan domestik AS relatif melimpah, sementara kenaikan kebutuhan LNG belum mengimbangi tekanan produksi.",
}


def world_bank_ranges():
    """Rentang min/max dari 12 harga rata-rata bulanan terakhir, bukan 52-week high/low harian."""
    response = requests.get(WB_URL, headers=HEADERS, timeout=35)
    response.raise_for_status()
    workbook = openpyxl.load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    try:
        sheet = workbook["Monthly Prices"]
        rows = sheet.iter_rows(values_only=True)
        for _ in range(4):
            next(rows)
        headers = next(rows)
        columns = {label: headers.index(series) for label, series in WB_SERIES.items()}
        monthly = []
        for row in rows:
            period = row[0]
            if not isinstance(period, str) or not re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", period):
                continue
            year, month = int(period[:4]), int(period[5:])
            if (year, month) > (TODAY.year, TODAY.month):
                continue
            monthly.append((period, row))
        if len(monthly) < 12:
            raise ValueError("Kurang dari 12 bulan harga World Bank tersedia")
        window = monthly[-12:]
        first_period, last_period = window[0][0], window[-1][0]
        first_index = int(first_period[:4]) * 12 + int(first_period[5:])
        last_index = int(last_period[:4]) * 12 + int(last_period[5:])
        if last_index - first_index != 11 or TODAY.year * 12 + TODAY.month - last_index > 2:
            raise ValueError("Periode World Bank tidak lengkap atau belum diperbarui")
        results = {}
        for label, column in columns.items():
            values = [row[column] for _, row in window]
            if any(not isinstance(value, (int, float)) for value in values):
                raise ValueError(f"Seri {label} tidak lengkap selama 12 bulan")
            results[label] = (min(values), max(values))
        period_label = f"WB bulanan {first_period}–{last_period}"
        return results, period_label
    finally:
        workbook.close()


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

    for label, path in NAMES.items():
        try:
            detail = fetch_html(URL + path)
            text = detail.get_text(" ", strip=True)
            yearly, summary = detail_fields(text, label)
            if yearly and not data[label]["Year %"]:
                data[label]["Year %"] = yearly
            if summary:
                data[label]["Reason"] = "Konteks pasar TE: " + summary
                data[label]["Link berita"] = URL + path
        except (requests.RequestException, ValueError):
            # Angka dari halaman daftar tetap ditampilkan bila halaman detail gagal.
            pass
    # Hanya untuk hari contoh yang diberikan pengguna; jangan teruskan angka lama ke hari berikutnya.
    if TODAY.isoformat() == "2026-09-28":
        for label in NAMES:
            if not data[label]["Reason"]:
                data[label]["Reason"] = "Contoh 28/09/2026: " + REFERENCE_REASON_20260928[label]
    return pd.DataFrame(data.values(), columns=COLS)


def fmt(value, signed=False):
    try:
        number = float(str(value).replace(",", ""))
        return f"{number:+.2f}%" if signed else f"{number:,.2f}"
    except (TypeError, ValueError):
        return "—"


def fmt_range(value, commodity):
    try:
        return f"{float(str(value).replace(',', '')):,.{3 if commodity == 'Natural Gas' else 2}f}"
    except (TypeError, ValueError):
        return "—"


def preview(frame, period, lalang, pendalian, lalang_note, pendalian_note):
    """Tampilkan tata letak yang sama dengan keluaran PNG."""
    def bar(row):
        try:
            low, high, price = [float(str(row[k]).replace(",", "")) for k in ("Low 1Y", "High 1Y", "Latest Price")]
            pos = max(0, min(100, 100 * (price - low) / (high - low))) if high > low else 0
            marker = f'<span class="marker" style="left:{pos:.1f}%"></span>' if high > low else ""
        except (TypeError, ValueError):
            marker = ""
        return f'<div class="rangebar">{marker}</div><div class="bounds"><span>{fmt_range(row["Low 1Y"],row["Komoditas"])}</span><span>{fmt_range(row["High 1Y"],row["Komoditas"])}</span></div><small>Rentang: {escape(str(row["Acuan rentang"] or "belum diverifikasi"))}</small>'

    def change(value):
        try:
            color = "#ab2020" if float(value) < 0 else "#286a29"
        except (TypeError, ValueError):
            color = "#333"
        return f'<span style="color:{color}">{fmt(value, True)}</span>'

    lines = []
    for _, row in frame.iterrows():
        name = escape(str(row["Komoditas"]))
        link = escape(URL + NAMES[row["Komoditas"]], quote=True)
        reason = escape(str(row["Reason"] or "—"))
        lines.append(
            f'<tr><td class="name"><a href="{link}" target="_blank">{name}</a></td>'
            f'<td class="price">{fmt(row["Latest Price"])}<small>{escape(str(row["Unit"] or ""))} · {escape(str(row["Waktu sumber"] or "tanggal belum ada"))}</small></td>'
            f'<td>{change(row["Day %"])}</td><td>{change(row["Month %"])}</td><td>{change(row["Year %"])}</td>'
            f'<td class="reason">{reason}</td><td class="range">{bar(row)}</td></tr>'
        )
    html = """<style>
    .report {font-family:Arial,sans-serif; color:#181818; border:1px solid #222; width:100%; min-width:1050px; border-collapse:collapse; table-layout:fixed}
    .report th,.report td {border:1px solid #222;padding:10px 8px;text-align:center;vertical-align:middle}
    .report .title {background:#3977c9;color:#fff;font-size:21px;padding:8px}
    .report .title small {display:block;font-size:12px}
    .report .heading {background:#699ce4;color:white;font-size:15px}
    .report .green {background:#67a44f;color:white;font-size:18px}
    .report .lightgreen {background:#a1cf90;color:white}
    .report tbody tr {height:120px;background:#fffaf7}
    .report td.name {text-align:left;font-weight:bold}.report td.name a{color:#181818;text-decoration:none}
    .report td.price {font-weight:bold;font-size:18px}.report td.price small{display:block;font-size:12px;font-weight:normal}
    .report td.reason{text-align:left;line-height:1.35;font-size:14px;white-space:pre-wrap}
    .report .rangebar{height:12px;background:#f3f0eb;border:1px solid #d8cec7;position:relative;margin:12px 5px}
    .report .marker{position:absolute;background:#218497;height:25px;width:5px;top:-7px;transform:translateX(-50%)}
    .report .bounds{display:flex;justify-content:space-between;font-size:12px;color:#53606a}
    .report .icp td{text-align:left;height:34px;font-weight:bold}.report .icp td+td{text-align:center;font-weight:normal}
    </style>"""
    html += '<table class="report"><colgroup><col style="width:14%"><col style="width:15%"><col style="width:6%"><col style="width:6%"><col style="width:6%"><col style="width:29%"><col style="width:24%"></colgroup>'
    html += f'<thead><tr><th colspan="7" class="title">Changes in Commodity Prices<small>Source: tradingeconomics.com · Updated: {datetime.now(ZoneInfo("Asia/Jakarta")):%d/%m/%Y %H:%M} GMT+7 (waktu laporan)</small></th></tr>'
    html += '<tr class="heading"><th>Komoditas</th><th>Latest Price</th><th colspan="3">%Chg</th><th rowspan="2">Reason</th><th rowspan="2">Low–High (12 rata-rata bulanan)</th></tr>'
    html += '<tr class="heading"><th></th><th></th><th>Day</th><th>Month</th><th>Year</th></tr></thead>'
    html += '<tbody>'+''.join(lines)+'</tbody>'
    html += f'<tr><th colspan="7" class="green">Indonesian Crude Price (per {escape(period or "periode belum diisi")})<br><small>Source: Kementerian ESDM, updated monthly</small></th></tr>'
    html += '<tr><th class="lightgreen">Crude</th><th colspan="3" class="lightgreen">Price (USD/bbl)</th><th colspan="3" class="lightgreen">Notes</th></tr>'
    html += f'<tr class="icp"><td>Lalang</td><td colspan="3">{fmt(lalang)}</td><td colspan="3">{escape(lalang_note or "—")}</td></tr>'
    html += f'<tr class="icp"><td>Pendalian</td><td colspan="3">{fmt(pendalian)}</td><td colspan="3">{escape(pendalian_note or "—")}</td></tr></table>'
    return html


def png(frame, icp_period, lalang, pendalian, lalang_note, pendalian_note):
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(18, 9), dpi=150)
    ax.set_xlim(0, 1800); ax.set_ylim(0, 900); ax.axis("off")
    fig.patch.set_facecolor("white")
    edges = [30, 270, 505, 585, 665, 745, 1190, 1770]
    def rect(x, y, w, h, color):
        ax.add_patch(Rectangle((x,y),w,h,facecolor=color,edgecolor="#202020",linewidth=1))
    def txt(x,y,s,size=14,bold=False,color="#181818",align="left"):
        ax.text(x,y,str(s),fontsize=size,fontweight="bold" if bold else "normal",color=color,
                ha=align,va="center",family="DejaVu Sans")
    rect(30,800,1740,58,"#3977c9")
    txt(900,837,"Changes in Commodity Prices",19,True,"white","center")
    txt(900,810,f"Source: tradingeconomics.com · laporan dibuat {datetime.now(ZoneInfo('Asia/Jakarta')):%d/%m/%Y %H:%M} GMT+7",9,False,"white","center")
    rect(30,735,1740,65,"#699ce4")
    for j,title in enumerate(["Komoditas","Latest Price","Day","Month","Year","Reason","Low–High (12 bulan)"]):
        if j == 5: x0,x1=edges[5],edges[6]
        elif j == 6: x0,x1=edges[6],edges[7]
        else: x0,x1=edges[j],edges[j+1]
        txt((x0+x1)/2,768,title,11 if j in (2,3,4) else 14,True,"white","center")
    for idx,(_,row) in enumerate(frame.iterrows()):
        top=735-idx*145; bottom=top-145
        rect(30,bottom,1740,145,"#fffaf7")
        for x in edges[1:-1]:
            ax.plot([x,x],[bottom,top],color="#202020",linewidth=1)
        txt(42,bottom+74,row["Komoditas"],16,True)
        txt(387,bottom+78,fmt(row["Latest Price"]),17,True,align="center")
        txt(387,bottom+49,row["Unit"] or "",10,align="center")
        txt(387,bottom+27,row["Waktu sumber"] or "tanggal belum ada",8,align="center")
        for j,key in enumerate(["Day %","Month %","Year %"]):
            try: color="#a51d1d" if float(row[key])<0 else "#276c2a"
            except (TypeError,ValueError): color="#333333"
            txt((edges[j+2]+edges[j+3])/2,bottom+73,fmt(row[key],True),9,False,color,"center")
        reason=fill(str(row["Reason"] or "—"),34).splitlines()[:5]
        for k,line in enumerate(reason): txt(758,bottom+115-k*23,line,10)
        low,high,price=[row[k] for k in ["Low 1Y","High 1Y","Latest Price"]]
        txt(1204,bottom+36,fmt_range(low,row["Komoditas"]),11)
        txt(1757,bottom+36,fmt_range(high,row["Komoditas"]),11,align="right")
        txt(1480,bottom+17,"Rentang: " + (row["Acuan rentang"] or "belum diverifikasi"),8,align="center")
        rect(1207,bottom+69,544,13,"#f4f0eb")
        try:
            low,high,price=[float(v) for v in (low,high,price)]
            if high>low:
                pos=max(0,min(1,(price-low)/(high-low)))
                ax.add_patch(Rectangle((1207+pos*544-3,bottom+60),6,34,color="#218497"))
                txt(1207+pos*544,bottom+110,fmt(price),11,True,"#17657a","center")
        except (TypeError,ValueError): pass
    rect(30,108,1740,47,"#67a44f")
    txt(900,132,f"Indonesian Crude Price (per {icp_period or 'periode belum diisi'})",17,True,"white","center")
    rect(30,75,1740,33,"#a1cf90")
    txt(160,92,"Crude",12,True,"white","center")
    txt(700,92,"Price (USD/bbl)",12,True,"white","center")
    txt(1380,92,"Notes",12,True,"white","center")
    rect(30,42,1740,33,"#fffaf7")
    txt(42,59,"Lalang",12,True)
    txt(700,59,fmt(lalang),12,align="center")
    txt(1380,59,fill(lalang_note or "—",40).splitlines()[0],10,align="center")
    rect(30,9,1740,33,"#fffaf7")
    txt(42,26,"Pendalian",12,True)
    txt(700,26,fmt(pendalian),12,align="center")
    txt(1380,26,fill(pendalian_note or "—",40).splitlines()[0],10,align="center")
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight", pad_inches=.2)
    plt.close(fig)
    return out.getvalue()


if "frame" not in st.session_state:
    st.session_state.frame = pd.DataFrame([{
        "Komoditas": name, "Latest Price": "", "Unit": "", "Day %": "", "Month %": "", "Year %": "",
        "Low 1Y": "", "High 1Y": "",
        "Reason": "", "Link berita": "", "Waktu sumber": "", "Acuan rentang": "Belum diambil", "Status": "Belum diambil"
    } for name in NAMES], columns=COLS)

if st.button("🔄 Ambil dari halaman publik"):
    old = st.session_state.frame.set_index("Komoditas")
    try:
        new = collect_public()
        try:
            ranges, range_period = world_bank_ranges()
        except (requests.RequestException, ValueError, KeyError, OSError, openpyxl.utils.exceptions.InvalidFileException) as exc:
            ranges, range_period = {}, "World Bank gagal dibaca"
            st.warning(f"Rentang bulanan World Bank belum bisa diperbarui: {exc}")
        for i, record in new.iterrows():
            label = record["Komoditas"]
            if label in ranges:
                new.at[i, "Low 1Y"], new.at[i, "High 1Y"] = ranges[label]
                new.at[i, "Acuan rentang"] = range_period
            else:
                new.at[i, "Low 1Y"] = ""
                new.at[i, "High 1Y"] = ""
                new.at[i, "Acuan rentang"] = range_period
            if old.at[label, "Reason"] and not str(old.at[label, "Reason"]).startswith(("Konteks pasar TE:", "Contoh 28/09/2026:")):
                new.at[i, "Reason"] = old.at[label, "Reason"]
                new.at[i, "Link berita"] = old.at[label, "Link berita"]
            # Jangan tampilkan harga lama seolah hasil pembacaan baru.
        st.session_state.frame = new
        st.success("Pembacaan selesai. Periksa tanggal sumber harga harian dan periode World Bank sebelum mengunduh.")
    except (requests.RequestException, ValueError) as exc:
        st.warning(f"Halaman publik tidak dapat dibaca sekarang: {exc}. Isi tabel secara manual.")

with st.expander("✏️ Edit angka, rentang bulanan, alasan dan tautan berita"):
    edited = st.data_editor(
        st.session_state.frame, hide_index=True, use_container_width=True,
        disabled=["Komoditas", "Status"],
        column_config={"Reason": st.column_config.TextColumn("Reason", width="large"),
                       "Link berita": st.column_config.LinkColumn("Link berita")},
        key="editor",
    )
    st.session_state.frame = edited
    st.caption("Low–High otomatis berasal dari 12 rata-rata harga bulanan World Bank, bukan titik ekstrem harga harian. Reason otomatis adalah ringkasan TE dan perlu ditinjau.")

with st.expander("✏️ Isi ICP bulanan"):
    icp_period = st.text_input("Periode", value="Agustus 2026")
    c1, c2 = st.columns(2)
    lalang = c1.number_input("Lalang (USD/bbl)", min_value=0.0, step=.01, value=93.15)
    pendalian = c2.number_input("Pendalian (USD/bbl)", min_value=0.0, step=.01, value=90.95)
    lalang_note = st.text_input("Notes Lalang", value="Ref. untuk debitur a.n ITA")
    pendalian_note = st.text_input("Notes Pendalian", value="Ref. untuk debitur a.n APG West Kampar")

st.caption(f"Low–High: 12 rata-rata bulanan dari [World Bank Pink Sheet]({WB_URL}); harga harian: Trading Economics. Seri World Bank dapat berbeda dari instrumen harga harian, sehingga penanda harga bisa di luar rentang bulanan. ICP masih contoh Agustus 2026 dan perlu diisi saat rilis baru.")

st.markdown("### Tampilan laporan")
st.markdown(preview(edited, icp_period, lalang, pendalian, lalang_note, pendalian_note), unsafe_allow_html=True)
with st.expander("Sumber dan status pembacaan"):
    st.dataframe(edited[["Komoditas", "Waktu sumber", "Status", "Link berita"]], hide_index=True, use_container_width=True)

timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d")
invalid = [str(row["Komoditas"]) for _,row in edited.iterrows()
           if not row["Latest Price"] or not is_fresh(row["Waktu sumber"])]
invalid_range = [str(row["Komoditas"]) for _, row in edited.iterrows()
                 if not row["Low 1Y"] or not row["High 1Y"]]
missing_year = [str(row["Komoditas"]) for _,row in edited.iterrows() if not row["Year %"]]
if missing_year:
    st.warning("Year % belum terambil untuk: " + ", ".join(missing_year) + ". Isi setelah mencocokkan halaman detail sumber.")
if invalid:
    st.warning("Harga kosong atau lebih dari satu hari perdagangan sejak tanggal sumber: " + ", ".join(invalid))
if invalid_range:
    st.warning("Rentang bulanan belum terisi untuk: " + ", ".join(invalid_range) + ". Lengkapi dan tulis periode acuannya sebelum mengunduh PNG.")
if invalid or invalid_range:
    manual_verified = st.checkbox("Saya sudah melengkapi dan memeriksa angka, tanggal harga, serta periode rentang pada sumbernya")
else:
    manual_verified = True
st.download_button("⬇️ Unduh PNG", png(edited, icp_period, lalang, pendalian, lalang_note, pendalian_note) if manual_verified else b"",
                   f"komoditas_{timestamp}.png", "image/png", disabled=not manual_verified)
st.download_button("⬇️ Unduh CSV", edited.to_csv(index=False).encode("utf-8-sig"), f"komoditas_{timestamp}.csv", "text/csv")
