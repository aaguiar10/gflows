from requests.cookies import create_cookie
import yfinance.data as _data
from yfinance import Ticker, Tickers
from curl_cffi import requests as curl_requests


def _wrap_cookie(cookie, session):
    """
    If cookie is just a str (cookie name), look up its value
    in session.cookies and wrap it into a real Cookie object.
    """
    if isinstance(cookie, str):
        value = session.cookies.get(cookie)
        return create_cookie(name=cookie, value=value)
    return cookie


def patch_yf():
    """
    Monkey-patch YfData._get_cookie_basic so that
    it always returns a proper Cookie object,
    even when response.cookies is a simple dict.
    """
    original = _data.YfData._get_cookie_basic

    def _patched(self, timeout=30):
        cookie = original(self, timeout)
        return _wrap_cookie(cookie, self._session)

    _data.YfData._get_cookie_basic = _patched


def _get_session():
    """Creates and returns a curl_cffi session."""
    return curl_requests.Session(impersonate="chrome")


def yf_ticker(symbol, **kwargs):
    """
    Creates a yfinance Ticker object with a pre-configured session.

    Args:
        symbol (str): The ticker symbol.
        **kwargs: Additional keyword arguments to pass to yf.Ticker.

    Returns:
        yf.Ticker: An initialized Ticker object.
    """
    session = _get_session()
    return Ticker(symbol, session=session, **kwargs)


def yf_tickers(symbols, **kwargs):
    """
    Creates a yfinance Tickers object with a pre-configured session.

    Args:
        symbols (list or str): A list of ticker symbols or a space-separated string.
        **kwargs: Additional keyword arguments to pass to yf.Tickers.

    Returns:
        yf.Tickers: An initialized Tickers object.
    """
    session = _get_session()
    return Tickers(symbols, session=session, **kwargs)
