"""
fetch_market_data.py

Fetch market indicators (CBS CPI, CBS house price index) and accumulate
historical snapshots in a JSON state file.

Usage:
    python3.13 fetch_market_data.py [--state-path PATH]

Output: JSON to stdout with latest values.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

# Default state file location. Override with MARKET_DATA_STATE env var or --state-path flag.
STATE_PATH = Path(os.environ.get(
    "MARKET_DATA_STATE",
    str(Path.home() / ".local/share/market-data-state.json"),
))

# CBS OData v3 API base URLs
# CPI: table 83131NED -- monthly CPI and year-on-year change
#   Dimension: Bestedingscategorieen = 'T001112  ' (Alle bestedingen)
#   Fields: CPI_1 (index), JaarmutatieCPI_5 (year-on-year % change)
# House price: table 85773NED -- monthly, Nederland only (no RegioS dimension)
#   Fields: PrijsindexVerkoopprijzen_1 (index, 2020=100),
#           OntwikkelingTOVEenJaarEerder_3 (year-on-year % change)
#
# Note: CBS OData v3 ignores $orderby on TypedDataSet, so we use $filter with
# substringof to fetch specific years and sort client-side.

CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"
CPI_TABLE = "83131NED"
HOUSE_TABLE = "85773NED"
YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
ECB_MRR_URL = (
    "https://data-api.ecb.europa.eu/service/data/"
    "FM/B.U2.EUR.4F.KR.MRR_FR.LEV?lastNObservations=12&format=jsondata"
)


def _build_cpi_url(year: int) -> str:
    """Build CBS OData URL for CPI data for a given year (monthly only)."""
    base = f"{CBS_BASE}/{CPI_TABLE}/TypedDataSet"
    filt = (
        f"Bestedingscategorieen eq 'T001112  ' and "
        f"substringof('{year}MM',Perioden)"
    )
    sel = "Perioden,CPI_1,JaarmutatieCPI_5"
    return f"{base}?$filter={quote(filt, safe='')}&$select={quote(sel, safe=',')}"


def _build_house_url(year: int) -> str:
    """Build CBS OData URL for house price index data for a given year (monthly only)."""
    base = f"{CBS_BASE}/{HOUSE_TABLE}/TypedDataSet"
    filt = f"substringof('{year}MM',Perioden)"
    sel = "Perioden,PrijsindexVerkoopprijzen_1,OntwikkelingTOVEenJaarEerder_3"
    return f"{base}?$filter={quote(filt, safe='')}&$select={quote(sel, safe=',')}"


def load_state(state_path=None) -> dict:
    """Load JSON state file, return empty dict if missing."""
    path = Path(state_path) if state_path is not None else STATE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshot(state_path, indicator: str, snapshot: dict):
    """Append snapshot to state, dedup by period key."""
    path = Path(state_path) if state_path is not None else STATE_PATH
    state = load_state(path)

    if indicator not in state:
        state[indicator] = []

    # Dedup by period
    period = snapshot.get("period")
    existing_periods = {s.get("period") for s in state[indicator]}
    if period not in existing_periods:
        state[indicator].append(snapshot)

    # Sort by period for readability
    state[indicator].sort(key=lambda s: s.get("period", ""))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _convert_cbs_period(period_str: str) -> str | None:
    """Convert CBS period format (e.g. '2026MM01') to 'YYYY-MM'."""
    if not period_str:
        return None
    if "MM" in period_str:
        parts = period_str.split("MM")
        if len(parts) == 2:
            return f"{parts[0]}-{parts[1]}"
    if "KW" in period_str:
        parts = period_str.split("KW")
        if len(parts) == 2:
            return f"{parts[0]}-Q{parts[1]}"
    return period_str


def parse_cbs_cpi(response: dict) -> list[dict]:
    """Parse CBS OData CPI response into list of {period, cpi, yoy_pct} dicts."""
    results = []
    for row in response.get("value", []):
        raw_period = row.get("Perioden", "")
        if "JJ" in raw_period:
            continue
        cpi_val = row.get("CPI_1")
        yoy_val = row.get("JaarmutatieCPI_5")
        if cpi_val is None and yoy_val is None:
            continue
        period = _convert_cbs_period(raw_period)
        if period:
            entry = {"period": period}
            if cpi_val is not None:
                try:
                    entry["cpi"] = float(cpi_val)
                except (ValueError, TypeError):
                    pass
            if yoy_val is not None:
                try:
                    entry["yoy_pct"] = float(yoy_val)
                except (ValueError, TypeError):
                    pass
            results.append(entry)
    return results


def parse_cbs_house_price(response: dict) -> list[dict]:
    """Parse CBS OData house price response into list of {period, index, yoy_pct} dicts."""
    results = []
    for row in response.get("value", []):
        raw_period = row.get("Perioden", "")
        if "JJ" in raw_period or "KW" in raw_period:
            continue
        idx_val = row.get("PrijsindexVerkoopprijzen_1")
        yoy_val = row.get("OntwikkelingTOVEenJaarEerder_3")
        if idx_val is None and yoy_val is None:
            continue
        period = _convert_cbs_period(raw_period)
        if period:
            entry = {"period": period}
            if idx_val is not None:
                try:
                    entry["index"] = float(idx_val)
                except (ValueError, TypeError):
                    pass
            if yoy_val is not None:
                try:
                    entry["yoy_pct"] = float(yoy_val)
                except (ValueError, TypeError):
                    pass
            results.append(entry)
    return results


def fetch_url(url: str, timeout: int = 15) -> dict | None:
    """GET JSON from URL, return None on any error."""
    try:
        req = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "vault-watcher/1.0",
            },
        )
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, OSError) as exc:
        print(f"[fetch_market_data] fetch_url error for {url}: {exc}", file=sys.stderr)
        return None


def _period_from_timestamp(ts: int | float | None) -> str | None:
    """Convert Unix timestamp to UTC YYYY-MM-DD period string."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _fetch_yahoo_with_yfinance(ticker: str) -> list[dict] | None:
    """Fetch latest daily closes via yfinance if the optional package is installed."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        history = yf.Ticker(ticker).history(period="1mo", interval="1d")
    except Exception as exc:
        print(f"[fetch_market_data] yfinance error for {ticker}: {exc}", file=sys.stderr)
        return None

    if history is None or history.empty or "Close" not in history:
        return None

    results = []
    for idx, close_val in history["Close"].tail(12).items():
        if close_val is None:
            continue
        try:
            close = float(close_val)
        except (ValueError, TypeError):
            continue

        try:
            period = idx.date().isoformat()
        except AttributeError:
            period = str(idx)[:10]

        if period:
            results.append({"period": period, "close": close})

    if not results:
        return None

    results.sort(key=lambda x: x["period"], reverse=True)
    return results


def _fetch_yahoo_chart(ticker: str) -> list[dict] | None:
    """Fetch latest daily closes from Yahoo Finance chart endpoint."""
    url = f"{YAHOO_CHART_BASE}/{quote(ticker, safe='')}?range=1mo&interval=1d"
    response = fetch_url(url)
    if response is None:
        return None

    try:
        chart = response["chart"]["result"][0]
        timestamps = chart.get("timestamp", [])
        closes = chart["indicators"]["quote"][0].get("close", [])
    except (KeyError, IndexError, TypeError):
        return None

    results = []
    for ts, close_val in zip(timestamps, closes):
        if close_val is None:
            continue
        period = _period_from_timestamp(ts)
        if not period:
            continue
        try:
            close = float(close_val)
        except (ValueError, TypeError):
            continue
        results.append({"period": period, "close": close})

    if not results:
        return None

    results.sort(key=lambda x: x["period"], reverse=True)
    return results[:12]


def fetch_yahoo_index(ticker: str) -> list[dict] | None:
    """Fetch latest 12 daily closes from Yahoo Finance."""
    yfinance_data = _fetch_yahoo_with_yfinance(ticker)
    if yfinance_data:
        return yfinance_data
    return _fetch_yahoo_chart(ticker)


def fetch_aex() -> list[dict] | None:
    """Fetch latest 12 daily AEX index closes from Yahoo Finance."""
    return fetch_yahoo_index("^AEX")


def fetch_sp500() -> list[dict] | None:
    """Fetch latest 12 daily S&P 500 index closes from Yahoo Finance."""
    return fetch_yahoo_index("^GSPC")


def parse_ecb_rate(response: dict) -> list[dict]:
    """Parse ECB SDMX-JSON response into list of {period, rate_pct} dicts."""
    try:
        observation_values = response["structure"]["dimensions"]["observation"][0]["values"]
        series = response["dataSets"][0]["series"]
    except (KeyError, IndexError, TypeError):
        return []

    if not series:
        return []

    results = []
    first_series = next(iter(series.values()))
    observations = first_series.get("observations", {})
    for obs_key, obs_val in observations.items():
        try:
            period = observation_values[int(obs_key)]["id"]
            rate = float(obs_val[0])
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        results.append({"period": period, "rate_pct": rate})

    results.sort(key=lambda x: x["period"], reverse=True)
    return results


def fetch_ecb_main_refinancing_rate() -> list[dict] | None:
    """Fetch latest ECB main refinancing rate observations from ECB SDW API."""
    response = fetch_url(ECB_MRR_URL)
    if response is None:
        return None

    results = parse_ecb_rate(response)
    if not results:
        return None

    return results[:12]


def fetch_cbs_cpi() -> list[dict] | None:
    """Fetch latest 12 months of CPI data from CBS Open Data API."""
    now = datetime.now()
    current_year = now.year
    all_data = []

    # Fetch current year and previous year to ensure we have 12 months
    for year in [current_year - 1, current_year]:
        url = _build_cpi_url(year)
        response = fetch_url(url)
        if response is not None:
            all_data.extend(parse_cbs_cpi(response))

    if not all_data:
        return None

    # Sort by period descending, take latest 12
    all_data.sort(key=lambda x: x["period"], reverse=True)
    return all_data[:12]


def fetch_cbs_house_price() -> list[dict] | None:
    """Fetch latest 12 months of house price index data from CBS Open Data API."""
    now = datetime.now()
    current_year = now.year
    all_data = []

    # Fetch current year and previous year
    for year in [current_year - 1, current_year]:
        url = _build_house_url(year)
        response = fetch_url(url)
        if response is not None:
            all_data.extend(parse_cbs_house_price(response))

    if not all_data:
        return None

    # Sort by period descending, take latest 12
    all_data.sort(key=lambda x: x["period"], reverse=True)
    return all_data[:12]


def fetch_all(state_path=None) -> dict:
    """Fetch all indicators, save snapshots, return latest values + fetched_at."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = {"fetched_at": fetched_at, "indicators": {}}

    cpi_data = fetch_cbs_cpi()
    if cpi_data:
        for snap in cpi_data:
            save_snapshot(state_path, "cbs_cpi", snap)
        result["indicators"]["cbs_cpi"] = cpi_data

    house_data = fetch_cbs_house_price()
    if house_data:
        for snap in house_data:
            save_snapshot(state_path, "cbs_house_price", snap)
        result["indicators"]["cbs_house_price"] = house_data

    aex_data = fetch_aex()
    if aex_data:
        for snap in aex_data:
            save_snapshot(state_path, "aex", snap)
        result["indicators"]["aex"] = aex_data

    sp500_data = fetch_sp500()
    if sp500_data:
        for snap in sp500_data:
            save_snapshot(state_path, "sp500", snap)
        result["indicators"]["sp500"] = sp500_data

    ecb_rate_data = fetch_ecb_main_refinancing_rate()
    if ecb_rate_data:
        for snap in ecb_rate_data:
            save_snapshot(state_path, "ecb_main_refinancing_rate", snap)
        result["indicators"]["ecb_main_refinancing_rate"] = ecb_rate_data

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch market indicators.")
    parser.add_argument("--state-path", default=None, help="Path to JSON state file")
    args = parser.parse_args()

    state_path = args.state_path or STATE_PATH
    output = fetch_all(state_path=state_path)
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
