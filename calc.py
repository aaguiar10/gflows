from scipy.stats import norm
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from os import getcwd
import yfinance as yf
from warnings import simplefilter
import pandas_market_calendars as mcal
from calendar import monthrange

# Ignore warning for NaN values in dataframe
simplefilter(action="ignore", category=RuntimeWarning)

pd.options.display.float_format = "{:,.4f}".format


# Black-Scholes Pricing Formula
# S is stock price, K is strike price
def calcDeltaEx(S, K, vol, T, r, q, optType, OI):
    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    if optType == "call":
        delta = np.exp(-q * T) * norm.cdf(dp)
        return OI * 100 * S * S * 0.01 * delta
        # change in option price per one percent move in underlying
    else:
        delta = -np.exp(-q * T) * norm.cdf(-dp)
        return OI * 100 * S * S * 0.01 * delta


def calcGammaEx(S, K, vol, T, r, q, optType, OI):
    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    dm = dp - vol * np.sqrt(T)
    if optType == "call":
        gamma = K * np.exp(-r * T) * norm.pdf(dm) / (S * S * vol * np.sqrt(T))
        return OI * 100 * S * S * 0.01 * gamma
        # change in delta per one percent move in underlying
    else:  # Gamma is same formula for calls and puts
        gamma = K * np.exp(-r * T) * norm.pdf(dm) / (S * S * vol * np.sqrt(T))
        return OI * 100 * S * S * 0.01 * gamma


def calcVannaEx(S, K, vol, T, r, q, optType, OI):
    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    dm = dp - vol * np.sqrt(T)
    if optType == "call":
        vanna = -np.exp(-q * T) * norm.pdf(dp) * (dm / vol)
        # change in delta per one percent move in IV
        # or change in vega per one percent move in underlying
        return OI * 100 * vol * 100 * vanna
    else:  # Vanna is same formula for calls and puts
        vanna = -np.exp(-q * T) * norm.pdf(dp) * (dm / vol)
        return OI * 100 * vol * 100 * vanna


def calcCharmEx(S, K, vol, T, r, q, optType, OI):
    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    dm = dp - vol * np.sqrt(T)
    if optType == "call":
        charm = (q * np.exp(-q * T) * norm.cdf(dp)) - np.exp(-q * T) * norm.pdf(dp) * (
            2 * (r - q) * T - dm * vol * np.sqrt(T)
        ) / (2 * T * vol * np.sqrt(T))
        return OI * 100 * T * charm  # change in delta per day until expiration
    else:
        charm = (-q * np.exp(-q * T) * norm.cdf(-dp)) - np.exp(-q * T) * norm.pdf(
            dp
        ) * (2 * (r - q) * T - dm * vol * np.sqrt(T)) / (2 * T * vol * np.sqrt(T))
        return OI * 100 * T * charm


def isThirdFriday(date):
    _, last = monthrange(date.year, date.month)
    first = datetime(date.year, date.month, 1).strftime("%Y %B %d")
    last = datetime(date.year, date.month, last).strftime("%Y %B %d")
    result = mcal.get_calendar("NYSE").schedule(start_date=first, end_date=last)
    result = result.index.to_pydatetime()
    found = [False, False]
    for i in result:
        if i.weekday() == 4 and 15 <= i.day <= 21 and i.month == date.month:
            # Third Friday
            found[0] = i + timedelta(hours=16)
        elif i.weekday() == 3 and 15 <= i.day <= 21 and i.month == date.month:
            # Thursday alternative
            found[1] = i + timedelta(hours=16)
    # returns Third Friday if market open,
    # else if market closed returns the Thursday before it
    return (found[0], result) if found[0] else (found[1], result)


def isMarketOpen(date, calendar):
    if date in calendar:
        # market is open so return that date
        return date
    else:
        # market is closed so look for when it is open
        return isMarketOpen(date + timedelta(days=1), calendar)


# check 10 yr treasury yield
def checkTenYr(date):
    data = yf.Ticker("^TNX").history(
        start=date - timedelta(days=5), end=date, prepost=True
    )
    if data.empty:
        # no data for the date range so look back further
        return checkTenYr(date - timedelta(days=2))
    else:
        # most recent date
        return data.tail(1)["Close"].item()


def getOptionsData(ticker, expir):
    if expir != "all":
        filename = getcwd() + "/data/monthly_exp/" + ticker + "_quotedata.csv"
    else:
        filename = getcwd() + "/data/all_exp/" + ticker + "_quotedata.csv"
    # This assumes the CBOE file format hasn't been edited, i.e. table begins at line 4
    optionsFile = open(filename, encoding="utf-8")
    optionsFileData = optionsFile.readlines()
    optionsFile.close()

    # Error check if data unavailable
    if len(optionsFileData) == 0 or optionsFileData[0] == "Unavailable":
        print(ticker, expir, "data is unavailable")
        return
    # Get Spot
    spotLine = optionsFileData[1]
    spotPrice = float(spotLine.split("Last:")[1].split(",")[0])
    fromStrike = 0.5 * spotPrice
    toStrike = 1.5 * spotPrice
    # Get Today's Date
    dateLine = optionsFileData[2]
    todayDate = dateLine.split("Date: ")[1].split(",")
    timezone = ""
    if "EST" in todayDate[1]:
        retrieved_ampm = todayDate[1].split("at")[1].split("EST")
    else:
        retrieved_ampm = todayDate[1].split("at")[1].split("EDT")
    timezone = " ET "
    am_pm = "%I:%M %p"
    data_time = (
        datetime.strptime(todayDate[0], "%B %d").strftime("%b %d")
        + ","
        + todayDate[1].split("at")[0]
        + "at "
        + (
            datetime.strptime(retrieved_ampm[0].strip(), am_pm) - timedelta(minutes=15)
        ).strftime("%-I:%M %p")
        + timezone
        + "(15min delay)"
    )
    monthDay = todayDate[0].split(" ")
    # Handling of US/EU date formats
    if len(monthDay) == 2:
        year = int(todayDate[1].split("at")[0])
        month = monthDay[0]
        day = int(monthDay[1])
    else:
        year = int(monthDay[2])
        month = monthDay[1]
        day = int(monthDay[0])
    todayDate = datetime.strptime(month, "%B")
    todayDate = todayDate.replace(day=day, year=year)
    df = pd.read_csv(filename, sep=",", header=None, skiprows=4)
    df.columns = [
        "ExpirationDate",
        "Calls",
        "CallLastSale",
        "CallNet",
        "CallBid",
        "CallAsk",
        "CallVol",
        "CallIV",
        "CallDelta",
        "CallGamma",
        "CallOpenInt",
        "StrikePrice",
        "Puts",
        "PutLastSale",
        "PutNet",
        "PutBid",
        "PutAsk",
        "PutVol",
        "PutIV",
        "PutDelta",
        "PutGamma",
        "PutOpenInt",
    ]

    df["ExpirationDate"] = pd.to_datetime(df["ExpirationDate"], format="%a %b %d %Y")
    df["ExpirationDate"] = df["ExpirationDate"] + timedelta(hours=16)
    df["StrikePrice"] = df["StrikePrice"].astype(float)
    df["CallIV"] = df["CallIV"].astype(float)
    df["PutIV"] = df["PutIV"].astype(float)
    df["CallDelta"] = df["CallDelta"].astype(float)
    df["PutDelta"] = df["PutDelta"].astype(float)
    df["CallGamma"] = df["CallGamma"].astype(float)
    df["PutGamma"] = df["PutGamma"].astype(float)
    df["CallOpenInt"] = df["CallOpenInt"].astype(float)
    df["PutOpenInt"] = df["PutOpenInt"].astype(float)

    firstExpiry = df["ExpirationDate"].min()
    thisMonthlyOpex, calendarRange = isThirdFriday(firstExpiry)
    if expir != "all":
        # month, monthly opex, 0DTE
        monthly_options_dates = [
            firstExpiry,
            thisMonthlyOpex,
            isMarketOpen(
                datetime(firstExpiry.year, firstExpiry.month, firstExpiry.day),
                calendarRange,
            ),
        ]
    else:
        monthly_options_dates = []
    dividend_yield = 0  # assume 0
    yield_10yr = checkTenYr(firstExpiry)

    if expir == "0dte":
        df = df.loc[df["ExpirationDate"] == firstExpiry]
    elif expir == "opex":
        df = df.loc[df["ExpirationDate"] <= thisMonthlyOpex]

    # set DTE. 0DTE options are included in 1 day expiration
    df["daysTillExp"] = [
        1 / 252
        if (np.busday_count(todayDate.date(), x.date())) == 0
        else np.busday_count(todayDate.date(), x.date()) / 252
        for x in df.ExpirationDate
    ]

    expirations = df["ExpirationDate"].to_numpy()

    # parameters to reuse
    params = np.vstack(
        (
            df["StrikePrice"].to_numpy(),
            df["daysTillExp"].to_numpy(),
            df["CallIV"].to_numpy(),
            df["CallOpenInt"].to_numpy(),
            df["PutIV"].to_numpy(),
            df["PutOpenInt"].to_numpy(),
        )
    )
    nonzero_call_cond = np.logical_and(params[1] > 0, params[2] > 0)
    nonzero_put_cond = np.logical_and(params[1] > 0, params[4] > 0)

    # ---=== CALCULATE EXPOSURES ===---
    df["CallDEX"] = (
        df["CallDelta"].to_numpy() * params[3] * 100 * spotPrice * spotPrice * 0.01
    )
    df["PutDEX"] = (
        df["PutDelta"].to_numpy() * params[5] * 100 * spotPrice * spotPrice * 0.01
    )
    df["CallGEX"] = (
        df["CallGamma"].to_numpy() * params[3] * 100 * spotPrice * spotPrice * 0.01
    )
    df["PutGEX"] = (
        df["PutGamma"].to_numpy() * params[5] * 100 * spotPrice * spotPrice * 0.01 * -1
    )
    df["CallVEX"] = np.where(
        nonzero_call_cond,
        calcVannaEx(
            spotPrice,
            df["StrikePrice"].to_numpy(),
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    df["PutVEX"] = np.where(
        nonzero_put_cond,
        calcVannaEx(
            spotPrice,
            df["StrikePrice"].to_numpy(),
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )
    df["CallCEX"] = np.where(
        nonzero_call_cond,
        calcCharmEx(
            spotPrice,
            df["StrikePrice"].to_numpy(),
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    df["PutCEX"] = np.where(
        nonzero_put_cond,
        calcCharmEx(
            spotPrice,
            df["StrikePrice"].to_numpy(),
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )
    # Calculate total and scale down
    df["TotalDelta"] = (df["CallDEX"].to_numpy() + df["PutDEX"].to_numpy()) / 10**11
    df["TotalGamma"] = (df["CallGEX"].to_numpy() + df["PutGEX"].to_numpy()) / 10**9
    df["TotalVanna"] = (df["CallVEX"].to_numpy() - df["PutVEX"].to_numpy()) / 10**9
    df["TotalCharm"] = (df["CallCEX"].to_numpy() - df["PutCEX"].to_numpy()) / 10**9

    # group all options by strike / expiration then average their IVs
    dfAgg_strike_mean = (
        df[["StrikePrice", "CallIV", "PutIV"]]
        .groupby(["StrikePrice"])
        .mean(numeric_only=True)
    )
    dfAgg_exp_mean = (
        df[["ExpirationDate", "CallIV", "PutIV"]]
        .groupby(["ExpirationDate"])
        .mean(numeric_only=True)
    )
    # filter strikes / expirations for relevance
    dfAgg_strike_mean = dfAgg_strike_mean.loc[fromStrike:toStrike]
    dfAgg_exp_mean = dfAgg_exp_mean.loc[todayDate : todayDate + timedelta(weeks=26)]

    call_ivs = dfAgg_strike_mean["CallIV"].to_numpy()
    put_ivs = dfAgg_strike_mean["PutIV"].to_numpy()
    call_ivs_exp = dfAgg_exp_mean["CallIV"].to_numpy()
    put_ivs_exp = dfAgg_exp_mean["PutIV"].to_numpy()

    # ---=== CALCULATE EXPOSURE PROFILES ===---
    levels = np.linspace(fromStrike, toStrike, 180).reshape(-1, 1)
    totalDelta = np.array([])
    totalDeltaExNext = np.array([])
    totalDeltaExFri = np.array([])
    totalGamma = np.array([])
    totalGammaExNext = np.array([])
    totalGammaExFri = np.array([])
    totalVanna = np.array([])
    totalVannaExNext = np.array([])
    totalVannaExFri = np.array([])
    totalCharm = np.array([])
    totalCharmExNext = np.array([])
    totalCharmExFri = np.array([])

    # For each spot level, calculate greek exposure at that point
    callDeltaEx = np.where(
        nonzero_call_cond,
        calcDeltaEx(
            levels,
            params[0],
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    putDeltaEx = np.where(
        nonzero_put_cond,
        calcDeltaEx(
            levels,
            params[0],
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )
    callGammaEx = np.where(
        nonzero_call_cond,
        calcGammaEx(
            levels,
            params[0],
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    putGammaEx = np.where(
        nonzero_put_cond,
        calcGammaEx(
            levels,
            params[0],
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )
    callVannaEx = np.where(
        nonzero_call_cond,
        calcVannaEx(
            levels,
            params[0],
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    putVannaEx = np.where(
        nonzero_put_cond,
        calcVannaEx(
            levels,
            params[0],
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )
    callCharmEx = np.where(
        nonzero_call_cond,
        calcCharmEx(
            levels,
            params[0],
            params[2],
            params[1],
            yield_10yr,
            dividend_yield,
            "call",
            params[3],
        ),
        0,
    )
    putCharmEx = np.where(
        nonzero_put_cond,
        calcCharmEx(
            levels,
            params[0],
            params[4],
            params[1],
            yield_10yr,
            dividend_yield,
            "put",
            params[5],
        ),
        0,
    )

    # delta exposure
    totalDelta = (callDeltaEx.sum(axis=1) + putDeltaEx.sum(axis=1)) / 10**11
    # gamma exposure
    totalGamma = (callGammaEx.sum(axis=1) - putGammaEx.sum(axis=1)) / 10**9
    # vanna exposure
    totalVanna = (callVannaEx.sum(axis=1) - putVannaEx.sum(axis=1)) / 10**9
    # charm exposure
    totalCharm = (callCharmEx.sum(axis=1) - putCharmEx.sum(axis=1)) / 10**9

    if expir != "0dte":
        # exposure for next expiry
        totalDeltaExNext = (
            np.where(expirations != firstExpiry, callDeltaEx, 0).sum(axis=1)
            + np.where(expirations != firstExpiry, putDeltaEx, 0).sum(axis=1)
        ) / 10**11
        totalGammaExNext = (
            np.where(expirations != firstExpiry, callGammaEx, 0).sum(axis=1)
            - np.where(expirations != firstExpiry, putGammaEx, 0).sum(axis=1)
        ) / 10**9
        totalVannaExNext = (
            np.where(expirations != firstExpiry, callVannaEx, 0).sum(axis=1)
            - np.where(expirations != firstExpiry, putVannaEx, 0).sum(axis=1)
        ) / 10**9
        totalCharmExNext = (
            np.where(expirations != firstExpiry, callCharmEx, 0).sum(axis=1)
            - np.where(expirations != firstExpiry, putCharmEx, 0).sum(axis=1)
        ) / 10**9
        if expir == "all":
            # exposure for next monthly opex
            totalDeltaExFri = (
                np.where(expirations != thisMonthlyOpex, callDeltaEx, 0).sum(axis=1)
                + np.where(expirations != thisMonthlyOpex, putDeltaEx, 0).sum(axis=1)
            ) / 10**11
            totalGammaExFri = (
                np.where(expirations != thisMonthlyOpex, callGammaEx, 0).sum(axis=1)
                - np.where(expirations != thisMonthlyOpex, putGammaEx, 0).sum(axis=1)
            ) / 10**9
            totalVannaExFri = (
                np.where(expirations != thisMonthlyOpex, callVannaEx, 0).sum(axis=1)
                - np.where(expirations != thisMonthlyOpex, putVannaEx, 0).sum(axis=1)
            ) / 10**9
            totalCharmExFri = (
                np.where(expirations != thisMonthlyOpex, callCharmEx, 0).sum(axis=1)
                - np.where(expirations != thisMonthlyOpex, putCharmEx, 0).sum(axis=1)
            ) / 10**9

    # Find Delta Flip Point
    zeroCrossIdx = np.where(np.diff(np.sign(totalDelta)))[0]
    negDelta = totalDelta[zeroCrossIdx]
    posDelta = totalDelta[zeroCrossIdx + 1]
    negStrike = levels[zeroCrossIdx]
    posStrike = levels[zeroCrossIdx + 1]
    zeroDelta = posStrike - ((posStrike - negStrike) * posDelta / (posDelta - negDelta))
    # Find Gamma Flip Point
    zeroCrossIdx = np.where(np.diff(np.sign(totalGamma)))[0]
    negGamma = totalGamma[zeroCrossIdx]
    posGamma = totalGamma[zeroCrossIdx + 1]
    negStrike = levels[zeroCrossIdx]
    posStrike = levels[zeroCrossIdx + 1]
    zeroGamma = posStrike - ((posStrike - negStrike) * posGamma / (posGamma - negGamma))

    if zeroDelta.size > 0:
        zeroDelta = zeroDelta[0][0]
    else:
        print("delta flip not found for " + ticker + " " + expir)
    if zeroGamma.size > 0:
        zeroGamma = zeroGamma[0][0]
    else:
        print("gamma flip not found for " + ticker + " " + expir)

    return (
        df,
        data_time,
        todayDate,
        monthly_options_dates,
        spotPrice,
        fromStrike,
        toStrike,
        levels.ravel(),
        totalDelta,
        totalDeltaExNext,
        totalDeltaExFri,
        totalGamma,
        totalGammaExNext,
        totalGammaExFri,
        totalVanna,
        totalVannaExNext,
        totalVannaExFri,
        totalCharm,
        totalCharmExNext,
        totalCharmExFri,
        zeroDelta,
        zeroGamma,
        call_ivs,
        put_ivs,
        call_ivs_exp,
        put_ivs_exp,
    )
