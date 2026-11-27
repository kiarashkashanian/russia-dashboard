"""Fetchers + metadata for every series. Each fetcher returns a DataFrame with a 'date' column."""
import io, datetime as dt
import xml.etree.ElementTree as ET
import pandas as pd, requests

H = {"User-Agent": "Mozilla/5.0 (Russia economy dashboard; university assignment)"}
TODAY = dt.date.today()


def _get(url):
    r = requests.get(url, headers=H, timeout=40)
    r.raise_for_status()
    return r


def key_rate():
    u = ("https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True"
         f"&UniDbQuery.From=01.01.2013&UniDbQuery.To={TODAY:%d.%m.%Y}")
    t = pd.read_html(io.StringIO(_get(u).text))[0]
    return pd.DataFrame({
        "date": pd.to_datetime(t.iloc[:, 0], format="%d.%m.%Y"),
        "value": pd.to_numeric(t.iloc[:, 1].astype(str).str.replace(",", ".")),
    }).sort_values("date")


def cpi():
    u = ("https://www.cbr.ru/hd_base/infl/?UniDbQuery.Posted=True"
         f"&UniDbQuery.From=01.2013&UniDbQuery.To={TODAY:%m.%Y}")
    t = pd.read_html(io.StringIO(_get(u).text))[0]
    # columns on the CBR page: date, key rate, inflation y/y, target
    return pd.DataFrame({
        "date": pd.to_datetime(t.iloc[:, 0], format="%m.%Y"),
        "value": pd.to_numeric(t.iloc[:, 2].astype(str).str.replace(",", ".")),
    }).sort_values("date")


def _fx(code):
    u = ("https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1=01/01/2013"
         f"&date_req2={TODAY:%d/%m/%Y}&VAL_NM_RQ={code}")
    root = ET.fromstring(_get(u).content)
    rows = [(pd.to_datetime(r.get("Date"), format="%d.%m.%Y"),
             float(r.find("Value").text.replace(",", ".")) / int(r.find("Nominal").text))
            for r in root.iter("Record")]  # divide by Nominal -> RUB per 1 unit
    return pd.DataFrame(rows, columns=["date", code])


def fx():
    d = _fx("R01235").merge(_fx("R01375"), on="date", how="outer").sort_values("date")
    return d.rename(columns={"R01235": "usd", "R01375": "cny"})


def _fred(sid):
    df = pd.read_csv(io.StringIO(_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}").text))
    df.columns = ["date", sid]
    df["date"] = pd.to_datetime(df["date"])
    df[sid] = pd.to_numeric(df[sid], errors="coerce")
    return df.dropna()


def oil_gas():
    d = _fred("DCOILBRENTEU").merge(_fred("PNGASEUUSDM"), on="date", how="outer").sort_values("date")
    return d.rename(columns={"DCOILBRENTEU": "brent", "PNGASEUUSDM": "gas"})


def _imf(code):
    d = _get(f"https://www.imf.org/external/datamapper/api/v1/{code}/RUS").json()["values"][code]["RUS"]
    df = pd.DataFrame({"date": pd.to_datetime([f"{y}-12-31" for y in d]), "value": list(d.values())})
    df["forecast"] = df["date"].dt.year >= TODAY.year  # IMF estimates/projections
    return df.sort_values("date")


SERIES = {
    "key_rate": dict(fn=key_rate, title="Key policy rate", units="% per year", freq="Daily series (changes at ~8 board meetings a year)",
        source="Bank of Russia", url="https://www.cbr.ru/hd_base/KeyRate/", note="None; level as published."),
    "cpi": dict(fn=cpi, title="CPI inflation", units="% change vs same month a year earlier", freq="Monthly",
        source="Bank of Russia (Rosstat data)", url="https://www.cbr.ru/hd_base/infl/", note="None; y/y rate as published. Dashed line = 4% CBR target."),
    "fx": dict(fn=fx, title="Ruble exchange rates", units="RUB per 1 USD / per 1 CNY (higher = weaker ruble)", freq="Daily (official CBR rate)",
        source="Bank of Russia", url="https://www.cbr.ru/currency_base/dynamics/", note="CBR quotes CNY per 10 units; divided by the Nominal field to give RUB per 1 CNY."),
    "oil_gas": dict(fn=oil_gas, title="Oil and gas prices", units="Brent: USD per barrel (left). EU gas: USD per MMBtu (right)", freq="Brent daily; EU gas monthly",
        source="FRED: U.S. EIA (Brent), IMF (EU gas)", url="https://fred.stlouisfed.org/series/DCOILBRENTEU",
        note="None. Brent is a proxy: Urals sells at a discount and has no free API. Gas is monthly and lags."),
    "balance": dict(fn=lambda: _imf("GGXCNL_NGDP"), title="Budget balance (general government)", units="% of GDP (negative = deficit)", freq="Annual",
        source="IMF DataMapper (WEO)", url="https://www.imf.org/external/datamapper/GGXCNL_NGDP@WEO/RUS",
        note="IMF general-government balance, not federal-only. Faded bars = IMF estimate/projection."),
    "gdp": dict(fn=lambda: _imf("NGDP_RPCH"), title="Real GDP growth", units="% change vs previous year", freq="Annual",
        source="IMF DataMapper (WEO)", url="https://www.imf.org/external/datamapper/NGDP_RPCH@WEO/RUS", note="None. Faded bars = IMF estimate/projection."),
    "unemp": dict(fn=lambda: _imf("LUR"), title="Unemployment rate", units="% of labor force", freq="Annual",
        source="IMF DataMapper (WEO)", url="https://www.imf.org/external/datamapper/LUR@WEO/RUS", note="None. Faded bars = IMF estimate/projection."),
}
