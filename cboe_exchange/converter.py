import json
import re
import functools
from typing import List
from datetime import datetime, time
import tensorflow as tf
import tf_quant_finance as tff
from cboe_exchange.dataclasses import CBOEData, CBOEStockData, CBOEOption

def get_time_to_expiry(timetag, expire_date):
    """
    Calculates the time to expiry in years, with expiry time set to 15:00:00.
    """
    try:
        current_datetime = datetime.strptime(timetag, "%Y%m%d %H:%M:%S")
        expiry_date_obj = datetime.strptime(str(expire_date), "%Y%m%d")

        # Combine expiry date with the fixed time 15:00:00
        expiry_datetime = datetime.combine(expiry_date_obj.date(), time(15, 0, 0))

        time_delta = expiry_datetime - current_datetime

        # Calculate time to expiry in years, using 365 days
        seconds_in_year = 365 * 24 * 60 * 60
        time_to_expiry = time_delta.total_seconds() / seconds_in_year

        return time_to_expiry if time_to_expiry > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0

def convert_szosho_to_cboe(file_path: str) -> List[CBOEData]:
    """
    Parses a JSON file with stock and option data, calculates financial metrics,
    and returns a list of CBOEData objects.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    risk_free_rate = data.pop("RiskFreeRate", 0.0)
    stocks = {k: v for k, v in data.items() if ".SH" in k or ".SZ" in k}
    options = {k: v for k, v in data.items() if "SHO" in k or "SZO" in k}
    stock_map = {re.search(r'\d+', key).group(): key for key in stocks.keys()}

    cboe_data_map = {}
    for stock_symbol, stock_data in stocks.items():
        stock_obj = CBOEStockData(
            symbol=stock_symbol,
            security_type="stock",
            exchange_id=0,
            current_price=stock_data.get("lastPrice", 0.0),
            price_change=stock_data.get("lastPrice", 0) - stock_data.get("lastClose", 0),
            price_change_percent=(stock_data.get("lastPrice", 0) - stock_data.get("lastClose", 0)) / stock_data.get("lastClose", 1) if stock_data.get("lastClose") else 0,
            bid=stock_data.get("bidPrice")[0] if stock_data.get("bidPrice") else 0.0,
            ask=stock_data.get("askPrice")[0] if stock_data.get("askPrice") else 0.0,
            bid_size=stock_data.get("bidVol")[0] if stock_data.get("bidVol") else 0,
            ask_size=stock_data.get("askVol")[0] if stock_data.get("askVol") else 0,
            open=stock_data.get("open", 0.0),
            high=stock_data.get("high", 0.0),
            low=stock_data.get("low", 0.0),
            close=stock_data.get("lastPrice", 0.0),
            prev_day_close=stock_data.get("lastClose", 0.0),
            volume=stock_data.get("volume", 0),
            iv30=0.0,
            iv30_change=0.0,
            iv30_change_percent=0.0,
            seqno=0,
            last_trade_time=stock_data.get("timetag", ""),
            tick="",
            options=[]
        )
        cboe_data_map[stock_symbol] = CBOEData(
            timestamp=stock_data.get("timetag", ""),
            symbol=stock_symbol,
            data=stock_obj
        )

    options_to_process = []
    for option_symbol, option_data in options.items():
        instrument = option_data.get("Instrument", {})
        product_id_str = instrument.get("ProductID", "")
        product_id_match = re.search(r'\((\d+)\)', product_id_str)
        if not product_id_match:
            continue

        product_id = product_id_match.group(1)
        stock_symbol = stock_map.get(product_id)

        if stock_symbol and stock_symbol in cboe_data_map:
            stock_data = stocks[stock_symbol]
            spot = stock_data.get("lastPrice", 0.0)
            strike_match = re.findall(r'\d+', instrument.get("InstrumentName"))
            if not strike_match:
                continue
            strike = float(strike_match[-1])
            expiry = get_time_to_expiry(stock_data.get("timetag"), instrument.get("ExpireDate"))
            is_call = "购" in instrument.get("InstrumentName")

            options_to_process.append({
                "option_symbol": option_symbol, "option_data": option_data, "stock_symbol": stock_symbol,
                "spot": spot, "strike": strike, "expiry": expiry, "is_call": is_call
            })

    # Group options by stock and expiry date
    option_groups = {}
    for opt in options_to_process:
        instrument = opt['option_data'].get("Instrument", {})
        expire_date = instrument.get("ExpireDate")
        key = (opt['stock_symbol'], expire_date)
        if key not in option_groups:
            option_groups[key] = []
        option_groups[key].append(opt)

    all_calculated_options = {}

    for (stock_symbol, expire_date), group_options in option_groups.items():
        # Add mid_price to each option dict for easier access and filtering
        for opt in group_options:
            bid = opt['option_data'].get("bidPrice")[0] if opt['option_data'].get("bidPrice") else 0.0
            ask = opt['option_data'].get("askPrice")[0] if opt['option_data'].get("askPrice") else 0.0
            if bid > 0 and ask > 0:
                opt['mid_price'] = (bid + ask) / 2.0
            else:
                opt['mid_price'] = opt['option_data'].get("lastPrice", 0.0)

        valid_options_in_group = [opt for opt in group_options if opt['expiry'] > 0 and opt['spot'] > 0 and opt.get('mid_price', 0.0) > 0]

        if not valid_options_in_group:
            continue

        # For each group, spot and expiry are scalar
        spot = tf.constant(valid_options_in_group[0]['spot'], dtype=tf.float64)
        expiry = tf.constant(valid_options_in_group[0]['expiry'], dtype=tf.float64)

        # Prices, strikes, and is_call are vectors for the group
        prices = tf.constant([opt['mid_price'] for opt in valid_options_in_group], dtype=tf.float64)
        strikes = tf.constant([opt['strike'] for opt in valid_options_in_group], dtype=tf.float64)
        is_call_options = tf.constant([opt['is_call'] for opt in valid_options_in_group], dtype=tf.bool)

        risk_free_rate_tensor = tf.constant(risk_free_rate, dtype=tf.float64)
        discount_factor = tf.exp(-risk_free_rate_tensor * expiry)

        implied_vols = tff.black_scholes.implied_vol(
            prices=prices, strikes=strikes, expiries=expiry, spots=spot,
            discount_factors=discount_factor, is_call_options=is_call_options, dtype=tf.float64)
        implied_vols = tf.where(tf.math.is_nan(implied_vols), 0.0, implied_vols)

        # Greeks calculation
        dividend_rate = tf.constant(0.0, dtype=tf.float64)
        price_fn = functools.partial(tff.black_scholes.option_price,
                                     strikes=strikes,
                                     is_call_options=is_call_options,
                                     dividend_rates=dividend_rate,
                                     dtype=tf.float64)

        delta = tff.math.fwd_gradient(lambda s: price_fn(spots=s, volatilities=implied_vols, expiries=expiry, discount_rates=risk_free_rate_tensor), spot)
        gamma = tff.math.fwd_gradient(lambda s: tff.math.fwd_gradient(lambda s_inner: price_fn(spots=s_inner, volatilities=implied_vols, expiries=expiry, discount_rates=risk_free_rate_tensor), s), spot)
        vega = tff.math.fwd_gradient(lambda v: price_fn(spots=spot, volatilities=v, expiries=expiry, discount_rates=risk_free_rate_tensor), implied_vols)
        rho = tff.math.fwd_gradient(lambda r: price_fn(spots=spot, volatilities=implied_vols, expiries=expiry, discount_rates=r), risk_free_rate_tensor)
        theta_grad = tff.math.fwd_gradient(lambda t: price_fn(spots=spot, volatilities=implied_vols, expiries=t, discount_rates=risk_free_rate_tensor), expiry)
        theta = -theta_grad

        results = {
            "iv": implied_vols.numpy().tolist(), "delta": delta.numpy().tolist(),
            "gamma": gamma.numpy().tolist(), "vega": vega.numpy().tolist(),
            "theta": theta.numpy().tolist(), "rho": rho.numpy().tolist()
        }
        for i, opt in enumerate(valid_options_in_group):
            for k, v in results.items():
                opt[k] = v[i]
            all_calculated_options[opt['option_symbol']] = opt

    for opt_proc in options_to_process:
        option_symbol = opt_proc['option_symbol']
        option_data = opt_proc['option_data']
        stock_symbol = opt_proc['stock_symbol']
        calcs = all_calculated_options.get(option_symbol, {})

        option_obj = CBOEOption(
            option=option_symbol,
            bid=option_data.get("bidPrice")[0] if option_data.get("bidPrice") else 0.0,
            bid_size=option_data.get("bidVol")[0] if option_data.get("bidVol") else 0,
            ask=option_data.get("askPrice")[0] if option_data.get("askPrice") else 0.0,
            ask_size=option_data.get("askVol")[0] if option_data.get("askVol") else 0,
            iv=calcs.get('iv', 0.0),
            open_interest=option_data.get("openInt", 0),
            volume=option_data.get("volume", 0),
            delta=calcs.get('delta', 0.0),
            gamma=calcs.get('gamma', 0.0),
            vega=calcs.get('vega', 0.0),
            theta=calcs.get('theta', 0.0),
            rho=calcs.get('rho', 0.0),
            theo=0.0,
            change=option_data.get("lastPrice", 0) - option_data.get("lastSettlementPrice", 0),
            open=option_data.get("open", 0.0),
            high=option_data.get("high", 0.0),
            low=option_data.get("low", 0.0),
            tick="",
            last_trade_price=option_data.get("lastPrice", 0.0),
            last_trade_time=option_data.get("timetag", ""),
            percent_change=(option_data.get("lastPrice", 0) - option_data.get("lastSettlementPrice", 0)) / option_data.get("lastSettlementPrice", 1) if option_data.get("lastSettlementPrice") else 0,
            prev_day_close=option_data.get("lastSettlementPrice", 0.0)
        )
        cboe_data_map[stock_symbol].data.options.append(option_obj)

    return list(cboe_data_map.values())
