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


def compact_dollars(value):
    return re.sub(r"\$\s+(?=\d)", "$", str(value or ""))


@st.cache_data(ttl=86400, show_spinner=False)
def translate_summary(english):
    """Terjemahkan kutipan ringkas TE; cache teks yang sama agar hemat kuota gratis."""
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": english, "langpair": "en|id"}, timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    translated = unescape(str(payload.get("responseData", {}).get("translatedText", ""))).strip()
    if payload.get("quotaFinished") or payload.get("responseStatus") != 200 or not translated or translated.casefold() == english.casefold():
        raise ValueError("Layanan terjemahan tidak memberikan hasil bahasa Indonesia")
    return compact_dollars(translated)


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
                    data[label]["Reason"] = "Terjemahan belum tersedia. Lihat penjelasan asli pada tautan sumber."
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


def preview(frame, period, lalang, pendalian, lalang_note, pendalian_note):
    """Tampilkan tata letak yang sama dengan keluaran PNG."""
    def bar(row):
        try:
            low, high, price = [float(str(row[k]).replace(",", "")) for k in ("Low 1Y", "High 1Y", "Latest Price")]
            if not (math.isfinite(low) and math.isfinite(high) and math.isfinite(price) and 0 < low < high):
                return '<div>Low–High belum valid</div>'
            if not low <= price <= high:
                return '<div>Periksa kembali Low–High TE</div>'
            if high > low:
                axis_low, axis_high = min(low, price), max(high, price)
                pct = lambda value: 100 * (value - axis_low) / (axis_high - axis_low)
                low_pos, high_pos, price_pos = pct(low), pct(high), pct(price)
                label_pos = max(13, min(87, price_pos))
                marker = (f'<span class="range-bound" style="left:{low_pos:.1f}%"></span><span class="range-bound" style="left:{high_pos:.1f}%"></span>'
                          f'<span class="price-marker" style="left:{label_pos:.1f}%">{fmt_price(price,row["Komoditas"])}</span>'
                          f'<span class="marker" style="left:{price_pos:.1f}%"></span>')
                bounds = (f'<div class="bounds"><span style="left:{low_pos:.1f}%">{fmt_range(low,row["Komoditas"])}</span>'
                          f'<span class="high-bound" style="left:{high_pos:.1f}%">{fmt_range(high,row["Komoditas"])}</span></div>')
            else:
                marker = ""
                bounds = ""
        except (TypeError, ValueError):
            marker = ""
            bounds = ""
        return f'<div class="rangebar">{marker}</div>{bounds}'

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
        reason = f'<span class="reason-text">{escape(compact_dollars(row["Reason"] or "—"))}</span>'
        source_link = str(row["Link berita"] or "")
        if source_link.startswith("https://"):
            reason += f'<small class="reason-link"><a href="{escape(source_link, quote=True)}" target="_blank" rel="noopener noreferrer">Lihat penjelasan sumber</a></small>'
        lines.append(
            f'<tr><td class="name"><a href="{link}" target="_blank">{name}</a></td>'
            f'<td class="price">{fmt_price(row["Latest Price"], row["Komoditas"])}<small>{escape(str(row["Unit"] or ""))} · {escape(str(row["Waktu sumber"] or "tanggal belum ada"))}</small></td>'
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
    .report td.reason{line-height:1.35;font-size:14px;overflow-wrap:anywhere;vertical-align:middle}
    .report td.reason .reason-text{display:block;text-align:justify;text-justify:inter-word;white-space:pre-line}
    .report td.reason .reason-link{display:block;text-align:left;margin-top:6px}
    .report .rangebar{height:12px;background:#f3f0eb;border:1px solid #d8cec7;position:relative;margin:38px 5px 12px}
    .report .range-bound{position:absolute;top:-3px;height:18px;width:1px;background:#a69b92;transform:translateX(-50%)}
    .report .price-marker{position:absolute;top:-30px;transform:translateX(-50%);font-size:14px;font-weight:bold;color:#17657a;white-space:nowrap}
    .report .marker{position:absolute;background:#218497;height:25px;width:5px;top:-7px;transform:translateX(-50%)}
    .report .bounds{position:relative;height:20px;margin:0 5px;font-size:12px;color:#53606a}
    .report .bounds span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}
    .report .bounds span:first-child{transform:translateX(0)}
    .report .bounds span.high-bound{transform:translateX(-100%)}
    .report .icp td{text-align:left;height:34px;font-weight:bold}.report .icp td+td{text-align:center;font-weight:normal}
    </style>"""
    html += '<table class="report"><colgroup><col style="width:14%"><col style="width:15%"><col style="width:6%"><col style="width:6%"><col style="width:6%"><col style="width:29%"><col style="width:24%"></colgroup>'
    html += f'<thead><tr><th colspan="7" class="title">Changes in Commodity Prices<small>Source: tradingeconomics.com · Updated: {datetime.now(ZoneInfo("Asia/Jakarta")):%d/%m/%Y %H:%M} GMT+7</small></th></tr>'
    html += '<tr class="heading"><th>Komoditas</th><th>Latest Price</th><th colspan="3">%Chg</th><th rowspan="2">Reason</th><th rowspan="2">Low–High (1 Year)</th></tr>'
    html += '<tr class="heading"><th></th><th></th><th>Day</th><th>Month</th><th>Year</th></tr></thead>'
    html += '<tbody>'+''.join(lines)+'</tbody>'
    html += f'<tr><th colspan="7" class="green">Indonesian Crude Price (per {escape(period or "periode belum diisi")})<br><small>Source: Kementerian ESDM, updated monthly</small></th></tr>'
    html += '<tr><th class="lightgreen">Crude</th><th colspan="3" class="lightgreen">Price (USD/bbl)</th><th colspan="3" class="lightgreen">Notes</th></tr>'
    html += f'<tr class="icp"><td>Lalang</td><td colspan="3">{fmt(lalang)}</td><td colspan="3">{escape(lalang_note or "—")}</td></tr>'
    html += f'<tr class="icp"><td>Pendalian</td><td colspan="3">{fmt(pendalian)}</td><td colspan="3">{escape(pendalian_note or "—")}</td></tr></table>'
    return html


def png(frame, icp_period, lalang, pendalian, lalang_note, pendalian_note):
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(18, 11), dpi=150)
    ax.set_xlim(0, 1800); ax.set_ylim(0, 1100); ax.axis("off")
    fig.patch.set_facecolor("white")
    edges = [30, 270, 505, 585, 665, 745, 1190, 1770]
    def rect(x, y, w, h, color):
        ax.add_patch(Rectangle((x,y),w,h,facecolor=color,edgecolor="#202020",linewidth=1))
    def txt(x,y,s,size=14,bold=False,color="#181818",align="left"):
        ax.text(x,y,str(s),fontsize=size,fontweight="bold" if bold else "normal",color=color,
                ha=align,va="center",family="DejaVu Sans")
    rect(30,1000,1740,58,"#3977c9")
    txt(900,1037,"Changes in Commodity Prices",19,True,"white","center")
    txt(900,1010,f"Source: tradingeconomics.com · laporan dibuat {datetime.now(ZoneInfo('Asia/Jakarta')):%d/%m/%Y %H:%M} GMT+7",9,False,"white","center")
    rect(30,935,1740,65,"#699ce4")
    for j,title in enumerate(["Komoditas","Latest Price","Day","Month","Year","Reason","Low–High (1 Year)"]):
        if j == 5: x0,x1=edges[5],edges[6]
        elif j == 6: x0,x1=edges[6],edges[7]
        else: x0,x1=edges[j],edges[j+1]
        txt((x0+x1)/2,968,title,11 if j in (2,3,4) else 14,True,"white","center")
    for idx,(_,row) in enumerate(frame.iterrows()):
        top=935-idx*195; bottom=top-195
        rect(30,bottom,1740,195,"#fffaf7")
        for x in edges[1:-1]:
            ax.plot([x,x],[bottom,top],color="#202020",linewidth=1)
        txt(42,bottom+103,row["Komoditas"],16,True)
        txt(387,bottom+108,fmt_price(row["Latest Price"],row["Komoditas"]),17,True,align="center")
        txt(387,bottom+77,row["Unit"] or "",10,align="center")
        txt(387,bottom+53,row["Waktu sumber"] or "tanggal belum ada",8,align="center")
        for j,key in enumerate(["Day %","Month %","Year %"]):
            try: color="#a51d1d" if float(row[key])<0 else "#276c2a"
            except (TypeError,ValueError): color="#333333"
            txt((edges[j+2]+edges[j+3])/2,bottom+103,fmt(row[key],True),9,False,color,"center")
        # Bungkus sesuai lebar teks yang terukur, lalu ratakan tiap baris kecuali baris terakhir.
        from matplotlib.font_manager import FontProperties
        font = FontProperties(family="DejaVu Sans", size=9)
        renderer = fig.canvas.get_renderer()
        pixels_per_unit = ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0]
        width = edges[6] - edges[5] - 26
        def measure(s):
            return renderer.get_text_width_height_descent(s, font, ismath=False)[0] / pixels_per_unit
        words = compact_dollars(row["Reason"] or "—").split()
        reason_lines, current = [], []
        for word in words:
            if current and measure(" ".join(current + [word])) > width:
                reason_lines.append(current)
                current = []
            current.append(word)
        if current:
            reason_lines.append(current)
        if len(reason_lines) > 9:
            reason_lines = reason_lines[:9]
            last = reason_lines[-1]
            while last and measure(" ".join(last) + "…") > width:
                last.pop()
            reason_lines[-1] = last + ["…"]
        reason_clip=Rectangle((edges[5]+10,bottom+12),edges[6]-edges[5]-20,171,transform=ax.transData)
        start_y = bottom + 97 + (len(reason_lines) - 1) * 9
        for k,line in enumerate(reason_lines):
            y = start_y - k * 18
            gaps = len(line) - 1
            extra = (width - sum(measure(word) for word in line)) / gaps if gaps and k < len(reason_lines)-1 else measure(" ")
            x = edges[5] + 13
            for word in line:
                label = ax.text(x,y,word,fontsize=9,color="#181818",ha="left",va="center",family="DejaVu Sans")
                label.set_clip_path(reason_clip)
                x += measure(word) + extra
        low,high,price=[row[k] for k in ["Low 1Y","High 1Y","Latest Price"]]
        try:
            low,high,price=[float(v) for v in (low,high,price)]
            if math.isfinite(low) and math.isfinite(high) and math.isfinite(price) and 0 < low < high and low <= price <= high:
                axis_low,axis_high=min(low,price),max(high,price)
                x_of=lambda value:1207+(value-axis_low)/(axis_high-axis_low)*544
                low_x,high_x,marker_x=x_of(low),x_of(high),x_of(price)
                rect(1207,bottom+97,544,13,"#f4f0eb")
                for bound_x in (low_x, high_x):
                    ax.plot([bound_x,bound_x],[bottom+94,bottom+113],color="#a69b92",linewidth=1)
                txt(low_x,bottom+54,fmt_range(low,row["Komoditas"]),11)
                txt(high_x,bottom+54,fmt_range(high,row["Komoditas"]),11,align="right")
                ax.add_patch(Rectangle((marker_x-3,bottom+88),6,34,color="#218497"))
                label_x=max(1260,min(1700,marker_x))
                txt(label_x,bottom+146,fmt_price(price,row["Komoditas"]),11,True,"#17657a","center")
            else:
                txt(1480,bottom+103,"Periksa Low–High TE",12,align="center")
        except (TypeError,ValueError):
            txt(1480,bottom+103,"Low–High belum diisi",12,align="center")
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

with st.expander("✏️ Isi ICP bulanan"):
    icp_period = st.text_input("Periode", value="Agustus 2026")
    c1, c2 = st.columns(2)
    lalang = c1.number_input("Lalang (USD/bbl)", min_value=0.0, step=.01, value=93.15)
    pendalian = c2.number_input("Pendalian (USD/bbl)", min_value=0.0, step=.01, value=90.95)
    lalang_note = st.text_input("Notes Lalang", value="Ref. untuk debitur a.n ITA")
    pendalian_note = st.text_input("Notes Pendalian", value="Ref. untuk debitur a.n APG West Kampar")

st.caption("Low–High (1 Year): input manual dari Trading Economics. Harga, perubahan, dan ringkasan dibaca dari halaman publik jika tersedia. ICP masih contoh dan perlu diperbarui manual.")
with st.expander("💾 Simpan / pulihkan Low–High"):
    saved = [{k: str(row.get(k, "")) for k in ("Komoditas", "Low 1Y", "High 1Y", "Tanggal cek Low-High")} for _, row in edited.iterrows()]
    st.download_button("Unduh pengaturan Low–High", json.dumps(saved, ensure_ascii=False, indent=2), "low_high_te.json", "application/json")
    uploaded = st.file_uploader("Unggah pengaturan yang pernah disimpan", type=["json"])
    if uploaded is not None and st.button("Terapkan pengaturan"):
        try:
            records = json.load(uploaded)
            restored = edited.copy()
            if not isinstance(records, list): raise ValueError("Format pengaturan harus berupa daftar")
            for record in records:
                if record["Komoditas"] not in NAMES: raise ValueError("Komoditas tidak dikenal")
                lo, hi = float(record["Low 1Y"]), float(record["High 1Y"])
                date = datetime.strptime(record["Tanggal cek Low-High"], "%Y-%m-%d").date()
                if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo < hi) or date > TODAY:
                    raise ValueError("Angka atau tanggal cek tidak valid")
                mask = restored["Komoditas"] == record["Komoditas"]
                for field in ("Low 1Y", "High 1Y", "Tanggal cek Low-High"):
                    restored.loc[mask, field] = record[field]
            st.session_state.frame = restored
            st.session_state.editor_revision += 1
            st.rerun()
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"Pengaturan tidak dapat dipakai: {exc}")

st.markdown("### Tampilan laporan")
st.markdown(preview(edited, icp_period, lalang, pendalian, lalang_note, pendalian_note), unsafe_allow_html=True)
with st.expander("Sumber dan status pembacaan"):
    st.dataframe(edited[["Komoditas", "Waktu sumber", "Tanggal cek Low-High", "Acuan rentang", "Status", "Link berita"]], hide_index=True, use_container_width=True)

timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d")
invalid = [str(row["Komoditas"]) for _,row in edited.iterrows()
           if not row["Latest Price"] or not is_fresh(row["Waktu sumber"])
           or "berbeda" in str(row["Status"]).lower()]
def range_valid(row):
    try:
        lo, hi, price = (float(str(row[k]).replace(",", "")) for k in ("Low 1Y", "High 1Y", "Latest Price"))
        checked = datetime.strptime(str(row["Tanggal cek Low-High"]), "%Y-%m-%d").date()
        return all(math.isfinite(v) for v in (lo, hi, price)) and 0 < lo < hi and lo <= price <= hi and checked == TODAY
    except (ValueError, TypeError, KeyError):
        return False
invalid_range = [str(row["Komoditas"]) for _, row in edited.iterrows() if not range_valid(row)]
missing_year = [str(row["Komoditas"]) for _,row in edited.iterrows() if not row["Year %"]]
if missing_year:
    st.warning("Year % belum terambil untuk: " + ", ".join(missing_year) + ". Isi setelah mencocokkan halaman detail sumber.")
if invalid:
    st.warning("Harga kosong, tanggal sumber sudah lama, atau harga daftar/detail berbeda: " + ", ".join(invalid))

if invalid:
    manual_verified = st.checkbox("Saya sudah melengkapi dan memeriksa angka, tanggal harga, serta periode rentang pada sumbernya")
else:
    manual_verified = True
st.download_button("⬇️ Unduh PNG", png(edited, icp_period, lalang, pendalian, lalang_note, pendalian_note) if manual_verified and not invalid_range else b"",
                   f"komoditas_{timestamp}.png", "image/png", disabled=not manual_verified or bool(invalid_range))
st.download_button("⬇️ Unduh CSV", edited.to_csv(index=False).encode("utf-8-sig"), f"komoditas_{timestamp}.csv", "text/csv")
