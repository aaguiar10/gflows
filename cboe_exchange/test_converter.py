import unittest
import os
import json
from cboe_exchange.converter import convert_szosho_to_cboe
from cboe_exchange.dataclasses import CBOEData, CBOEStockData, CBOEOption

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
            if data.symbol == "510050.SH":
                sh_510050_data = data
                break

        self.assertIsNotNone(sh_510050_data)
        self.assertIsInstance(sh_510050_data, CBOEData)
        self.assertEqual(sh_510050_data.symbol, "510050.SH")

        self.assertIsInstance(sh_510050_data.data, CBOEStockData)
        self.assertEqual(sh_510050_data.data.symbol, "510050.SH")

        self.assertIsInstance(sh_510050_data.data.options, list)

        sh_510050_options_count = 0
        for key, value in raw_data.items():
            if isinstance(value, dict) and "Instrument" in value and value["Instrument"].get("ProductID") == "50ETF(510050)":
                sh_510050_options_count += 1

        self.assertEqual(len(sh_510050_data.data.options), sh_510050_options_count)

        # Check that IV and greeks are calculated for at least one option
        iv_calculated = False
        greeks_calculated = False
        for option in sh_510050_data.data.options:
            if option.iv != 0.0:
                iv_calculated = True
            if option.delta != 0.0 or option.gamma != 0.0 or option.vega != 0.0:
                greeks_calculated = True

        self.assertTrue(iv_calculated, "Implied volatility was not calculated for any option.")
        self.assertTrue(greeks_calculated, "Greeks were not calculated for any option.")

if __name__ == '__main__':
    unittest.main()
