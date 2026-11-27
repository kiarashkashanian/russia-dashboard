"""Fetchers + metadata for every series. Each fetcher returns a DataFrame with a 'date' column."""
import io, os, re, time, datetime as dt
import xml.etree.ElementTree as ET
import lxml.html, pandas as pd, requests

H = {"User-Agent": "Mozilla/5.0 (Russia economy dashboard; university assignment)"}
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BROWSER = {"User-Agent": CHROME, "Accept": "application/json,text/csv,text/plain,*/*", "Accept-Language": "en-US,en;q=0.9"}
IMF_H = {**BROWSER, "Referer": "https://www.imf.org/external/datamapper/"}
TODAY = dt.date.today()


def _get(url, headers=None, timeout=(10, 60), tries=2):
    err = None
    for _ in range(tries):
        try:
            r = requests.get(url, headers=headers or H, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            err = e
            time.sleep(2)
    raise err


def _cbr_rows(url, date_pattern):
    """Parse a CBR HTML table as plain text (pandas would turn '14,00' into 1400 and '05.2026' into a decimal)."""
    doc = lxml.html.fromstring(_get(url).content)
    rows = [[c.text_content().strip().replace("\xa0", "") for c in tr.xpath("./td")] for tr in doc.xpath("//table//tr")]
    good = [r for r in rows if r and re.fullmatch(date_pattern, r[0])]
    if not good:
        raise ValueError(f"unexpected CBR table layout, first rows: {rows[:3]}")
    return good


def _f(x):
    return float(x.replace(",", ".").replace(" ", ""))


def key_rate():
    u = ("https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True"
         f"&UniDbQuery.From=01.01.2013&UniDbQuery.To={TODAY:%d.%m.%Y}")
    rows = _cbr_rows(u, r"\d{2}\.\d{2}\.\d{4}")  # date, rate
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows], format="%d.%m.%Y"),
                         "value": [_f(r[1]) for r in rows]}).sort_values("date")


def cpi():
    u = ("https://www.cbr.ru/hd_base/infl/?UniDbQuery.Posted=True"
         f"&UniDbQuery.From=01.2013&UniDbQuery.To={TODAY:%m.%Y}")
    rows = _cbr_rows(u, r"\d{2}\.\d{4}")  # date MM.YYYY, key rate, inflation y/y, target
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows], format="%m.%Y"),
                         "value": [_f(r[2]) for r in rows]}).sort_values("date")


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
    """FRED API if FRED_API_KEY is set, otherwise the public CSV endpoint (browser-style headers; FRED drops bot-like clients)."""
    df, key = None, os.environ.get("FRED_API_KEY")
    if key:
        try:
            j = _get("https://api.stlouisfed.org/fred/series/observations?series_id=" + sid + "&api_key=" + key
                     + "&file_type=json&observation_start=2013-01-01", headers=BROWSER).json()
            df = pd.DataFrame(j["observations"])[["date", "value"]]
            df.columns = ["date", sid]
        except Exception:
            df = None
    if df is None:
        u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2013-01-01"
        df = pd.read_csv(io.StringIO(_get(u, headers=BROWSER, tries=3).text))
        df.columns = ["date", sid]
    df["date"] = pd.to_datetime(df["date"])
    df[sid] = pd.to_numeric(df[sid], errors="coerce")
    return df.dropna()


def oil_gas():
    d = _fred("DCOILBRENTEU").merge(_fred("PNGASEUUSDM"), on="date", how="outer").sort_values("date")
    return d.rename(columns={"DCOILBRENTEU": "brent", "PNGASEUUSDM": "gas"})


_S, _warm = requests.Session(), []


def _imf_get(url):
    """The IMF blocks bot-like first requests: reuse one session, warm it up, retry with backoff."""
    if not _warm:
        _warm.append(1)
        try:
            _S.get("https://www.imf.org/external/datamapper/", headers=IMF_H, timeout=20)
        except requests.RequestException:
            pass
    err = None
    for wait in (0, 3, 8):
        time.sleep(wait)
        try:
            r = _S.get(url, headers=IMF_H, timeout=(10, 90))
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            err = e
    raise err


def _imf(code):
    d = _imf_get(f"https://www.imf.org/external/datamapper/api/v1/{code}/RUS").json()["values"][code]["RUS"]
    df = pd.DataFrame({"date": pd.to_datetime([f"{y}-12-31" for y in d]), "value": list(d.values())})
    df = df[df["date"].dt.year >= 2005].sort_values("date")
    df["forecast"] = df["date"].dt.year >= TODAY.year  # IMF estimates/projections
    return df


def _wb(indicators):
    errs = []
    for ind in indicators:
        try:
            j = _get(f"https://api.worldbank.org/v2/country/RUS/indicator/{ind}?format=json&per_page=200", headers=BROWSER).json()
            rows = [(pd.Timestamp(f"{r['date']}-12-31"), r["value"]) for r in (j[1] if len(j) > 1 and j[1] else [])
                    if r["value"] is not None and int(r["date"]) >= 2005]
            if rows:
                df = pd.DataFrame(rows, columns=["date", "value"]).sort_values("date")
                df["forecast"] = False
                return df
            errs.append(f"{ind}: no data ({str(j[0])[:80]})")
        except Exception as e:
            errs.append(f"{ind}: {type(e).__name__}")
    raise ValueError("World Bank fallback failed: " + "; ".join(errs))


WB_FALLBACK = {"GGXCNL_NGDP": ["GC.BAL.CASH.GD.ZS", "GC.NLD.TOTL.GD.ZS"], "NGDP_RPCH": ["NY.GDP.MKTP.KD.ZG"], "LUR": ["SL.UEM.TOTL.ZS"]}


def annual(code):
    """IMF DataMapper first; if the IMF blocks the request, fall back to the World Bank API."""
    try:
        df, src = _imf(code), "IMF DataMapper (WEO)"
    except Exception as e:
        try:
            df, src = _wb(WB_FALLBACK[code]), f"World Bank WDI (IMF unavailable: {type(e).__name__})"
        except Exception as e2:
            raise RuntimeError(f"IMF: {type(e).__name__}: {e} | {e2}")
    df.attrs["source"] = src
    return df


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
    "balance": dict(fn=lambda: annual("GGXCNL_NGDP"), title="Budget balance", units="% of GDP (negative = deficit)", freq="Annual",
        source="IMF DataMapper (World Bank fallback)", url="https://www.imf.org/external/datamapper/GGXCNL_NGDP@WEO/RUS",
        note="IMF: general government balance. World Bank fallback: central government cash balance. Faded bars = IMF estimate/projection."),
    "gdp": dict(fn=lambda: annual("NGDP_RPCH"), title="Real GDP growth", units="% change vs previous year", freq="Annual",
        source="IMF DataMapper (World Bank fallback)", url="https://www.imf.org/external/datamapper/NGDP_RPCH@WEO/RUS", note="None. Faded bars = IMF estimate/projection."),
    "unemp": dict(fn=lambda: annual("LUR"), title="Unemployment rate", units="% of labor force", freq="Annual",
        source="IMF DataMapper (World Bank fallback)", url="https://www.imf.org/external/datamapper/LUR@WEO/RUS", note="None. Faded bars = IMF estimate/projection."),
}
