import os
import requests
import base64
from multiprocessing.dummy import Pool as ThreadPool
import datetime


def fulfill_req(ticker, expiry):
    api_url = os.environ.get("API_URL")
    print(ticker + " " + expiry)
    for _ in range(3):  # in case of unavailable data, retry twice
        filename = os.getcwd() + "/data/" + expiry + "_exp/" + ticker + "_quotedata.csv"
        payload = {"ticker": ticker, "expiry": expiry}
        with open(filename, "wb") as f, requests.get(
            api_url, stream=True, params=payload
        ) as r:
            try:  # check if data is available
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(e)
                f.write("Unavailable".encode("utf-8"))
                if r.status_code == 504:  # check if timeout occurred
                    print(
                        "gateway timeout, retrying search for " + ticker + " " + expiry
                    )
                    continue
                elif r.status_code == 500:  # internal server error
                    print(
                        "internal server error, retrying search for "
                        + ticker
                        + " "
                        + expiry
                    )
                    continue
            else:
                for line in r.iter_lines():
                    if len(line) % 4:
                        # add padding:
                        line += b"==="
                    f.write(base64.b64decode(line) + "\n".encode("utf-8"))
        try:  # check if data was received incorrectly
            options_file = open(filename, encoding="utf-8")
            options_file.readlines()
            options_file.close()
        except:
            print("corrupted data, retrying search for " + ticker + " " + expiry)
        else:
            print("request done for", (ticker, expiry))
            break


def dwn_data():
    pool = ThreadPool()
    print("start:", datetime.datetime.now())
    ticks_exp = [
        ("spx", "monthly"),
        ("spx", "all"),
        ("ndx", "monthly"),
        ("ndx", "all"),
        ("rut", "monthly"),
        ("rut", "all"),
    ]
    pool.starmap(fulfill_req, ticks_exp)
    pool.close()
    pool.join()
    print("end:", datetime.datetime.now())


if __name__ == "__main__":
    dwn_data()
