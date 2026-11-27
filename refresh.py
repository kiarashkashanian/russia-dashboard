"""Fetch all series, cache to data/*.csv, record status. Failed series keep their last good CSV.
Used by the GitHub Action (python refresh.py) and by the app's 'Refresh data now' button."""
import json, sys, datetime as dt, pathlib
from data_sources import SERIES

D = pathlib.Path(__file__).parent / "data"


def run():
    D.mkdir(exist_ok=True)
    meta_p = D / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines, fails = [f"=== Refresh run {now} ==="], 0
    for k, s in SERIES.items():
        m = meta.setdefault(k, {})
        try:
            df = s["fn"]()
            if df.empty:
                raise ValueError("source returned no rows")
            df.to_csv(D / f"{k}.csv", index=False)
            obs = df[~df["forecast"]] if "forecast" in df.columns else df
            m.update(status="ok", last_success=now, latest_obs=str(obs["date"].max().date()), error=None,
                     source_used=df.attrs.get("source"))
            for c in [c for c in df.columns if c not in ("date", "forecast")]:
                r = obs.dropna(subset=[c]).iloc[-1]
                lines.append(f"OK   {k}.{c}: latest {r['date'].date()} = {r[c]}  (source: {s['url']})")
        except Exception as e:
            fails += 1
            m.update(status="failed", error=f"{type(e).__name__}: {e}"[:300])
            lines.append(f"FAIL {k}: {m['error']} (keeping cached data)")
    meta["_last_run"] = now
    meta_p.write_text(json.dumps(meta, indent=2))
    with open(D / "refresh_log.txt", "a") as f:
        f.write("\n".join(lines) + "\n")
    return lines, fails


if __name__ == "__main__":
    out, n = run()
    print("\n".join(out))
    sys.exit(1 if n else 0)
