import unittest
import os
import json
import re
from cboe_exchange.converter import convert_szosho_to_cboe, _generate_stock_code
from datetime import datetime

class TestConverter(unittest.TestCase):
    def test_convert_szosho_to_cboe(self):
        file_path = "szosho.json"

        self.assertTrue(os.path.exists(file_path), f"Test file not found: {file_path}")

        with open(file_path, 'r') as f:
            raw_data = json.load(f)

        stock_count = 0
        for key in raw_data.keys():
            if ".SH" in key or ".SZ" in key:
                stock_count += 1

        parsed_data = convert_szosho_to_cboe(file_path)

        self.assertIsInstance(parsed_data, list)
        self.assertEqual(len(parsed_data), stock_count)

        # Find the data for 510050.SH
        sh_510050_data = None
        for data in parsed_data:
            if data['symbol'] == "510050.SH":
                sh_510050_data = data
                break

        self.assertIsNotNone(sh_510050_data)
        self.assertIsInstance(sh_510050_data, dict)
        self.assertEqual(sh_510050_data['symbol'], "510050.SH")

        self.assertIsInstance(sh_510050_data['data'], dict)
        self.assertEqual(sh_510050_data['data']['symbol'], "510050.SH")

        self.assertIsInstance(sh_510050_data['data']['options'], list)

        sh_510050_options_count = 0
        for key, value in raw_data.items():
            if isinstance(value, dict) and "Instrument" in value and value["Instrument"].get("ProductID") == "50ETF(510050)":
                sh_510050_options_count += 1

        self.assertEqual(len(sh_510050_data['data']['options']), sh_510050_options_count)

        # Check that IV and greeks are calculated for at least one option
        iv_calculated = False
        greeks_calculated = False
        for option in sh_510050_data['data']['options']:
            if option['iv'] != 0.0:
                iv_calculated = True
            if option['delta'] != 0.0 or option['gamma'] != 0.0 or option['vega'] != 0.0:
                greeks_calculated = True

        self.assertTrue(iv_calculated, "Implied volatility was not calculated for any option.")
        self.assertTrue(greeks_calculated, "Greeks were not calculated for any option.")

        # Check the format of a specific option symbol
        option_under_test = sh_510050_data['data']['options'][0]
        option_symbol = option_under_test['option']

        stock_code = _generate_stock_code(sh_510050_data['symbol'])

        # Find the corresponding raw data to get the expire date and strike
        raw_option_data = None
        for key, value in raw_data.items():
            if "SHO" in key or "SZO" in key:
                instrument = value.get("Instrument", {})
                strike_match = re.findall(r'\d+', instrument.get("InstrumentName"))
                if not strike_match:
                    continue
                raw_strike = strike_match[-1]

                expire_date_str = str(instrument.get("ExpireDate"))
                expire_date = datetime.strptime(expire_date_str, "%Y%m%d").strftime("%y%m%d")
                option_type = "C" if "购" in instrument.get("InstrumentName") else "P"
                formatted_strike = raw_strike.zfill(8)

                expected_symbol = f"{stock_code}{expire_date}{option_type}{formatted_strike}"
                if option_symbol == expected_symbol:
                    raw_option_data = value
                    break

        self.assertIsNotNone(raw_option_data, "Could not find matching raw option data for symbol format test")


if __name__ == '__main__':
    unittest.main()
