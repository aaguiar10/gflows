import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, html, Input, Output, ctx, no_update
from dash.dependencies import Input, Output

import textwrap
from flask_caching import Cache
from calc import get_options_data
from ticker_dwn import dwn_data
from layout import serve_layout
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timedelta
from pytz import timezone
from dotenv import load_dotenv
from os import environ

load_dotenv()  # load environment variables from .env

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    ],
)
server = app.server
app.title = "G|Flows"
app.layout = serve_layout

cache = Cache(
    server,
    config={
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": "cache",
        "CACHE_THRESHOLD": 150,
    },
)


# download data at start
def sensor_init():
    # respond to prompt if env variable not set
    response = environ.get("AUTO_RESPONSE") or input("\nDownload recent data? (y/n): ")
    if response.lower() == "y":
        dwn_data()
        cache.delete_memoized(analyze_data)
    else:
        print("\nUsing existing data...\n")


def sensor():
    dwn_data()
    cache.delete_memoized(analyze_data)


# schedule when to redownload data
sched = BackgroundScheduler(daemon=True)
sched.add_job(
    sensor,
    CronTrigger.from_crontab(
        "0,30 9-16 * * 0-4", timezone=timezone("America/New_York")
    ),
)
sched.start()


@cache.memoize(timeout=60 * 30)  # cache charts for 30 min
def analyze_data(ticker, expir):
    # Analyze stored data of specified ticker and expiry
    # defaults: json format, timezone 'America/New_York'
    result = get_options_data(
        ticker,
        expir,
        is_json=True,  # False for CSV
        tz="America/New_York",
    )
    if result == None:
        return (None,) * 26
    return result


@app.callback(  # handle selected expiration
    Output("exp-value", "data"),
    Output("all-btn", "active"),
    Output("monthly-options", "value"),
    Input("monthly-options", "value"),
    Input("all-btn", "n_clicks"),
)
def on_click(value, btn):
    expir = no_update
    is_all_active = no_update
    current_val = no_update
    if "all-btn" == ctx.triggered_id:
        expir = "all"
        is_all_active = True
        current_val = ""
    elif "monthly-btn" == value:
        expir = "monthly"
        is_all_active = False
        current_val = "monthly-btn"
    elif "opex-btn" == value:
        expir = "opex"
        is_all_active = False
        current_val = "opex-btn"
    elif "0dte-btn" == value:
        expir = "0dte"
        is_all_active = False
        current_val = "0dte-btn"
    return expir, is_all_active, current_val


@app.callback(  # handle selected option greek
    Output("delta-btn", "active"),
    Output("gamma-btn", "active"),
    Output("vanna-btn", "active"),
    Output("charm-btn", "active"),
    Output("pagination", "active_page"),
    Output("live-dropdown", "options"),
    Output("live-dropdown", "value"),
    Input("delta-btn", "n_clicks"),
    Input("gamma-btn", "n_clicks"),
    Input("vanna-btn", "n_clicks"),
    Input("charm-btn", "n_clicks"),
)
def on_click(btn1, btn2, btn3, btn4):
    is_active1 = True
    is_active2 = False
    is_active3 = False
    is_active4 = False
    options = [
        "Absolute Delta Exposure",
        "Absolute Delta Exposure By Calls/Puts",
        "Delta Exposure Profile",
    ]
    value = "Absolute Delta Exposure"
    page = 1
    if "gamma-btn" == ctx.triggered_id:
        is_active1 = False
        is_active2 = True
        is_active3 = False
        is_active4 = False
        options = [
            "Absolute Gamma Exposure",
            "Absolute Gamma Exposure By Calls/Puts",
            "Gamma Exposure Profile",
        ]
        value = "Absolute Gamma Exposure"

    elif "vanna-btn" == ctx.triggered_id:
        is_active1 = False
        is_active2 = False
        is_active3 = True
        is_active4 = False
        options = [
            "Absolute Vanna Exposure",
            "Implied Volatility Average",
            "Vanna Exposure Profile",
        ]
        value = "Absolute Vanna Exposure"
    elif "charm-btn" == ctx.triggered_id:
        is_active1 = False
        is_active2 = False
        is_active3 = False
        is_active4 = True
        options = [
            "Absolute Charm Exposure",
            "Charm Exposure Profile",
        ]
        value = "Absolute Charm Exposure"
    return is_active1, is_active2, is_active3, is_active4, page, options, value


@app.callback(  # handle chart display based on inputs
    Output("live-chart", "figure"),
    Output("pagination-div", "hidden"),
    Output("monthly-options", "options"),
    Input("live-dropdown", "value"),
    Input("tabs", "active_tab"),
    Input("exp-value", "data"),
    Input("pagination", "active_page"),
)
def update_live_chart(value, stock, expiration, active_page):
    stock = f"{stock[1:].upper()}" if stock[0] == "^" else stock.upper()
    (
        df,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels,
        totaldelta,
        totaldelta_exnext,
        totaldelta_exfri,
        totalgamma,
        totalgamma_exnext,
        totalgamma_exfri,
        totalvanna,
        totalvanna_exnext,
        totalvanna_exfri,
        totalcharm,
        totalcharm_exnext,
        totalcharm_exfri,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
        call_ivs_exp,
        put_ivs_exp,
    ) = analyze_data(stock, expiration)
    if df is None:
        return (
            go.Figure(
                {
                    "data": [],
                    "layout": {
                        "title": {
                            "text": stock + " data unavailable, retry later",
                            "x": 0.5,
                            "font": {"size": 12.5},
                        }
                    },
                }
            ),
            True,
            no_update,
        )

    df_agg = (
        df.groupby(["strike_price"]).sum(numeric_only=True).loc[from_strike:to_strike]
    )
    strikes = df_agg.index.to_numpy()

    exp_dates = (
        df.groupby(["expiration_date"])
        .sum(numeric_only=True)
        .loc[: today_ddt + timedelta(weeks=26)]
    )
    exp_dates_x = exp_dates.index.to_numpy()

    if expiration == "monthly":
        legend_title = monthly_options_dates[0].strftime("%Y %b")
    elif expiration == "opex":
        legend_title = monthly_options_dates[1].strftime("%Y %b %d")
    elif expiration == "0dte":
        legend_title = monthly_options_dates[0].strftime("%Y %b %d")
    else:
        legend_title = "All Expirations"

    name = value.split()[1]
    num_type = " per 1% "
    scale = 10**9
    factor = 10**9
    if name == "Delta":
        scale = 10**11
        factor = 10**11
    elif name == "Charm":
        num_type = " a day "

    date_condition = active_page == 2 and not value.count("Profile")

    if date_condition:  # use dates
        strikes = exp_dates_x
        levels = exp_dates_x
        call_ivs = call_ivs_exp
        put_ivs = put_ivs_exp
        df_agg = exp_dates

    if (not value.count("Calls/Puts")) and value.count("Absolute"):
        fig = go.Figure(
            data=[
                go.Bar(
                    name=name + " Exposure",
                    x=strikes,
                    y=df_agg[f"total_{name.lower()}"].to_numpy(),
                    marker=dict(
                        line=dict(width=0.25, color="black"),
                    ),
                )
            ]
        )
    elif value.count("Calls/Puts"):
        fig = go.Figure(
            data=[
                go.Bar(
                    name="Call " + name,
                    x=strikes,
                    y=df_agg[f"call_{name[:1].lower()}ex"].to_numpy() / scale,
                    marker=dict(
                        line=dict(width=0.25, color="black"),
                    ),
                ),
                go.Bar(
                    name="Put " + name,
                    x=strikes,
                    y=df_agg[f"put_{name[:1].lower()}ex"].to_numpy() / scale,
                    marker=dict(
                        line=dict(width=0.25, color="black"),
                    ),
                ),
            ]
        )

    if not (value.count("Profile") or value.count("Average")):
        if name == "Vanna":
            y_title = " Exposure (delta / 1% IV move)"
            descript = stock + " IV Move, "
        elif name == "Charm":
            y_title = " Exposure (delta / day til expiry)"
            descript = "til " + stock + " Expiry, "
        elif name == "Gamma":
            y_title = " Exposure (delta / 1% move)"
            descript = stock + " Move, "
        else:
            y_title = " Exposure (price / 1% move)"
            descript = stock + " Move, "
        split_title = textwrap.wrap(
            "Total "
            + name
            + ": $"
            + str("{:,.2f}".format(df[f"total_{name.lower()}"].sum() * factor))
            + num_type
            + descript
            + today_ddt_string,
            width=50,
        )
        fig.update_layout(  # bar chart layout
            title_text="<br>".join(split_title),
            title_x=0.5,
            title_font_size=12.5,
            title_xref="paper",
            xaxis=({"title": ("Strike") if not date_condition else "Date"}),
            yaxis={"title": {"text": name + y_title}},
            showlegend=True,
            paper_bgcolor="#fff",
            margin=dict(l=0, r=40),
            legend=dict(
                title_text=legend_title,
                orientation="v",
                yanchor="top",
                xanchor="right",
                y=0.98,
                x=0.98,
                bgcolor="rgba(0,0,0,0.05)",
                font_size=10,
            ),
            barmode="relative",
            template="seaborn",
            modebar_remove=["autoscale", "lasso2d"],
        )
    if value.count("Profile") or value.count("Average"):
        name = value.split()[0]
        if name == "Delta":
            y_title = " Exposure (price / 1% move)"
            all_ex = totaldelta
            ex_next = totaldelta_exnext
            ex_fri = totaldelta_exfri
            zeroflip = zerodelta
        elif name == "Gamma":
            y_title = " Exposure (delta / 1% move)"
            all_ex = totalgamma
            ex_next = totalgamma_exnext
            ex_fri = totalgamma_exfri
            zeroflip = zerogamma
        elif name == "Vanna":
            y_title = " Exposure (delta / 1% IV move)"
            all_ex = totalvanna
            ex_next = totalvanna_exnext
            ex_fri = totalvanna_exfri
        elif name == "Charm":
            y_title = " Exposure (delta / day til expiry)"
            all_ex = totalcharm
            ex_next = totalcharm_exnext
            ex_fri = totalcharm_exfri
        fig = make_subplots(rows=1, cols=1)
        split_title = textwrap.wrap(
            f"{stock} {name} Exposure Profile, {today_ddt_string}", width=50
        )
        if not date_condition and name != "Implied":  # chart profiles
            fig.add_trace(go.Scatter(x=levels, y=all_ex, name="All Expiries"))
            fig.add_trace(go.Scatter(x=levels, y=ex_next, name="Next Expiry"))
            fig.add_trace(go.Scatter(x=levels, y=ex_fri, name="Next Monthly Expiry"))
            # show - &/or + areas of exposure depending on condition
            if name == "Charm" or name == "Vanna":
                all_ex_min = all_ex.min()
                all_ex_max = all_ex.max()
                min_n = [
                    all_ex_min,
                    ex_fri.min() if ex_fri.size != 0 else all_ex_min,
                    ex_next.min() if ex_next.size != 0 else all_ex_min,
                ]
                max_n = [
                    all_ex_max,
                    ex_fri.max() if ex_fri.size != 0 else all_ex_max,
                    ex_next.max() if ex_next.size != 0 else all_ex_max,
                ]
                min_n.sort()
                max_n.sort()
                if min_n[0] < 0:
                    fig.add_hrect(
                        y0=0,
                        y1=min_n[0] * 1.5,
                        fillcolor="red",
                        opacity=0.1,
                        line_width=0,
                    )
                if max_n[2] > 0:
                    fig.add_hrect(
                        y0=0,
                        y1=max_n[2] * 1.5,
                        fillcolor="green",
                        opacity=0.1,
                        line_width=0,
                    )
                fig.add_hline(
                    y=0,
                    line_width=0,
                    name=name + " Flip",
                    annotation_text=name + " Flip",
                    annotation_position="top left",
                )
            elif zeroflip.size > 0:  # greek has a - to + flip
                fig.add_vline(
                    x=zeroflip,
                    line_color="green",
                    line_width=1,
                    name=name + " Flip",
                    annotation_text=name + " Flip: " + str("{:,.0f}".format(zeroflip)),
                    annotation_position="top left",
                )
                fig.add_vrect(
                    x0=from_strike,
                    x1=zeroflip,
                    fillcolor="red",
                    opacity=0.1,
                    line_width=0,
                )
                fig.add_vrect(
                    x0=zeroflip,
                    x1=to_strike,
                    fillcolor="green",
                    opacity=0.1,
                    line_width=0,
                )
            elif all_ex[0] < 0:  # flip unknown, assume - dominance
                fig.add_vrect(
                    x0=from_strike,
                    x1=to_strike,
                    fillcolor="red",
                    opacity=0.1,
                    line_width=0,
                )
            elif all_ex[0] > 0:  # flip unknown, assume + dominance
                fig.add_vrect(
                    x0=from_strike,
                    x1=to_strike,
                    fillcolor="green",
                    opacity=0.1,
                    line_width=0,
                )
        elif name == "Implied":
            # in IV section, chart call/put IV averages
            fig.add_trace(
                go.Scatter(
                    x=strikes,
                    y=put_ivs * 100,
                    name="Put IV",
                    fill="tozeroy",
                    line_color="#C44E52",
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=strikes,
                    y=call_ivs * 100,
                    name="Call IV",
                    fill="tozeroy",
                    line_color="#32A3A3",
                )
            )

            split_title = textwrap.wrap(
                f"{stock} IV Average, {today_ddt_string}", width=50
            )
        fig.update_layout(  # scatter chart layout
            title_text="<br>".join(split_title),
            title_x=0.5,
            title_font_size=12.5,
            title_xref="paper",
            xaxis=({"title": ("Strike") if not date_condition else "Date"}),
            yaxis={
                "title": {
                    "text": (name + y_title)
                    if not (date_condition or value.count("Average"))
                    else "Implied Volatility (IV) Average"
                }
            },
            showlegend=True,
            legend=dict(
                title_text=legend_title,
                orientation="v",
                yanchor="top",
                xanchor="right",
                y=0.98,
                x=0.98,
                bgcolor="rgba(0,0,0,0.05)",
                font_size=10,
            ),
            paper_bgcolor="#fff",
            margin=dict(l=0, r=40),
            template="seaborn",
            modebar_remove=["autoscale"],
        )
        fig.add_hline(
            y=0,
            line_width=1,
            line_color="gray",
        )
    fig.update_xaxes(
        showgrid=True,
        minor=dict(ticklen=5, tickcolor="black", showgrid=True),
        range=(
            [spot_price * 0.9, spot_price * 1.1]
            if not date_condition
            else [
                today_ddt,
                today_ddt + timedelta(days=31),
            ]
        ),
        gridcolor="lightgray",
        gridwidth=1,
        rangeslider=dict(
            visible=True,
            range=(
                [from_strike, to_strike]
                if not date_condition
                else [
                    exp_dates_x.min() if exp_dates_x.size != 0 else today_ddt,
                    exp_dates_x.max()
                    if exp_dates_x.size != 0
                    else today_ddt + timedelta(days=31),
                ]
            ),
        ),
    )
    fig.update_yaxes(
        showgrid=True,
        fixedrange=True,
        minor_ticks="inside",
        gridcolor="lightgray",
        gridwidth=1,
    )
    if not date_condition:
        fig.add_vline(
            x=spot_price,
            line_color="slategray",
            line_width=1,
            line_dash="dash",
            name=stock + " Spot",
            annotation_text="Last: " + str("{:,.0f}".format(spot_price)),
            annotation_position="top",
        )

    pagination_hidden = False
    if value.count("Profile"):
        pagination_hidden = True

    # provide monthly option labels
    if len(monthly_options_dates) != 0:
        monthly_options = [
            {
                "label": monthly_options_dates[0].strftime("%Y %B"),
                "value": "monthly-btn",
            },
            {
                "label": html.Div(
                    children=[
                        monthly_options_dates[1].strftime("%Y %B %d"),
                        html.Span("*", className="align-super"),
                    ],
                    className="d-flex align-items-center",
                ),
                "value": "opex-btn",
            },
            {
                "label": monthly_options_dates[0].strftime("%Y %B %d"),
                "value": "0dte-btn",
            },
        ]
    else:
        monthly_options = no_update

    return fig, pagination_hidden, monthly_options


if __name__ == "__main__":
    cache.clear()
    sensor_init()
    app.run(debug=False, host="0.0.0.0", port="8050")
