import re
import subprocess
from pathlib import Path

from stock_ai import errors

ROOT = Path(__file__).resolve().parents[1]


def test_error_messages_fill_in_details():
    assert errors.NotInSP500Error("XYZ").message == "XYZ isn't in the S&P 500. This site only trades S&P 500 stocks."
    assert errors.InvalidSharesError().message == "Enter a whole number of shares, 1 or more."
    assert errors.NotEnoughCashError(1234.5, 1000).message == (
        "That would cost $1,234.50 but you have $1,000.00. Try fewer shares.")
    assert errors.NotEnoughSharesError("XYZ", 3).message == "You own 3 shares of XYZ, so you can sell up to 3."
    assert "current price for XYZ" in errors.PriceUnavailableError("XYZ").message
    assert errors.NotEnoughHistoryError("XYZ").message.startswith("XYZ hasn't been trading long enough")
    assert errors.DataUnavailableError("2024-01-02").message == (
        "We couldn't download new data, so suggestions are from 2024-01-02.")
    assert "Check your internet connection" in errors.DataUnavailableError().message


# QA section 6: secrets

SECRET_SHAPE = re.compile(r"(sk-ant-|ghp_|github_pat_)[A-Za-z0-9_\-]{20,}")


def tracked_and_new_files():
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / name for name in listed if (ROOT / name).is_file()]


def test_no_credentials_in_project_files():
    found = []
    for path in tracked_and_new_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if SECRET_SHAPE.search(text):
            found.append(str(path.relative_to(ROOT)))
    assert found == [], f"Something shaped like a key or token is in: {found}"


def test_env_is_ignored_and_example_has_no_values():
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ignored
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, _, value = line.partition("=")
            assert value.strip() == "", f"{name} has a value in .env.example"


def test_data_folder_is_ignored():
    assert subprocess.run(["git", "check-ignore", "-q", "data/x.csv"], cwd=ROOT).returncode == 0
