import pandas as pd
import exchange_calendars as xcals
import numpy as np
import orjson
import modules.stats as stats
from yahooquery import Ticker
from datetime import datetime, timedelta
from pytz import timezone
from dateparser.date import DateDataParser
from warnings import simplefilter
from calendar import monthrange
from cachetools import cached, TTLCache
from pathlib import Path
from os import getcwd

# Ignore warning for NaN values in dataframe
simplefilter(action="ignore", category=RuntimeWarning)

pd.options.display.float_format = "{:,.4f}".format


@cached(cache=TTLCache(maxsize=16, ttl=60 * 60 * 4))  # in-memory cache for 4 hrs
def is_third_friday(date, tz):
    _, last = monthrange(date.year, date.month)
    first = datetime(date.year, date.month, 1)
    last = datetime(date.year, date.month, last)
    result = xcals.get_calendar("XNYS", start=first, end=last)
    result = result.sessions.to_pydatetime()
    found = [False, False]
    for i in result:
        if i.weekday() == 4 and 15 <= i.day <= 21 and i.month == date.month:
            # Third Friday
            found[0] = timezone(tz).localize(i) + timedelta(hours=16)
        elif i.weekday() == 3 and 15 <= i.day <= 21 and i.month == date.month:
            # Thursday alternative
            found[1] = timezone(tz).localize(i) + timedelta(hours=16)
    # returns Third Friday if market open,
    # else if market closed returns the Thursday before it
    return (found[0], result) if found[0] else (found[1], result)


# check 10 yr treasury yield
@cached(cache=TTLCache(maxsize=16, ttl=60 * 15))  # in-memory cache for 15 min
def check_ten_yr(date):
    data = Ticker("^TNX").history(start=date - timedelta(days=5), end=date)
    if data.empty:
        # no data for the date range so look back further
        return check_ten_yr(date - timedelta(days=2))
    else:
        # most recent date
        return data.tail(1)["close"].item() / 100


def is_parsable(date):
    try:
        datetime.strptime(date.split()[-2], "%H:%M")
        return True
    except ValueError:
        return False


def format_data(data, today_ddt, tzinfo):
    keys_to_keep = ["option", "iv", "open_interest", "delta", "gamma"]
    data = pd.DataFrame([{k: d[k] for k in keys_to_keep if k in d} for d in data])
    data = pd.concat(
        [
            data.rename(
                columns={
                    "option": "calls",
                    "iv": "call_iv",
                    "open_interest": "call_open_int",
                    "delta": "call_delta",
                    "gamma": "call_gamma",
                }
            )
            .iloc[0::2]
            .reset_index(drop=True),
            data.rename(
                columns={
                    "option": "puts",
                    "iv": "put_iv",
                    "open_interest": "put_open_int",
                    "delta": "put_delta",
                    "gamma": "put_gamma",
                }
            )
            .iloc[1::2]
            .reset_index(drop=True),
        ],
        axis=1,
    )
    data["strike_price"] = (
        data["calls"].str.extract(r"\d[A-Z](\d+)\d\d\d").astype(float)
    )
    data["expiration_date"] = data["calls"].str.extract(r"[A-Z](\d+)")
    data["expiration_date"] = pd.to_datetime(
        data["expiration_date"], format="%y%m%d"
    ).dt.tz_localize(tzinfo) + timedelta(hours=16)

    busday_counts = np.busday_count(
        today_ddt.date(),
        data["expiration_date"].values.astype("datetime64[D]"),
    )
    # set DTE. 0DTE options are included in 1 day expirations
    # time to expiration in years (252 trading days)
    data["time_till_exp"] = np.where(busday_counts == 0, 1 / 252, busday_counts / 252)

    data = data.sort_values(by=["expiration_date", "strike_price"]).reset_index(
        drop=True
    )

    return data


def calc_exposures(
    option_data,
    ticker,
    expir,
    first_expiry,
    this_monthly_opex,
    spot_price,
    today_ddt,
    today_ddt_string,
):
    dividend_yield = 0.0  # assume 0
    yield_10yr = check_ten_yr(today_ddt)

    monthly_options_dates = [first_expiry, this_monthly_opex]

    strike_prices = option_data["strike_price"].to_numpy()
    expirations = option_data["expiration_date"].to_numpy()
    time_till_exp = option_data["time_till_exp"].to_numpy()
    opt_call_ivs = option_data["call_iv"].to_numpy()
    opt_put_ivs = option_data["put_iv"].to_numpy()
    call_open_interest = option_data["call_open_int"].to_numpy()
    put_open_interest = option_data["put_open_int"].to_numpy()

    nonzero_call_cond = (time_till_exp > 0) & (opt_call_ivs > 0)
    nonzero_put_cond = (time_till_exp > 0) & (opt_put_ivs > 0)
    np_spot_price = np.array([[spot_price]])

    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        yield_10yr,
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        yield_10yr,
        dividend_yield,
    )

    from_strike = 0.5 * spot_price
    to_strike = 1.5 * spot_price

    # ---=== CALCULATE EXPOSURES ===---
    option_data["call_dex"] = (
        option_data["call_delta"].to_numpy() * call_open_interest * spot_price
    )
    option_data["put_dex"] = (
        option_data["put_delta"].to_numpy() * put_open_interest * spot_price
    )
    option_data["call_gex"] = (
        option_data["call_gamma"].to_numpy()
        * call_open_interest
        * spot_price
        * spot_price
    )
    option_data["put_gex"] = (
        option_data["put_gamma"].to_numpy()
        * put_open_interest
        * spot_price
        * spot_price
        * -1
    )
    option_data["call_vex"] = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_vex"] = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    option_data["call_cex"] = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            yield_10yr,
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_cex"] = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            yield_10yr,
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    # Calculate total and scale down
    option_data["total_delta"] = (
        option_data["call_dex"].to_numpy() + option_data["put_dex"].to_numpy()
    ) / 10**9
    option_data["total_gamma"] = (
        option_data["call_gex"].to_numpy() + option_data["put_gex"].to_numpy()
    ) / 10**9
    option_data["total_vanna"] = (
        option_data["call_vex"].to_numpy() - option_data["put_vex"].to_numpy()
    ) / 10**9
    option_data["total_charm"] = (
        option_data["call_cex"].to_numpy() - option_data["put_cex"].to_numpy()
    ) / 10**9

    # group all options by strike / expiration then average their IVs
    df_agg_strike_mean = (
        option_data[["strike_price", "call_iv", "put_iv"]]
        .groupby(["strike_price"])
        .mean(numeric_only=True)
    )
    df_agg_exp_mean = (
        option_data[["expiration_date", "call_iv", "put_iv"]]
        .groupby(["expiration_date"])
        .mean(numeric_only=True)
    )
    # filter strikes / expirations for relevance
    df_agg_strike_mean = df_agg_strike_mean[from_strike:to_strike]
    # df_agg_exp_mean = df_agg_exp_mean[: today_ddt + timedelta(weeks=52)]

    call_ivs = {
        "strike": df_agg_strike_mean["call_iv"].to_numpy(),
        "exp": df_agg_exp_mean["call_iv"].to_numpy(),
    }
    put_ivs = {
        "strike": df_agg_strike_mean["put_iv"].to_numpy(),
        "exp": df_agg_exp_mean["put_iv"].to_numpy(),
    }

    # ---=== CALCULATE EXPOSURE PROFILES ===---
    levels = np.linspace(from_strike, to_strike, 300).reshape(-1, 1)

    totaldelta = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalgamma = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalvanna = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalcharm = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }

    # For each spot level, calculate greek exposure at that point
    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        yield_10yr,
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        yield_10yr,
        dividend_yield,
    )
    call_delta_ex = np.where(
        nonzero_call_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "call",
            call_open_interest,
            call_cdf_dp,
        ),
        0,
    )
    put_delta_ex = np.where(
        nonzero_put_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "put",
            put_open_interest,
            put_cdf_dp,
        ),
        0,
    )
    call_gamma_ex = np.where(
        nonzero_call_cond,
        stats.calc_gamma_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_pdf_dp,
        ),
        0,
    )
    put_gamma_ex = np.where(
        nonzero_put_cond,
        stats.calc_gamma_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_pdf_dp,
        ),
        0,
    )
    call_vanna_ex = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_vanna_ex = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        ),
        0,
    )
    call_charm_ex = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            yield_10yr,
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_charm_ex = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            yield_10yr,
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        ),
        0,
    )

    # delta exposure
    totaldelta["all"] = (call_delta_ex.sum(axis=1) + put_delta_ex.sum(axis=1)) / 10**9
    # gamma exposure
    totalgamma["all"] = (call_gamma_ex.sum(axis=1) - put_gamma_ex.sum(axis=1)) / 10**9
    # vanna exposure
    totalvanna["all"] = (call_vanna_ex.sum(axis=1) - put_vanna_ex.sum(axis=1)) / 10**9
    # charm exposure
    totalcharm["all"] = (call_charm_ex.sum(axis=1) - put_charm_ex.sum(axis=1)) / 10**9

    expirs_not_first_expiry = expirations != first_expiry
    expirs_not_this_monthly_opex = expirations != this_monthly_opex
    if expir != "0dte":
        # exposure for next expiry
        totaldelta["ex_next"] = (
            np.where(expirs_not_first_expiry, call_delta_ex, 0).sum(axis=1)
            + np.where(expirs_not_first_expiry, put_delta_ex, 0).sum(axis=1)
        ) / 10**9
        totalgamma["ex_next"] = (
            np.where(expirs_not_first_expiry, call_gamma_ex, 0).sum(axis=1)
            - np.where(expirs_not_first_expiry, put_gamma_ex, 0).sum(axis=1)
        ) / 10**9
        totalvanna["ex_next"] = (
            np.where(expirs_not_first_expiry, call_vanna_ex, 0).sum(axis=1)
            - np.where(expirs_not_first_expiry, put_vanna_ex, 0).sum(axis=1)
        ) / 10**9
        totalcharm["ex_next"] = (
            np.where(expirs_not_first_expiry, call_charm_ex, 0).sum(axis=1)
            - np.where(expirs_not_first_expiry, put_charm_ex, 0).sum(axis=1)
        ) / 10**9
        if expir == "all":
            # exposure for next monthly opex
            totaldelta["ex_fri"] = (
                np.where(expirs_not_this_monthly_opex, call_delta_ex, 0).sum(axis=1)
                + np.where(expirs_not_this_monthly_opex, put_delta_ex, 0).sum(axis=1)
            ) / 10**9
            totalgamma["ex_fri"] = (
                np.where(expirs_not_this_monthly_opex, call_gamma_ex, 0).sum(axis=1)
                - np.where(expirs_not_this_monthly_opex, put_gamma_ex, 0).sum(axis=1)
            ) / 10**9
            totalvanna["ex_fri"] = (
                np.where(expirs_not_this_monthly_opex, call_vanna_ex, 0).sum(axis=1)
                - np.where(expirs_not_this_monthly_opex, put_vanna_ex, 0).sum(axis=1)
            ) / 10**9
            totalcharm["ex_fri"] = (
                np.where(expirs_not_this_monthly_opex, call_charm_ex, 0).sum(axis=1)
                - np.where(expirs_not_this_monthly_opex, put_charm_ex, 0).sum(axis=1)
            ) / 10**9

    # Find Delta Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totaldelta["all"])))[0]
    neg_delta = totaldelta["all"][zero_cross_idx]
    pos_delta = totaldelta["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerodelta = pos_strike - (
        (pos_strike - neg_strike) * pos_delta / (pos_delta - neg_delta)
    )
    # Find Gamma Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totalgamma["all"])))[0]
    negGamma = totalgamma["all"][zero_cross_idx]
    posGamma = totalgamma["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerogamma = pos_strike - (
        (pos_strike - neg_strike) * posGamma / (posGamma - negGamma)
    )

    if zerodelta.size > 0:
        zerodelta = zerodelta[0][0]
    else:
        zerodelta = 0
        print("delta flip not found for", ticker, expir)
    if zerogamma.size > 0:
        zerogamma = zerogamma[0][0]
    else:
        zerogamma = 0
        print("gamma flip not found for", ticker, expir)

    return (
        option_data,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels.ravel(),
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
    )


def get_options_data_json(ticker, expir, tz):
    try:
        # CBOE file format, json
        with open(
            Path(f"{getcwd()}/data/json/{ticker}_quotedata.json"), encoding="utf-8"
        ) as json_file:
            json_data = json_file.read()
        data = pd.json_normalize(orjson.loads(json_data))
    except orjson.JSONDecodeError as e:  # handle error if data unavailable
        print(f"{e}, {ticker} {expir} data is unavailable")
        return

    # Get Spot
    spot_price = data["data.current_price"][0].astype(float)

    # Get Today's Date
    today_date = DateDataParser(
        settings={
            "TIMEZONE": "UTC",
            "TO_TIMEZONE": tz,
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
    ).get_date_data(str(data["timestamp"][0]))
    # Handle date formats
    today_ddt = today_date.date_obj - timedelta(minutes=15)
    today_ddt_string = today_ddt.strftime("%Y %b %d, %I:%M %p %Z") + " (15min delay)"

    option_data = format_data(
        data["data.options"][0],
        today_ddt,
        today_date.date_obj.tzinfo,
    )

    all_dates = option_data["expiration_date"].drop_duplicates()
    first_expiry = all_dates.iat[0]
    if today_ddt > first_expiry:
        # first date expired so, if available, use next date as 0DTE
        try:
            option_data = option_data[option_data["expiration_date"] != first_expiry]
            first_expiry = all_dates.iat[1]
        except IndexError:
            print("next date unavailable. using expired date")

    this_monthly_opex, calendar_range = is_third_friday(first_expiry, tz)

    if expir == "monthly":
        option_data = option_data[
            option_data["expiration_date"]
            <= timezone(tz).localize(calendar_range[-1]) + timedelta(hours=16)
        ]
    elif expir == "0dte":
        option_data = option_data[option_data["expiration_date"] == first_expiry]
    elif expir == "opex":
        option_data = option_data[option_data["expiration_date"] <= this_monthly_opex]

    return calc_exposures(
        option_data,
        ticker,
        expir,
        first_expiry,
        this_monthly_opex,
        spot_price,
        today_ddt,
        today_ddt_string,
    )


def get_options_data_csv(ticker, expir, tz):
    try:
        # CBOE file format, csv
        with open(
            Path(f"{getcwd()}/data/csv/{ticker}_quotedata.csv"), encoding="utf-8"
        ) as csv_file:
            next(csv_file)  # skip first line
            spot_line = csv_file.readline()
            date_line = csv_file.readline()
            # Option data starts at line 4
            option_data = pd.read_csv(
                csv_file,
                header=0,
                names=[
                    "expiration_date",
                    "calls",
                    "call_last_sale",
                    "call_net",
                    "call_bid",
                    "call_ask",
                    "call_vol",
                    "call_iv",
                    "call_delta",
                    "call_gamma",
                    "call_open_int",
                    "strike_price",
                    "puts",
                    "put_last_sale",
                    "put_net",
                    "put_bid",
                    "put_ask",
                    "put_vol",
                    "put_iv",
                    "put_delta",
                    "put_gamma",
                    "put_open_int",
                ],
                usecols=lambda x: x
                not in [
                    "call_last_sale",
                    "call_net",
                    "call_bid",
                    "call_ask",
                    "call_vol",
                    "put_last_sale",
                    "put_net",
                    "put_bid",
                    "put_ask",
                    "put_vol",
                ],
            )
    except:  # handle error if data unavailable
        print(ticker, expir, "data is unavailable")
        return

    # Get Spot
    spot_price = float(spot_line.split("Last:")[1].split(",")[0])

    # Get Today's Date
    today_date = date_line.split("Date: ")[1].split(",Bid")[0]
    # Handle date formats
    if is_parsable(today_date):
        pass
    else:
        tmp = today_date.split()
        tmp[-1], tmp[-2] = tmp[-2], tmp[-1]
        today_date = " ".join(tmp)
    today_date = DateDataParser(settings={"TIMEZONE": tz}).get_date_data(today_date)
    today_ddt = today_date.date_obj - timedelta(minutes=15)
    today_ddt_string = today_ddt.strftime("%Y %b %d, %I:%M %p %Z") + " (15min delay)"

    option_data["expiration_date"] = pd.to_datetime(
        option_data["expiration_date"], format="%a %b %d %Y"
    ).dt.tz_localize(today_date.date_obj.tzinfo) + timedelta(hours=16)
    option_data["strike_price"] = option_data["strike_price"].astype(float)
    option_data["call_iv"] = option_data["call_iv"].astype(float)
    option_data["put_iv"] = option_data["put_iv"].astype(float)
    option_data["call_delta"] = option_data["call_delta"].astype(float)
    option_data["put_delta"] = option_data["put_delta"].astype(float)
    option_data["call_gamma"] = option_data["call_gamma"].astype(float)
    option_data["put_gamma"] = option_data["put_gamma"].astype(float)
    option_data["call_open_int"] = option_data["call_open_int"].astype(float)
    option_data["put_open_int"] = option_data["put_open_int"].astype(float)

    all_dates = option_data["expiration_date"].drop_duplicates()
    first_expiry = all_dates.iat[0]
    if today_ddt > first_expiry:
        # first date expired so, if available, use next date as 0DTE
        try:
            option_data = option_data[option_data["expiration_date"] != first_expiry]
            first_expiry = all_dates.iat[1]
        except IndexError:
            print("next date unavailable. using expired date")
    this_monthly_opex, calendar_range = is_third_friday(first_expiry, tz)

    busday_counts = np.busday_count(
        today_ddt.date(),
        option_data["expiration_date"].values.astype("datetime64[D]"),
    )
    # set DTE. 0DTE options are included in 1 day expirations
    # time to expiration in years (252 trading days)
    option_data["time_till_exp"] = np.where(
        busday_counts == 0, 1 / 252, busday_counts / 252
    )

    if expir == "monthly":
        option_data = option_data[
            option_data["expiration_date"]
            <= timezone(tz).localize(calendar_range[-1]) + timedelta(hours=16)
        ]
    elif expir == "0dte":
        option_data = option_data[option_data["expiration_date"] == first_expiry]
    elif expir == "opex":
        option_data = option_data[option_data["expiration_date"] <= this_monthly_opex]

    return calc_exposures(
        option_data,
        ticker,
        expir,
        first_expiry,
        this_monthly_opex,
        spot_price,
        today_ddt,
        today_ddt_string,
    )


def get_options_data(ticker, expir, is_json, tz):
    return (
        get_options_data_json(ticker, expir, tz)
        if is_json
        else get_options_data_csv(ticker, expir, tz)
    )
