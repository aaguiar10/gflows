import requests
import json
from apscheduler.schedulers.blocking import BlockingScheduler
from cboe_exchange.converter import convert_szosho_to_cboe
import re
import os

def fetch_and_convert():
    """
    Fetches JSON data from the specified URL, converts it, and saves it to files.
    """
    url = os.environ.get("SZOSHO_URL", "http://localhost")
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        szosho_data = response.json()

        with open('szosho.json', 'w', encoding='utf-8') as f:
            json.dump(szosho_data, f, ensure_ascii=False, indent=4)

        converted_data = convert_szosho_to_cboe(szosho_data)

        for data in converted_data:
            # Extract the base stock symbol (e.g., "000001" from "000001.SZ")
            symbol_match = re.match(r'(\d+)', data['symbol'])
            if symbol_match:
                stock_symbol = symbol_match.group(1)
                filename = f"cboe.{stock_symbol}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                print(f"Successfully saved {filename}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # This script is intended to be run as a scheduled job.
    # To run the job once for testing, you can call fetch_and_convert() directly.
    # fetch_and_convert()

    scheduler = BlockingScheduler()
    # Schedule the job to run every minute
    scheduler.add_job(fetch_and_convert, 'interval', minutes=1)
    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
