"""Report layout: commodity prices and monthly ICP."""
import math
import re
from datetime import datetime
from html import escape
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.font_manager import FontProperties

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

def number(value):
    try:
        v=float(str(value).replace(',',''))
        return v if math.isfinite(v) else None
    except (ValueError,TypeError): return None

def fmt(value, decimals=2, local=False):
    v=number(value)
    if v is None: return '—'
    result=f'{v:,.{decimals}f}'
    return result.replace(',','X').replace('.',',').replace('X','.') if local else result

def reason_text(value):
    return re.sub(r'\$\s+(?=\d)','$',str(value or '—'))

def price(row):
    name=row['Komoditas']; v=number(row['Latest Price'])
    if v is None: return '—'
    # Nickel remains USD/ton, not scaled to thousands.
    unit={'Nikel':'ton','Coal':'ton','Brent Oil':'barrel','Natural Gas':'MMBtu'}.get(name,str(row.get('Unit','')))
    return f'${fmt(v, 0 if name=="Nikel" else 2)}/{unit}'

def range_data(row):
    lo,hi,last=[number(row.get(k)) for k in ('Low 1Y','High 1Y','Latest Price')]
    if any(v is None for v in (lo,hi,last)) or not 0<lo<hi: return None,'Low–High belum diisi'
    if not lo<=last<=hi: return None,'Periksa Low–High TE'
    return (lo,hi,last,(last-lo)/(hi-lo)),''

def updated_label(value):
    try:
        parsed = datetime.strptime(value, "%d/%m/%Y %H:%M GMT+7")
        return "(Updated: " + parsed.strftime("%d/%m/%y at %H.%M GMT+7") + ")"
    except (ValueError, TypeError):
        return "(Updated: " + str(value) + ")"


def preview(frame, year, icp, updated):
    updated = updated_label(updated)
    css='''<style>.commodity-report{overflow-x:auto}.commodity-report table{width:100%;min-width:1200px;border-collapse:collapse;table-layout:fixed;font-family:Arial,sans-serif;color:#171717}.commodity-report th,.commodity-report td{border:1px solid #333;padding:10px 8px}.commodity-report td{background:#fff8f2;vertical-align:middle;text-align:center}.commodity-report .blue{background:#6b9ce4;color:white}.commodity-report .source{background:#3977c9;color:white;font-size:12px}.commodity-report .name{text-align:left;font-weight:bold}.commodity-report .reason{text-align:center;line-height:1.4;overflow-wrap:anywhere;font-size:14px}.commodity-report .green{background:#6aa64b;color:white}.commodity-report .month{background:#97c47d;color:white}.commodity-report .bar{height:12px;border:1px solid #ddd;border-radius:8px;background:#eeede7;position:relative;margin:34px 8px 6px}.commodity-report .marker{position:absolute;top:-4px;height:22px;width:4px;background:#598c7b;transform:translateX(-50%);border-radius:2px}.commodity-report .last{position:absolute;top:-24px;transform:translateX(-50%);color:#598c7b;font-weight:bold;font-size:12px;white-space:nowrap}.commodity-report .bounds{display:flex;justify-content:space-between;font-size:11px;color:#555}.commodity-report .quote{font-size:10px;color:#666;display:block;margin-top:7px}</style>'''
    h=css+'<div class="commodity-report"><table><colgroup>'+''.join(f'<col style="width:{w}%">' for w in [13,14,9,9,9,25,21])+'</colgroup>'
    h+='<tr><th class="source" colspan="7"><div style="font-size:22px;font-weight:bold;margin-bottom:5px">Changes in Commodity Prices</div>(Source: tradingeconomics.com)</th></tr>'
    h+=f'<tr class="blue"><th rowspan="2">Commodity</th><th>Latest Price</th><th colspan="3">%Chg</th><th rowspan="2">Reason</th><th rowspan="2">Low–High (1 Year)</th></tr><tr class="blue"><th style="font-size:11px">{escape(updated)}</th><th>Day</th><th>Month</th><th>Year</th></tr>'
    for _,r in frame.iterrows():
        h+=f'<tr><td class="name">{escape(r["Komoditas"])}</td><td>{escape(price(r))}<span class="quote">{escape(str(r.get("Waktu sumber","") or ""))}</span></td>'
        for k in ('Day %','Month %','Year %'):
            v=number(r[k]); color='#a52222' if v is not None and v<0 else '#428227'
            h+=f'<td style="color:{color}">{fmt(v)+"%" if v is not None else "—"}</td>'
        h+=f'<td class="reason">{escape(reason_text(r["Reason"]))}</td>'
        data,msg=range_data(r)
        if data:
            lo,hi,last,pos=data; label=min(86,max(14,pos*100))
            cell=f'<div class="bar"><span class="last" style="left:{label}%">{fmt(last,0 if r["Komoditas"]=="Nikel" else 2)}</span><span class="marker" style="left:{pos*100}%"></span></div><div class="bounds"><span>{fmt(lo,0 if r["Komoditas"]=="Nikel" else 2)}</span><span>{fmt(hi,0 if r["Komoditas"]=="Nikel" else 2)}</span></div>'
        else: cell=escape(msg)
        h+=f'<td>{cell}</td></tr>'
    h+='</table><table><colgroup><col style="width:13%">'+''.join('<col>' for _ in icp.columns[2:])+'</colgroup>'
    total=len(icp.columns)-1
    h+=f'<tr><th class="green" colspan="{total}">Indonesian Crude Price {year} (USD/bbl)<br><small>(Source: Kementerian ESDM, Updated: Monthly)</small></th></tr><tr class="month"><th>Crude</th>'+''.join(f'<th>{escape(m)}</th>' for m in icp.columns[2:])+'</tr>'
    for _,r in icp.iterrows():
        h+=f'<tr><td class="name">{escape(str(r["Crude"]))}<br><small style="font-weight:normal">{escape(str(r["Notes"]))}</small></td>'+''.join(f'<td>{fmt(r[m],local=True)}</td>' for m in icp.columns[2:])+'</tr>'
    return h+'</table></div>'

def png(frame,year,icp,updated):
    updated = updated_label(updated)
    widths=[260,280,180,180,180,500,420];edges=[20]
    for w in widths:edges.append(edges[-1]+w)
    width=edges[-1]+20
    fig,ax=plt.subplots(figsize=(20,12),dpi=160);fig.subplots_adjust(left=.01,right=.99,bottom=.01,top=.99)
    ax.set_xlim(0,width);ax.axis('off');fig.patch.set_facecolor('white')
    def box(x,y,w,h,color):ax.add_patch(Rectangle((x,y),w,h,facecolor=color,edgecolor='#333',linewidth=.8))
    def txt(x,y,t,size=12,color='#181818',bold=False,ha='center'):
        return ax.text(x,y,str(t),fontsize=size,color=color,fontweight='bold' if bold else 'normal',ha=ha,va='center',family='DejaVu Sans')
    # Measure text on a fixed axis scale so every Reason fits its row.
    ax.set_ylim(0,1400);fig.canvas.draw();renderer=fig.canvas.get_renderer()
    scale=ax.transData.transform((1,0))[0]-ax.transData.transform((0,0))[0]
    font=FontProperties(family='DejaVu Sans',size=12)
    def wrap(text,maxwidth,size=12):
        prop=FontProperties(family='DejaVu Sans',size=size)
        def measure(s):return renderer.get_text_width_height_descent(s,prop,ismath=False)[0]/scale
        lines=[];line=''
        for word in str(text).split():
            if measure(word)>maxwidth:
                if line:lines.append(line);line=''
                chunk=''
                for char in word:
                    if chunk and measure(chunk+char)>maxwidth:lines.append(chunk);chunk=''
                    chunk+=char
                line=chunk
            elif line and measure(line+' '+word)>maxwidth:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        if line:lines.append(line)
        return lines or ['—']
    reasons=[wrap(reason_text(r['Reason']),widths[5]-28) for _,r in frame.iterrows()]
    heights=[max(180,len(lines)*26+26) for lines in reasons]
    total=70+85+sum(heights)+70+38+2*85+30
    ax.set_ylim(0,total);fig.set_size_inches(20,max(10,total/110))
    y=total-15
    box(20,y-70,width-40,70,'#3977c9');txt(width/2,y-25,'Changes in Commodity Prices',19,'white',True);txt(width/2,y-52,'(Source: tradingeconomics.com)',10,'white');y-=70
    for j,title in enumerate(['Commodity','Latest Price','Day','Month','Year','Reason','Low–High (1 Year)']):
        box(edges[j],y-85,widths[j],85,'#6b9ce4')
        if j in (2,3,4):txt((edges[j]+edges[j+1])/2,y-62,title,13,'white',True)
        elif j==1:
            txt((edges[j]+edges[j+1])/2,y-25,title,14,'white',True)
            for n,line in enumerate(wrap(updated,widths[j]-15,8)):txt((edges[j]+edges[j+1])/2,y-52-n*15,line,8,'white')
        else:txt((edges[j]+edges[j+1])/2,y-42,title,14,'white',True)
    box(edges[2],y-40,sum(widths[2:5]),40,'#6b9ce4');txt((edges[2]+edges[5])/2,y-20,'%Chg',14,'white',True);y-=85
    for idx,(_,r) in enumerate(frame.iterrows()):
        h=heights[idx];bottom=y-h;mid=(y+bottom)/2
        for j in range(7):box(edges[j],bottom,widths[j],h,'#fff8f2')
        txt(edges[0]+10,mid,r['Komoditas'],14,bold=True,ha='left');txt((edges[1]+edges[2])/2,mid+8,price(r),13)
        txt((edges[1]+edges[2])/2,mid-19,r.get('Waktu sumber',''),8,'#666')
        for j,k in enumerate(('Day %','Month %','Year %'),2):
            v=number(r[k]);txt((edges[j]+edges[j+1])/2,mid,fmt(v)+'%' if v is not None else '—',13,'#a52222' if v is not None and v<0 else '#428227')
        for n,line in enumerate(reasons[idx]):txt((edges[5]+edges[6])/2,mid+(len(reasons[idx])-1)*13-n*26,line,12)
        data,msg=range_data(r);x=edges[6]+18;w=widths[6]-36
        if data:
            lo,hi,last,pos=data;dec=0 if r['Komoditas']=='Nikel' else 2
            ax.add_patch(FancyBboxPatch((x,mid-6),w,12,boxstyle='round,pad=0,rounding_size=6',facecolor='#eeede7',edgecolor='#ddd'))
            mark=x+pos*w;ax.plot([mark,mark],[mid-10,mid+10],color='#598c7b',linewidth=3,solid_capstyle='round')
            txt(min(x+w-45,max(x+45,mark)),mid+24,fmt(last,dec),10,'#598c7b',True)
            txt(x,mid-23,fmt(lo,dec),9,'#666',ha='left');txt(x+w,mid-23,fmt(hi,dec),9,'#666',ha='right')
        else:txt(x+w/2,mid,msg,11,'#666')
        y=bottom
    box(20,y-70,width-40,70,'#6aa64b');txt(width/2,y-25,f'Indonesian Crude Price {year} (USD/bbl)',16,'white',True);txt(width/2,y-52,'(Source: Kementerian ESDM, Updated: Monthly)',10,'white');y-=70
    months=list(icp.columns[2:]);first=widths[0];cell=(width-40-first)/max(1,len(months))
    box(20,y-38,first,38,'#97c47d');txt(20+first/2,y-19,'Crude',13,'white',True)
    for j,m in enumerate(months):box(20+first+j*cell,y-38,cell,38,'#97c47d');txt(20+first+(j+.5)*cell,y-19,m,13,'white',True)
    y-=38
    for _,r in icp.iterrows():
        box(20,y-85,first,85,'#fff8f2');txt(30,y-20,r['Crude'],13,bold=True,ha='left')
        for n,line in enumerate(wrap(r['Notes'],first-20,9)):txt(30,y-42-n*16,line,9,ha='left')
        for j,m in enumerate(months):box(20+first+j*cell,y-85,cell,85,'#fff8f2');txt(20+first+(j+.5)*cell,y-42,fmt(r[m],local=True),12)
        y-=85
    out=BytesIO();fig.savefig(out,format='png',facecolor='white');plt.close(fig);return out.getvalue()
