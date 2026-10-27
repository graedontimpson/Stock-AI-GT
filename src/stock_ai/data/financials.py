"""Company financials from SEC EDGAR "company facts".

Every figure keeps the date it was filed, and is only ever used from then on.
Details in 06_phase2/output.md section 4.
"""

import time
from dataclasses import dataclass, field

import pandas as pd
import requests

from stock_ai import storage
from stock_ai.config import load_settings
from stock_ai.errors import DataUnavailableError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
REQUEST_PAUSE_SECONDS = 0.2  # at most 5 requests a second; the SEC allows 10

# Labels companies use for each concept, in order of preference. For each period the
# value comes from the first label that has one, because companies switch labels.
CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}
FLOW = {"revenue", "net_income", "eps_diluted"}  # cover a period; the rest are a point in time
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)


@dataclass
class UpdateReport:
    updated: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)


def _headers() -> dict:
    contact = load_settings().sec_contact
    if not contact:
        raise DataUnavailableError()
    return {"User-Agent": f"stock-ai {contact}"}


def _fetch_ticker_map() -> dict[str, int]:
    response = requests.get(TICKERS_URL, headers=_headers(), timeout=30)
    response.raise_for_status()
    return {row["ticker"]: int(row["cik_str"]) for row in response.json().values()}


def _fetch_facts(cik: int) -> dict:
    response = requests.get(FACTS_URL.format(cik=cik), headers=_headers(), timeout=60)
    response.raise_for_status()
    return response.json()


def _entries(facts: dict, label: str) -> list[dict]:
    units = facts.get("facts", {}).get("us-gaap", {}).get(label, {}).get("units", {})
    for unit in ("USD", "USD/shares"):
        if unit in units:
            return units[unit]
    return []


def _quarters(entries: list[dict]) -> pd.DataFrame:
    """Quarterly values for a flow concept. The fourth quarter is the full year
    minus the three quarters inside it, dated when the annual report was filed."""
    table = pd.DataFrame(entries)
    if table.empty or "start" not in table:
        return pd.DataFrame(columns=["period_end", "value", "filed"])
    table = table[table["form"].isin(FORMS)].copy()
    table["start"] = pd.to_datetime(table["start"])
    table["end"] = pd.to_datetime(table["end"])
    table["filed"] = pd.to_datetime(table["filed"])
    table["days"] = (table["end"] - table["start"]).dt.days
    quarters = table[table["days"].between(*QUARTER_DAYS)]
    years = table[table["days"].between(*YEAR_DAYS)]

    rows = [{"period_end": r.end, "value": r.val, "filed": r.filed} for r in quarters.itertuples()]
    first_filed = quarters.groupby("end")["filed"].min() if not quarters.empty else pd.Series(dtype="datetime64[ns]")
    for year in years.sort_values("filed").drop_duplicates(["start", "end"]).itertuples():
        inside = quarters[(quarters["start"] >= year.start - pd.Timedelta(days=7)) & (quarters["end"] < year.end)]
        inside = inside.sort_values("filed").drop_duplicates("end")
        if len(inside) != 3 or year.end in set(first_filed.index):
            continue
        rows.append({"period_end": year.end, "value": year.val - inside["val"].sum(), "filed": year.filed})
    return pd.DataFrame(rows, columns=["period_end", "value", "filed"])


def _points(entries: list[dict]) -> pd.DataFrame:
    table = pd.DataFrame(entries)
    if table.empty:
        return pd.DataFrame(columns=["period_end", "value", "filed"])
    table = table[table["form"].isin(FORMS)]
    return pd.DataFrame({
        "period_end": pd.to_datetime(table["end"]),
        "value": table["val"].astype(float),
        "filed": pd.to_datetime(table["filed"]),
    })


def extract(facts: dict) -> pd.DataFrame:
    """One row per (concept, period_end, value) with the first date that value was filed.

    A value that is later corrected appears again with the new value and its own
    filed date, so the correction is only used from then on."""
    frames = []
    for concept, labels in CONCEPTS.items():
        covered = set()
        for label in labels:
            entries = _entries(facts, label)
            rows = _quarters(entries) if concept in FLOW else _points(entries)
            rows = rows[~rows["period_end"].isin(covered)]
            if rows.empty:
                continue
            covered |= set(rows["period_end"])
            rows = rows.assign(concept=concept)
            frames.append(rows)
    if not frames:
        return pd.DataFrame(columns=["concept", "period_end", "value", "filed"])
    table = pd.concat(frames)[["concept", "period_end", "value", "filed"]]
    table = table.sort_values("filed").drop_duplicates(["concept", "period_end", "value"], keep="first")
    return table.sort_values(["concept", "period_end", "filed"]).reset_index(drop=True)


def update(tickers: list[str], refresh: bool = False, progress=None) -> UpdateReport:
    """Download and save financials for each ticker. Done weekly; a ticker saved in the
    last 7 days is skipped unless refresh=True."""
    report = UpdateReport()
    ciks = _fetch_ticker_map()
    for number, ticker in enumerate(tickers, start=1):
        if progress and number % 50 == 1:
            progress(f"Downloading company financials: {number} of {len(tickers)}")
        if not refresh and storage.saved_within_days(storage.financials_path(ticker), 7):
            continue
        cik = ciks.get(ticker)
        if cik is None:
            report.failed[ticker] = "not in the SEC's ticker list"
            continue
        try:
            table = extract(_fetch_facts(cik))
        except Exception as error:
            report.failed[ticker] = f"download failed: {error}"
            continue
        finally:
            time.sleep(REQUEST_PAUSE_SECONDS)
        storage.save_financials(ticker, table)
        report.updated.append(ticker)
    return report


def coverage(tickers: list[str]) -> dict[str, int]:
    """How many tickers have at least 8 quarters (or points) of each concept."""
    counts = {concept: 0 for concept in CONCEPTS}
    for ticker in tickers:
        table = storage.load_financials(ticker)
        if table is None:
            continue
        for concept in CONCEPTS:
            if table.loc[table["concept"] == concept, "period_end"].nunique() >= 8:
                counts[concept] += 1
    return counts
