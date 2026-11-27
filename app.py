import io, json, pathlib, zipfile
import pandas as pd, plotly.graph_objects as go, streamlit as st
from plotly.subplots import make_subplots
import refresh
from data_sources import SERIES

NAVY, BLUE, RED, GREY = "#12274D", "#0039A6", "#D52B1E", "#6B7280"
D = pathlib.Path(__file__).parent / "data"
st.set_page_config(page_title="Russia Economic Monitor", page_icon="📊", layout="wide")

st.markdown("""<style>
.block-container{padding-top:.6rem;padding-bottom:1rem;max-width:1500px}
.stripe{height:6px;background:linear-gradient(#fff 33.3%,#0039A6 33.3% 66.6%,#D52B1E 66.6%);border:1px solid #D5DAE3;margin-bottom:12px}
.flag{width:54px;height:36px;border:1px solid #C5CBD6;background:linear-gradient(#fff 33.3%,#0039A6 33.3% 66.6%,#D52B1E 66.6%)}
.ttl{font-size:1.6rem;font-weight:700;line-height:1.2;color:#12274D} .sub{color:#5B6578;font-size:.9rem}
.cell-title{font-weight:700;font-size:1rem;margin:6px 0 0;color:#12274D;border-bottom:2px solid #0039A6;padding-bottom:2px}
[data-testid="stCaptionContainer"]{font-size:.74rem;line-height:1.35}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="stripe"></div><div style="display:flex;align-items:center;gap:14px"><div class="flag"></div>'
            '<div><div class="ttl">Russia Economic Monitor</div>'
            '<div class="sub">Monetary policy, prices, the ruble, energy, fiscal position and growth, from official and international sources</div>'
            '</div></div>', unsafe_allow_html=True)


def read_meta():
    p = D / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def zip_bytes():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for p in list(D.glob("*.csv")) + list(D.glob("*.json")) + list(D.glob("*.txt")):
            z.write(p, p.name)
    return b.getvalue()


# ---- control bar ----
c2, c3, c4 = st.columns([1.3, 1.5, 4])
if c2.button("Refresh data now", type="primary"):
    with st.spinner("Fetching all series from their sources..."):
        lines, fails = refresh.run()
    st.session_state["msg"] = (fails, lines)
    st.rerun()
c3.download_button("Download data (zip)", zip_bytes(), "russia_data.zip", "application/zip")
meta = read_meta()
c4.markdown(f"**Last successful refresh run (UTC):** {meta.get('_last_run', 'never')}  \n"
            "<span style='font-size:.75rem;color:#5B6578'>This is separate from each chart's latest observation date.</span>",
            unsafe_allow_html=True)

if "msg" in st.session_state:
    fails, lines = st.session_state.pop("msg")
    (st.warning if fails else st.success)(
        f"Refresh finished: {fails} series failed, kept cached data for those." if fails else "Refresh finished: all series updated.")
    with st.expander("Refresh log (this run)", expanded=bool(fails)):
        st.code("\n".join(lines))


def load(k):
    p = D / f"{k}.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, parse_dates=["date"])


TXT = "#111827"


def style(fig, h=270):
    fig.update_layout(template="plotly_white", height=h, paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(color=TXT, size=12), margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=1.14, x=0, font=dict(color=TXT)),
                      hoverlabel=dict(bgcolor="white", font=dict(color=TXT)))
    for ax in (fig.update_xaxes, fig.update_yaxes):
        ax(gridcolor="#E5E7EB", linecolor="#9CA3AF", tickfont=dict(color=TXT), title_font=dict(color=TXT))
    fig.update_annotations(font=dict(color=TXT))
    return fig


def line(df, cols, **kw):
    f = go.Figure()
    for c, name, color in cols:
        d = df.dropna(subset=[c])
        f.add_trace(go.Scatter(x=d["date"], y=d[c], name=name, line=dict(color=color, width=2), **kw))
    return f


def annual(df, name):
    return go.Figure(go.Bar(x=df["date"].dt.year, y=df["value"], name=name,
                            marker_color=[RED if v < 0 else BLUE for v in df["value"]],
                            marker_opacity=[0.4 if x else 1 for x in df["forecast"]]))


def build(k, d):
    if k == "key_rate":
        return line(d, [("value", "Key rate, %", BLUE)], line_shape="hv")
    if k == "cpi":
        f = line(d, [("value", "CPI y/y, %", RED)])
        f.add_hline(y=4, line_dash="dash", line_color=GREY, annotation_text="CBR target 4%")
        return f
    if k == "fx":
        return line(d, [("usd", "RUB per USD", BLUE), ("cny", "RUB per CNY", RED)])
    if k == "oil_gas":
        f = make_subplots(specs=[[{"secondary_y": True}]])
        b, g = d.dropna(subset=["brent"]), d.dropna(subset=["gas"])
        f.add_trace(go.Scatter(x=b["date"], y=b["brent"], name="Brent, USD/bbl (left)", line=dict(color=NAVY, width=1.8)), secondary_y=False)
        f.add_trace(go.Scatter(x=g["date"], y=g["gas"], name="EU gas, USD/MMBtu (right)", line=dict(color=RED, width=2.2)), secondary_y=True)
        return f
    return annual(d, SERIES[k]["title"])


def info(k):
    s, m = SERIES[k], meta.get(k, {})
    ref = str(m.get("last_success", "never")).replace("T", " ")[:16]
    st.caption(f"{s['units']} | {s['freq']} | Source: [{m.get('source_used') or s['source']}]({s['url']})  \n"
               f"Latest observation: **{m.get('latest_obs', 'n/a')}** | Last successful refresh: **{ref} UTC**  \n"
               f"Transformation: {s['note']}")
    if m.get("status") == "failed":
        st.warning(f"Last refresh failed ({m.get('error')}). Showing cached data.")


def cell(k):
    st.markdown(f'<div class="cell-title">{SERIES[k]["title"]}</div>', unsafe_allow_html=True)
    d = load(k)
    if d is None:
        st.error("No data yet. Click 'Refresh data now'.")
    else:
        fig = style(build(k, d))
        try:
            st.plotly_chart(fig, width="stretch", theme=None)
        except TypeError:
            st.plotly_chart(fig, use_container_width=True, theme=None)
    info(k)


# ---- single-page grid: policy and prices, markets, fiscal and real economy ----
for left, right in [("key_rate", "cpi"), ("fx", "oil_gas"), ("balance", "gdp"), ("unemp", None)]:
    a, b = st.columns(2, gap="large")
    with a:
        cell(left)
    with b:
        if right:
            cell(right)
        else:
            st.markdown('<div class="cell-title">Refresh status by series</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"Series": SERIES[k]["title"], "Status": meta.get(k, {}).get("status", "never run"),
                                        "Latest obs.": meta.get(k, {}).get("latest_obs"),
                                        "Last success (UTC)": str(meta.get(k, {}).get("last_success", ""))[:16].replace("T", " ")}
                                       for k in SERIES]), hide_index=True)
            lp = D / "refresh_log.txt"
            if lp.exists():
                with st.expander("Refresh log (latest entries)"):
                    st.code("\n".join(lp.read_text().splitlines()[-25:]))
