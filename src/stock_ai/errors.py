"""The named errors from the API stage, each with the message the user sees."""


class StockAIError(Exception):
    """Base class. `message` is the plain-language text shown on the site."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotInSP500Error(StockAIError):
    def __init__(self, ticker: str):
        super().__init__(f"{ticker} isn't in the S&P 500. This site only trades S&P 500 stocks.")
        self.ticker = ticker


class InvalidSharesError(StockAIError):
    def __init__(self):
        super().__init__("Enter a whole number of shares, 1 or more.")


class NotEnoughCashError(StockAIError):
    def __init__(self, cost: float, cash: float):
        super().__init__(f"That would cost ${cost:,.2f} but you have ${cash:,.2f}. Try fewer shares.")
        self.cost = cost
        self.cash = cash


class NotEnoughSharesError(StockAIError):
    def __init__(self, ticker: str, owned: int):
        super().__init__(f"You own {owned} shares of {ticker}, so you can sell up to {owned}.")
        self.ticker = ticker
        self.owned = owned


class PriceUnavailableError(StockAIError):
    def __init__(self, ticker: str):
        super().__init__(
            f"We couldn't get a current price for {ticker}, so the trade wasn't placed. "
            "Try again in a minute."
        )
        self.ticker = ticker


class NotEnoughHistoryError(StockAIError):
    def __init__(self, ticker: str = "This stock"):
        super().__init__(
            f"{ticker} hasn't been trading long enough for a suggestion. "
            "It needs at least 1 year of prices. You can still trade it."
        )
        self.ticker = ticker


class DataUnavailableError(StockAIError):
    def __init__(self, saved_date: str | None = None):
        if saved_date:
            message = f"We couldn't download new data, so suggestions are from {saved_date}."
        else:
            message = (
                "We couldn't download stock data. Check your internet connection "
                "and try again in a few minutes."
            )
        super().__init__(message)
        self.saved_date = saved_date


JEV_NO_KEY = "Jev's explanation is turned off because no API key is set. See the README to add one."
JEV_FAILED = "Jev's explanation couldn't be loaded right now. The suggestion and numbers are not affected."
