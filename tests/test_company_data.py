"""Phase 2 company data: SEC financials, earnings, and the company inputs."""

import numpy as np
import pandas as pd
import pytest

from stock_ai import signals, storage
from stock_ai.data import earnings, financials
from tests.conftest import random_walk_prices


def quarter(label_entries, start, end, value, filed, form="10-Q"):
    label_entries.append({"start": start, "end": end, "val": value, "filed": filed, "form": form})


def fake_facts():
    """Made-up SEC facts. Revenue switches label in 2018; the fourth quarter of each
    year only appears inside the annual report; one figure is corrected later."""
    old_label, new_label, income, eps = [], [], [], []
    for year in range(2015, 2021):
        target = old_label if year < 2018 else new_label
        q_ends = [f"{year}-03-31", f"{year}-06-30", f"{year}-09-30"]
        q_starts = [f"{year}-01-01", f"{year}-04-01", f"{year}-07-01"]
        for i, (start, end) in enumerate(zip(q_starts, q_ends)):
            filed = (pd.Timestamp(end) + pd.Timedelta(days=35)).strftime("%Y-%m-%d")
            quarter(target, start, end, 100.0 + 10 * (year - 2015) + i, filed)
            quarter(income, start, end, 10.0 + (year - 2015), filed)
            quarter(eps, start, end, 1.0, filed)
        annual_filed = f"{year + 1}-02-20"
        quarter(target, f"{year}-01-01", f"{year}-12-31", 4 * (100.0 + 10 * (year - 2015)) + 10, annual_filed, "10-K")
        quarter(income, f"{year}-01-01", f"{year}-12-31", 4 * (10.0 + (year - 2015)), annual_filed, "10-K")
        quarter(eps, f"{year}-01-01", f"{year}-12-31", 4.0, annual_filed, "10-K")
    # A press release (8-K) with a different number: ignored.
    quarter(income, "2019-01-01", "2019-03-31", 999.0, "2019-04-20", "8-K")
    # The first quarter of 2019's profit is corrected in a later filing.
    quarter(income, "2019-01-01", "2019-03-31", 20.0, "2019-09-01", "10-Q")
    liabilities = [{"end": f"{y}-12-31", "val": 300.0, "filed": f"{y + 1}-02-20", "form": "10-K"} for y in range(2015, 2021)]
    equity = [{"end": f"{y}-12-31", "val": 150.0, "filed": f"{y + 1}-02-20", "form": "10-K"} for y in range(2015, 2021)]
    gaap = {
        "SalesRevenueNet": {"units": {"USD": old_label}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": new_label}},
        "NetIncomeLoss": {"units": {"USD": income}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
        "Liabilities": {"units": {"USD": liabilities}},
        "StockholdersEquity": {"units": {"USD": equity}},
    }
    return {"facts": {"us-gaap": gaap}}


@pytest.fixture(scope="module")
def extracted():
    return financials.extract(fake_facts())


# financials.py

def test_labels_are_combined_across_years(extracted):
    revenue = extracted[extracted["concept"] == "revenue"]
    assert revenue["period_end"].min() == pd.Timestamp("2015-03-31")
    assert revenue["period_end"].max() == pd.Timestamp("2020-12-31")
    assert revenue["period_end"].nunique() == 24  # 6 years x 4 quarters


def test_fourth_quarter_is_year_minus_three_quarters(extracted):
    revenue = extracted[extracted["concept"] == "revenue"].set_index("period_end")["value"]
    # 2016: quarters 110, 111, 112; year 4 x 110 + 10 = 450; fourth quarter 450 - 333 = 117
    assert revenue[pd.Timestamp("2016-12-31")] == pytest.approx(117.0)
    row = extracted[(extracted["concept"] == "revenue") & (extracted["period_end"] == "2016-12-31")]
    assert row["filed"].iloc[0] == pd.Timestamp("2017-02-20")


def test_press_releases_are_ignored(extracted):
    assert 999.0 not in set(extracted["value"])


def test_corrections_keep_both_values_with_their_dates(extracted):
    q1 = extracted[(extracted["concept"] == "net_income") & (extracted["period_end"] == "2019-03-31")]
    assert sorted(zip(q1["filed"].dt.strftime("%Y-%m-%d"), q1["value"])) == [
        ("2019-05-05", 14.0), ("2019-09-01", 20.0)]


def test_figures_are_never_known_before_they_are_filed(extracted):
    before = signals._known_values(extracted, "net_income", pd.Timestamp("2019-05-04"))
    assert pd.Timestamp("2019-03-31") not in before.index
    early = signals._known_values(extracted, "net_income", pd.Timestamp("2019-06-01"))
    late = signals._known_values(extracted, "net_income", pd.Timestamp("2019-09-01"))
    assert early[pd.Timestamp("2019-03-31")] == 14.0
    assert late[pd.Timestamp("2019-03-31")] == 20.0


def test_update_without_sec_contact_fails_cleanly(monkeypatch):
    from stock_ai.errors import DataUnavailableError
    with pytest.raises(DataUnavailableError):
        financials._headers()


def test_update_saves_and_reports(monkeypatch, sp500_saved):
    monkeypatch.setenv("SEC_CONTACT", "test@example.com")
    monkeypatch.setattr(financials, "_fetch_ticker_map", lambda: {"AAA": 1, "BBB": 2})
    monkeypatch.setattr(financials, "REQUEST_PAUSE_SECONDS", 0)

    def fetch(cik):
        if cik == 2:
            raise ConnectionError("refused")
        return fake_facts()
    monkeypatch.setattr(financials, "_fetch_facts", fetch)
    report = financials.update(["AAA", "BBB", "CCC"])
    assert report.updated == ["AAA"]
    assert "refused" in report.failed["BBB"]
    assert report.failed["CCC"] == "not in the SEC's ticker list"
    saved = storage.load_financials("AAA")
    assert len(saved) == len(financials.extract(fake_facts()))
    assert financials.coverage(["AAA"])["revenue"] == 1


# earnings.py

def test_earnings_clean_and_splits():
    raw = pd.DataFrame({
        "EPS Estimate": [1.0, 1.1, 1.2], "Reported EPS": [1.1, 1.0, None], "Surprise(%)": [10.0, -9.09, None],
    }, index=pd.DatetimeIndex(["2020-07-30 16:30", "2020-04-30 16:30", "2020-10-29 16:30"]).tz_localize("America/New_York"))
    table = earnings.clean(raw)
    assert list(table["announced"].dt.strftime("%Y-%m-%d")) == ["2020-04-30", "2020-07-30", "2020-10-29"]
    assert pd.isna(table["eps_reported"].iloc[-1])  # upcoming
    splits = earnings.clean_splits(pd.Series([4.0], index=pd.DatetimeIndex(["2020-08-31 09:30"]).tz_localize("America/New_York")))
    assert splits.to_dict("records") == [{"date": pd.Timestamp("2020-08-31"), "ratio": 4.0}]


# signals.py: company inputs

@pytest.fixture(scope="module")
def company_inputs(extracted):
    days = pd.bdate_range("2016-01-04", "2021-06-30")
    prices = random_walk_prices(np.random.default_rng(2), days, start=50.0)
    announcements = pd.DataFrame({
        "announced": pd.to_datetime(["2020-04-30 16:30", "2020-07-30 16:30", "2020-10-29 16:30"]),
        "eps_expected": [1.0, 1.0, 1.0], "eps_reported": [1.1, 0.9, None], "surprise_percent": [10.0, -10.0, None],
    })
    splits = pd.DataFrame({"date": pd.to_datetime(["2020-08-31"]), "ratio": [4.0]})
    table = signals.company_signals(prices, extracted, announcements, splits)
    return prices, table


def test_company_inputs_match_hand_calculation(company_inputs, extracted):
    prices, table = company_inputs
    day = pd.Timestamp("2020-06-01")  # latest filing known: 2020 Q1 (filed 2020-05-05)
    row = table.loc[day]
    rev = signals._known_values(extracted, "revenue", day)
    ttm, prior = rev.iloc[-4:].sum(), rev.iloc[-8:-4].sum()
    assert row["revenue_growth"] == pytest.approx(ttm / prior - 1)
    income = signals._known_values(extracted, "net_income", day)
    assert row["profit_margin"] == pytest.approx(income.iloc[-4:].sum() / ttm)
    assert row["debt_to_equity"] == pytest.approx(2.0)
    # Before the 4-for-1 split, the saved close is a quarter of the real price.
    assert row["pe_ratio"] == pytest.approx(prices.loc[day, "close"] * 4 / 4.0)


def test_pe_after_the_split_uses_the_price_as_is(company_inputs):
    prices, table = company_inputs
    day = pd.Timestamp("2020-09-15")
    assert table.loc[day, "pe_ratio"] == pytest.approx(prices.loc[day, "close"] / 4.0)


def test_earnings_surprise_used_from_the_next_trading_day(company_inputs):
    _, table = company_inputs
    assert table.loc[pd.Timestamp("2020-04-30"), "earnings_surprise"] != 10.0
    assert table.loc[pd.Timestamp("2020-05-01"), "earnings_surprise"] == 10.0
    assert table.loc[pd.Timestamp("2020-05-01"), "days_since_earnings"] == 1
    assert table.loc[pd.Timestamp("2020-07-31"), "earnings_surprise"] == -10.0
    # The upcoming announcement with no reported figures changes nothing.
    assert table.loc[pd.Timestamp("2020-11-02"), "earnings_surprise"] == -10.0


def test_filings_used_from_the_trading_day_after_filing(company_inputs, extracted):
    _, table = company_inputs
    # The 2019 annual report was filed on Thursday 2020-02-20; it counts from Friday.
    on_filing_day = table.loc[pd.Timestamp("2020-02-20"), "revenue_growth"]
    next_day = table.loc[pd.Timestamp("2020-02-21"), "revenue_growth"]
    assert on_filing_day != next_day


def test_company_inputs_never_see_the_future(company_inputs, extracted):
    prices, before = company_inputs
    cutoff = pd.Timestamp("2019-12-31")
    changed = extracted.copy()
    changed.loc[changed["filed"] > cutoff, "value"] *= 7
    announcements = pd.DataFrame({"announced": pd.to_datetime(["2020-04-30 16:30"]), "eps_expected": [1.0],
                                  "eps_reported": [5.0], "surprise_percent": [400.0]})
    splits = pd.DataFrame({"date": pd.to_datetime(["2020-08-31"]), "ratio": [4.0]})
    after = signals.company_signals(prices, changed, announcements, splits)
    pd.testing.assert_frame_equal(before.loc[:cutoff, signals.COMPANY_FEATURES[:5]],
                                  after.loc[:cutoff, signals.COMPANY_FEATURES[:5]])


def test_inputs_are_kept_in_range():
    days = pd.bdate_range("2016-01-04", "2021-06-30")
    prices = random_walk_prices(np.random.default_rng(2), days, start=5000.0)  # a huge P/E
    table = signals.company_signals(prices, financials.extract(fake_facts()), None, None)
    assert table["pe_ratio"].max() <= 200


def test_negative_equity_gives_no_debt_ratio():
    facts = fake_facts()
    for entry in facts["facts"]["us-gaap"]["StockholdersEquity"]["units"]["USD"]:
        entry["val"] = -10.0
    days = pd.bdate_range("2017-01-02", "2018-12-31")
    table = signals.company_signals(random_walk_prices(np.random.default_rng(1), days),
                                    financials.extract(facts), None, None)
    assert table["debt_to_equity"].isna().all()


def test_fill_company_gaps_uses_the_days_median_and_flags_it():
    days = pd.DatetimeIndex(["2020-01-02"] * 3 + ["2020-01-03"] * 3, name="date")
    table = pd.DataFrame({column: [1.0, 3.0, np.nan, 2.0, 4.0, 6.0] for column in signals.COMPANY_FEATURES},
                         index=days)
    filled = signals.fill_company_gaps(table)
    assert filled.iloc[2]["revenue_growth"] == 2.0  # median of 1 and 3
    assert list(filled["financials_missing"]) == [0, 0, 1, 0, 0, 0]
    assert not filled[signals.COMPANY_FEATURES].isna().any().any()
