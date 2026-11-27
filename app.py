import json, pathlib, random
import pandas as pd, plotly.graph_objects as go, streamlit as st
from plotly.subplots import make_subplots
from data_sources import SERIES

RED, BLUE, GOLD, SNOW = "#D52B1E", "#3B6FE0", "#E8B923", "#F4F8FF"
D = pathlib.Path(__file__).parent / "data"
st.set_page_config(page_title="Россия: Economic Monitor", page_icon="🪆", layout="wide")

random.seed(7)
flakes = "".join(f'<i style="left:{random.randint(0,100)}vw;font-size:{random.randint(10,26)}px;'
                 f'animation-duration:{random.randint(9,20)}s;animation-delay:-{random.randint(0,20)}s">❄</i>' for _ in range(45))
domes = "".join(f'<g transform="translate({x} {y}) scale({s})"><use href="#d" fill="{c}"/></g>'
                for x, y, s, c in [(300, 64, 1.5, GOLD), (222, 82, 1.1, RED), (378, 82, 1.1, BLUE),
                                   (150, 96, .85, "#1E8C4E"), (450, 96, .85, GOLD), (80, 104, .6, RED), (520, 104, .6, BLUE)])
towers = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{120-y}" fill="#8B1A1A"/>'
                 for x, y, w in [(284, 70, 32), (208, 86, 28), (364, 86, 28), (140, 98, 20), (440, 98, 20), (73, 106, 14), (513, 106, 14)])
skyline = (f'<svg viewBox="0 0 600 120" style="width:100%;max-width:760px;display:block;margin:0 auto">'
           f'<defs><path id="d" d="M0 40C-26 28-18 8 0 -16C18 8 26 28 0 40Z"/></defs>{towers}{domes}'
           f'<rect x="0" y="118" width="600" height="2" fill="{GOLD}"/></svg>')

st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Ruslan+Display&family=PT+Sans:wght@400;700&display=swap');
.stApp{{background:radial-gradient(ellipse at top,#16357A 0%,#0A1A3C 55%,#060F26 100%);font-family:'PT Sans',sans-serif}}
h1,h2,h3,.ru{{font-family:'Ruslan Display',serif!important;letter-spacing:.5px}}
.tri{{height:22px;border-radius:4px;background:linear-gradient(#fff 33.3%,#0039A6 33.3% 66.6%,#D52B1E 66.6%);box-shadow:0 0 18px rgba(255,255,255,.35)}}
.hero{{text-align:center;padding:10px 0 4px}}
.hero h1{{font-size:3.4rem;margin:.2rem 0;background:linear-gradient(90deg,#fff,{GOLD},#fff);-webkit-background-clip:text;color:transparent}}
.hero p{{color:#BFD0F5;font-size:1.1rem;margin:0 0 6px}}
.sec{{margin:42px 0 6px;padding:8px 16px;border-left:12px solid {RED};border-image:linear-gradient(#fff,#0039A6,{RED}) 1;background:rgba(255,255,255,.06)}}
.sec span{{font-size:2rem}} .sec b{{font-family:'Ruslan Display';font-size:1.7rem;margin-left:10px}} .sec em{{color:#BFD0F5;margin-left:12px}}
.snow{{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}}
.snow i{{position:absolute;top:-40px;color:#fff;opacity:.75;animation:fall linear infinite}}
@keyframes fall{{to{{transform:translateY(112vh) rotate(360deg)}}}}
@media (prefers-reduced-motion:reduce){{.snow{{display:none}}}}
[data-testid="stMetric"]{{background:rgba(255,255,255,.08);border-top:5px solid {GOLD};border-radius:10px;padding:10px 14px}}
</style><div class="snow">{flakes}</div>""", unsafe_allow_html=True)

meta = json.loads((D / "meta.json").read_text()) if (D / "meta.json").exists() else {}
st.markdown(f'<div class="tri"></div><div class="hero">{skyline}<h1>РОССИЯ 🪆 Economic Monitor</h1>'
            f'<p>Rates, prices, the ruble, oil, the budget and the people, from official and international sources</p></div>'
            f'<div class="tri"></div>', unsafe_allow_html=True)

start = st.sidebar.select_slider("Show data from year", options=[2005, 2010, 2013, 2016, 2020, 2022], value=2013)
st.sidebar.markdown("**Last successful data refresh (UTC)**")
st.sidebar.code(meta.get("_last_run", "never"))
st.sidebar.caption("This is when the refresh job last ran. Each chart also shows its own latest observation date.")


def load(k):
    p = D / f"{k}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    return df[df["date"].dt.year >= start]


def sec(emoji, ru, en):
    st.markdown(f'<div class="sec"><span>{emoji}</span><b>{ru}</b><em>{en}</em></div>', unsafe_allow_html=True)


def info(k):
    s, m = SERIES[k], meta.get(k, {})
    st.caption(f"**Units:** {s['units']}  \n**Frequency:** {s['freq']}  \n**Source:** [{s['source']}]({s['url']})  \n"
               f"**Latest observation:** {m.get('latest_obs', 'n/a')}  \n**Last successful refresh (UTC):** {m.get('last_success', 'never')}  \n"
               f"**Transformation:** {s['note']}")
    if m.get("status") == "failed":
        st.warning(f"Latest refresh failed ({m.get('error')}). Showing cached data from {m.get('last_success', 'n/a')}.")


def style(fig, h=380):
    fig.update_layout(height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.04)", font_color=SNOW,
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12), hovermode="x unified")
    fig.update_xaxes(gridcolor="rgba(255,255,255,.1)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.1)")
    return fig


def show(k, fig):
    if fig is None:
        st.error("No data yet. Run refresh.py or trigger the GitHub Action.")
    else:
        st.plotly_chart(style(fig), use_container_width=True)
    info(k)


def line(df, cols, **kw):
    f = go.Figure()
    for c, name, color in cols:
        d = df.dropna(subset=[c])
        f.add_trace(go.Scatter(x=d["date"], y=d[c], name=name, line=dict(color=color, width=2.5), **kw))
    return f


def annual(df, name):
    colors = [(RED if v < 0 else BLUE) for v in df["value"]]
    f = go.Figure(go.Bar(x=df["date"].dt.year, y=df["value"], marker_color=colors, name=name,
                         marker_opacity=[0.4 if x else 1 for x in df["forecast"]]))
    return f


data = {k: load(k) for k in SERIES}


def last(k, col, fmt):
    d = data[k]
    if d is None:
        return "n/a", None
    s = d[col].dropna()
    return fmt.format(s.iloc[-1]), (f"{s.iloc[-1]-s.iloc[-2]:+.2f}" if len(s) > 1 else None)


c = st.columns(4)
for col, (lab, k, cn, fmt) in zip(c, [("Key rate", "key_rate", "value", "{:.2f}%"), ("Inflation y/y", "cpi", "value", "{:.1f}%"),
                                      ("RUB per USD", "fx", "usd", "{:.2f}"), ("Brent, USD/bbl", "oil_gas", "brent", "{:.1f}")]):
    v, dlt = last(k, cn, fmt)
    col.metric(lab, v, dlt, delta_color="off")

sec("🏦", "Ключевая ставка", "1. Key policy rate")
d = data["key_rate"]
show("key_rate", None if d is None else line(d, [("value", "Key rate", RED)], line_shape="hv"))

sec("🛒", "Инфляция", "2. Consumer prices")
d = data["cpi"]
fig = None if d is None else line(d, [("value", "CPI y/y", GOLD)])
if fig is not None:
    fig.add_hline(y=4, line_dash="dash", line_color=SNOW, annotation_text="CBR target 4%")
show("cpi", fig)

sec("💱", "Рубль", "3. Ruble vs USD and CNY (higher = weaker ruble)")
d = data["fx"]
show("fx", None if d is None else line(d, [("usd", "RUB per USD", RED), ("cny", "RUB per CNY", GOLD)]))

sec("🛢️", "Нефть и газ", "4. Oil and gas prices")
d = data["oil_gas"]
fig = None
if d is not None:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    b, g = d.dropna(subset=["brent"]), d.dropna(subset=["gas"])
    fig.add_trace(go.Scatter(x=b["date"], y=b["brent"], name="Brent, USD/bbl", line=dict(color=SNOW, width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=g["date"], y=g["gas"], name="EU gas, USD/MMBtu", line=dict(color=GOLD, width=3)), secondary_y=True)
show("oil_gas", fig)

sec("🧾", "Бюджет", "5. Budget balance")
d = data["balance"]
show("balance", None if d is None else annual(d, "Balance, % of GDP"))

sec("🏭", "Рост экономики", "6. Real GDP growth")
d = data["gdp"]
show("gdp", None if d is None else annual(d, "GDP growth, %"))

sec("👷", "Безработица", "7. Unemployment")
d = data["unemp"]
show("unemp", None if d is None else annual(d, "Unemployment, %"))

st.markdown('<div class="tri" style="margin-top:40px"></div>', unsafe_allow_html=True)
with st.expander("Refresh status for every series"):
    st.dataframe(pd.DataFrame([{"series": SERIES[k]["title"], "status": meta.get(k, {}).get("status", "never run"),
                                "latest observation": meta.get(k, {}).get("latest_obs"),
                                "last successful refresh (UTC)": meta.get(k, {}).get("last_success"),
                                "error": meta.get(k, {}).get("error")} for k in SERIES]), hide_index=True)
