from scipy.stats import norm
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from os import getcwd
import yfinance as yf
from warnings import simplefilter

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


def isThirdFriday(d):
    return d.weekday() == 4 and 15 <= d.day <= 21


def getOptionsData(ticker, expir):
    dividend_yield = 0  # assume 0
    yield_10yr = 0
    tnx_data = yf.Ticker("^TNX").history(period="5d", interval="15m")
    yield_10yr = tnx_data.tail(1)["Close"].item()
    filename = getcwd() + "/data/" + expir + "_exp/" + ticker + "_quotedata.csv"
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
    if ticker == "ndx":
        fromStrike = 0.7 * spotPrice
    else:
        fromStrike = 0.8 * spotPrice
    toStrike = 1.2 * spotPrice
    # Get Today's Date
    dateLine = optionsFileData[2]
    todayDate = dateLine.split("Date: ")[1].split(",")
    retrieved_ampm = todayDate[1].split("at")[1].split("EST")
    am_pm = "%I:%M %p"
    data_time = (
        datetime.strptime(todayDate[0], "%B %d").strftime("%b %d")
        + ","
        + todayDate[1].split("at")[0]
        + "at "
        + (
            datetime.strptime(retrieved_ampm[0].strip(), am_pm) - timedelta(minutes=15)
        ).strftime("%-I:%M %p")
        + " EST "
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

    # set DTE. 0DTE options are included in 1 day expiration
    df["daysTillExp"] = [
        1 / 252
        if (np.busday_count(todayDate.date(), x.date())) == 0
        else np.busday_count(todayDate.date(), x.date()) / 252
        for x in df.ExpirationDate
    ]
    # ---=== CALCULATE EXPOSURES ===---
    df["CallGEX"] = (
        df["CallGamma"] * df["CallOpenInt"] * 100 * spotPrice * spotPrice * 0.01
    )
    df["PutGEX"] = (
        df["PutGamma"] * df["PutOpenInt"] * 100 * spotPrice * spotPrice * 0.01 * -1
    )
    df["CallDEX"] = (
        df["CallDelta"] * df["CallOpenInt"] * 100 * spotPrice * spotPrice * 0.01
    )
    df["PutDEX"] = (
        df["PutDelta"] * df["PutOpenInt"] * 100 * spotPrice * spotPrice * 0.01
    )
    df["CallVEX"] = np.where(
        np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
        calcVannaEx(
            spotPrice,
            df["StrikePrice"],
            df["CallIV"],
            df["daysTillExp"],
            yield_10yr,
            dividend_yield,
            "call",
            df["CallOpenInt"],
        ),
        0,
    )
    df["PutVEX"] = np.where(
        np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
        calcVannaEx(
            spotPrice,
            df["StrikePrice"],
            df["PutIV"],
            df["daysTillExp"],
            yield_10yr,
            dividend_yield,
            "put",
            df["PutOpenInt"],
        ),
        0,
    )
    df["CallCEX"] = np.where(
        np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
        calcCharmEx(
            spotPrice,
            df["StrikePrice"],
            df["CallIV"],
            df["daysTillExp"],
            yield_10yr,
            dividend_yield,
            "call",
            df["CallOpenInt"],
        ),
        0,
    )
    df["PutCEX"] = np.where(
        np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
        calcCharmEx(
            spotPrice,
            df["StrikePrice"],
            df["PutIV"],
            df["daysTillExp"],
            yield_10yr,
            dividend_yield,
            "put",
            df["PutOpenInt"],
        ),
        0,
    )
    # Calculate total and scale down
    df["TotalGamma"] = (df.CallGEX + df.PutGEX) / 10**9
    df["TotalDelta"] = (df.CallDEX + df.PutDEX) / 10**11
    df["TotalVanna"] = (df.CallVEX - df.PutVEX) / 10**9
    df["TotalCharm"] = (df.CallCEX - df.PutCEX) / 10**9
    # filter strikes and expiration dates for relevance
    dfAgg_strike = df.groupby(["StrikePrice"]).sum(numeric_only=True)
    dfAgg_strike = dfAgg_strike.loc[fromStrike:toStrike]
    dfAgg_strike_mean = df.groupby(["StrikePrice"]).mean(numeric_only=True)
    dfAgg_strike_mean = dfAgg_strike_mean.loc[fromStrike:toStrike]
    dfAgg_exp = df.groupby(["ExpirationDate"]).sum(numeric_only=True)
    dfAgg_exp = dfAgg_exp.loc[: todayDate + timedelta(weeks=26)]
    dfAgg_exp_mean = df.groupby(["ExpirationDate"]).mean(numeric_only=True)
    dfAgg_exp_mean = dfAgg_exp_mean.loc[todayDate : todayDate + timedelta(weeks=26)]

    strikes = dfAgg_strike.index.values
    exp_dates = dfAgg_exp.index.values

    # average IVs over all options in dfAgg
    call_ivs = dfAgg_strike_mean["CallIV"]
    put_ivs = dfAgg_strike_mean["PutIV"]
    call_ivs_exp = dfAgg_exp_mean["CallIV"]
    put_ivs_exp = dfAgg_exp_mean["PutIV"]
    # ---=== CALCULATE EXPOSURE PROFILES ===---
    levels = np.linspace(fromStrike, toStrike, 60)
    nextExpiry = df["ExpirationDate"].min()

    df["IsThirdFriday"] = [isThirdFriday(x) for x in df.ExpirationDate]
    thirdFridays = df.loc[df["IsThirdFriday"] == True]
    nextMonthlyExp = thirdFridays["ExpirationDate"].min()

    totalDelta = []
    totalDeltaExNext = []
    totalDeltaExFri = []
    totalGamma = []
    totalGammaExNext = []
    totalGammaExFri = []
    totalVanna = []
    totalVannaExNext = []
    totalVannaExFri = []
    totalCharm = []
    totalCharmExNext = []
    totalCharmExFri = []
    # For each spot level, calc exposure at that point
    for level in levels:
        # print(time.perf_counter())
        df["callDeltaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
            calcDeltaEx(
                level,
                df["StrikePrice"],
                df["CallIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "call",
                df["CallOpenInt"],
            ),
            0,
        )
        df["putDeltaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
            calcDeltaEx(
                level,
                df["StrikePrice"],
                df["PutIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "put",
                df["PutOpenInt"],
            ),
            0,
        )
        df["callGammaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
            calcGammaEx(
                level,
                df["StrikePrice"],
                df["CallIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "call",
                df["CallOpenInt"],
            ),
            0,
        )
        df["putGammaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
            calcGammaEx(
                level,
                df["StrikePrice"],
                df["PutIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "put",
                df["PutOpenInt"],
            ),
            0,
        )
        df["callVannaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
            calcVannaEx(
                level,
                df["StrikePrice"],
                df["CallIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "call",
                df["CallOpenInt"],
            ),
            0,
        )
        df["putVannaEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
            calcVannaEx(
                level,
                df["StrikePrice"],
                df["PutIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "put",
                df["PutOpenInt"],
            ),
            0,
        )
        df["callCharmEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["CallIV"] > 0),
            calcCharmEx(
                level,
                df["StrikePrice"],
                df["CallIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "call",
                df["CallOpenInt"],
            ),
            0,
        )
        df["putCharmEx"] = np.where(
            np.logical_and(df["daysTillExp"] > 0, df["PutIV"] > 0),
            calcCharmEx(
                level,
                df["StrikePrice"],
                df["PutIV"],
                df["daysTillExp"],
                yield_10yr,
                dividend_yield,
                "put",
                df["PutOpenInt"],
            ),
            0,
        )
        # print(time.perf_counter())
        # delta exposure
        totalDelta.append(df["callDeltaEx"].sum() + df["putDeltaEx"].sum())
        exNxt = df.loc[df["ExpirationDate"] != nextExpiry]
        totalDeltaExNext.append(exNxt["callDeltaEx"].sum() + exNxt["putDeltaEx"].sum())
        exFri = df.loc[df["ExpirationDate"] != nextMonthlyExp]
        totalDeltaExFri.append(exFri["callDeltaEx"].sum() + exFri["putDeltaEx"].sum())
        # gamma exposure
        totalGamma.append(df["callGammaEx"].sum() - df["putGammaEx"].sum())
        totalGammaExNext.append(exNxt["callGammaEx"].sum() - exNxt["putGammaEx"].sum())
        totalGammaExFri.append(exFri["callGammaEx"].sum() - exFri["putGammaEx"].sum())
        # vanna exposure
        totalVanna.append(df["callVannaEx"].sum() - df["putVannaEx"].sum())
        totalVannaExNext.append(exNxt["callVannaEx"].sum() - exNxt["putVannaEx"].sum())
        totalVannaExFri.append(exFri["callVannaEx"].sum() - exFri["putVannaEx"].sum())
        # charm exposure
        totalCharm.append(df["callCharmEx"].sum() - df["putCharmEx"].sum())
        totalCharmExNext.append(exNxt["callCharmEx"].sum() - exNxt["putCharmEx"].sum())
        totalCharmExFri.append(exFri["callCharmEx"].sum() - exFri["putCharmEx"].sum())
    totalDelta = np.array(totalDelta) / 10**11
    totalDeltaExNext = np.array(totalDeltaExNext) / 10**11
    totalDeltaExFri = np.array(totalDeltaExFri) / 10**11
    totalGamma = np.array(totalGamma) / 10**9
    totalGammaExNext = np.array(totalGammaExNext) / 10**9
    totalGammaExFri = np.array(totalGammaExFri) / 10**9
    totalVanna = np.array(totalVanna) / 10**9
    totalVannaExNext = np.array(totalVannaExNext) / 10**9
    totalVannaExFri = np.array(totalVannaExFri) / 10**9
    totalCharm = np.array(totalCharm) / 10**9
    totalCharmExNext = np.array(totalCharmExNext) / 10**9
    totalCharmExFri = np.array(totalCharmExFri) / 10**9

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
        zeroDelta = zeroDelta[0]
    else:
        print("delta flip not found for " + ticker + " " + expir)
    if zeroGamma.size > 0:
        zeroGamma = zeroGamma[0]
    else:
        print("gamma flip not found for " + ticker + " " + expir)
    return (
        df,
        data_time,
        todayDate,
        strikes,
        exp_dates,
        spotPrice,
        fromStrike,
        toStrike,
        levels,
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
