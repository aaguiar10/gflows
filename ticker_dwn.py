import requests
import base64
import orjson
from multiprocessing.dummy import Pool as ThreadPool
from datetime import datetime
from os import environ, getcwd
from pathlib import Path


def fulfill_req(ticker, expiry):
    api_url = environ.get(
        "API_URL",
        f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker.upper()}.json",
    )
    is_custom = (
        False if "cdn.cboe.com/api/global/delayed_quotes/options" in api_url else True
    )
    ticker = ticker.lower() if ticker[0] != "_" else ticker[1:].lower()
    for _ in range(3):  # in case of unavailable data, retry twice
        filename = (
            Path(f"{getcwd()}/data/json/{ticker}_quotedata.json")
            if not is_custom
            else Path(f"{getcwd()}/data/csv/{ticker}_quotedata.csv")
        )
        with open(filename, "wb") as f, requests.get(
            api_url,
            stream=True,
            params=None
            if not is_custom
            else {
                "ticker": ticker,
                "expiry": expiry,
            },
        ) as r:
            try:  # check if data is available
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(e)
                f.write("Unavailable".encode("utf-8"))
                if r.status_code == 504:  # check if timeout occurred
                    print("gateway timeout, retrying search for", ticker, expiry)
                    continue
                elif r.status_code == 500:  # internal server error
                    print("internal server error, retrying search for", ticker, expiry)
                    continue
            else:
                if not is_custom:
                    f.write(orjson.dumps(r.json()))
                else:
                    # assumes incoming data is CSV
                    for line in r.iter_lines():
                        if len(line) % 4:
                            # add padding:
                            line += b"==="
                        f.write(base64.b64decode(line) + "\n".encode("utf-8"))
                print("\nrequest done for", ticker, expiry)
                break


def dwn_data():
    pool = ThreadPool()
    print(f"\ndownload start: {datetime.now()}\n")
    tickers = environ.get("TICKERS", "^SPX,^NDX,^RUT").split(",")
    ticks_exp = [
        (f"_{ticker[1:]}" if ticker[0] == "^" else ticker, "all") for ticker in tickers
    ]
    pool.starmap(fulfill_req, ticks_exp)
    pool.close()
    pool.join()
    print(f"\n\ndownload end: {datetime.now()}\n")


if __name__ == "__main__":
    dwn_data()
