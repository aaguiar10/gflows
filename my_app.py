from dash import Dash, html, Input, Output, ctx, no_update
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from flask_caching import Cache
from calc import getOptionsData
from ticker_dwn import dwn_data
from layout import serve_layout
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timedelta
from pytz import UTC
import textwrap

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


def sensor():
    dwn_data()
    cache.delete_memoized(query_data)


# download data then schedule when to redownload
sched = BackgroundScheduler(daemon=True)
sched.add_job(sensor)
sched.add_job(sensor, CronTrigger.from_crontab("0,30 13-20 * * 0-4", timezone=UTC))
sched.start()


@cache.memoize(timeout=60 * 30)  # cache charts for 30 min
def query_data(ticker, expir):
    # Retrieve stored CBOE data of specified ticker & expiry
    result = getOptionsData(ticker, expir)
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
            "Vanna Exposure (w/ IV) Profile",
            "Vanna Exposure (w/ IV) Profile By Date ",
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
            "Charm Exposure Profile By Date",
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
def update_live_chart(value, stock, expiration, is_iv):
    (
        df,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spotprice,
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
    ) = query_data(stock, expiration)
    stock = stock.upper()
    if df is None:
        return (
            go.Figure(
                {
                    "data": [],
                    "layout": {
                        "title": {
                            "text": stock + " data unavailable, retry later",
                            "x": 0.5,
                            "font": {"size": 13},
                        }
                    },
                }
            ),
            True,
            no_update,
        )
    dfAgg = (
        df.groupby(["StrikePrice"]).sum(numeric_only=True).loc[from_strike:to_strike]
    )
    strikes = dfAgg.index.to_numpy()
    exp_dates = (
        df.groupby(["ExpirationDate"])
        .sum(numeric_only=True)
        .loc[: today_ddt + timedelta(weeks=26)]
        .index.to_numpy()
    )

    if expiration == "monthly":
        legend_title = monthly_options_dates[0].strftime("%Y %b")
    elif expiration == "opex":
        legend_title = monthly_options_dates[1].strftime("%Y %b %d")
    elif expiration == "0dte":
        legend_title = monthly_options_dates[2].strftime("%Y %b %d")
    else:
        legend_title = "All Expirations"

    name = value.split()[1]
    name_date = value.count("By Date")
    num_type = " per 1% "
    scale = 10**9
    factor = 10**9
    if name == "Delta":
        scale = 10**11
        factor = 10**11
    elif name == "Charm":
        num_type = " a day "
    if name_date:  # use dates
        strikes = exp_dates
        levels = exp_dates
        call_ivs = call_ivs_exp
        put_ivs = put_ivs_exp
    if (not value.count("Calls/Puts")) and value.count("Absolute"):
        fig = go.Figure(
            data=[
                go.Bar(
                    name=name + " Exposure",
                    x=strikes,
                    y=dfAgg["Total" + name].to_numpy(),
                    width=(6 if not name_date else None),
                    marker=dict(
                        line=dict(width=1, color="black"),
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
                    y=dfAgg["Call" + name[:1] + "EX"].to_numpy() / scale,
                    width=(6 if not name_date else None),
                    marker=dict(
                        line=dict(width=1, color="black"),
                    ),
                ),
                go.Bar(
                    name="Put " + name,
                    x=strikes,
                    y=dfAgg["Put" + name[:1] + "EX"].to_numpy() / scale,
                    width=(6 if not name_date else None),
                    marker=dict(
                        line=dict(width=1, color="black"),
                    ),
                ),
            ]
        )
    if not value.count("Profile"):
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
            + str("{:,.2f}".format(df["Total" + name].sum() * factor))
            + num_type
            + descript
            + today_ddt_string,
            width=50,
        )
        fig.update_layout(  # bar chart layout
            title_text="<br>".join(split_title),
            title_x=0.5,
            title_font_size=13,
            title_xref="paper",
            xaxis=({"title": ("Strike") if not name_date else "Date"}),
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
            barmode="overlay",
            modebar_remove=["autoscale", "lasso2d"],
        )
    if value.count("Profile"):
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
            stock + " " + name + " Exposure Profile, " + today_ddt_string, width=50
        )
        if is_iv == 1:  # chart profiles normally
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
        elif name == "Vanna" and is_iv == 2:
            # in Vanna section, chart profiles that show call/put iv
            fig.add_trace(
                go.Scatter(
                    x=strikes,
                    y=put_ivs * 100,
                    name="Put IV",
                    fill="tozeroy",
                    line_color="indianred",
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
                stock + " IV Profile, " + today_ddt_string, width=50
            )
        fig.update_layout(  # scatter chart layout
            title_text="<br>".join(split_title),
            title_x=0.5,
            title_font_size=13,
            title_xref="paper",
            xaxis=({"title": ("Strike") if not name_date else "Date"}),
            yaxis={
                "title": {
                    "text": (name + y_title)
                    if is_iv == 1
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
            [spotprice * 0.9, spotprice * 1.1]
            if not value.count("By Date")
            else [today_ddt, today_ddt + timedelta(days=31)]
        ),
        gridcolor="lightgray",
        gridwidth=1,
        rangeslider=dict(
            visible=True,
            range=(
                [from_strike, to_strike]
                if not value.count("By Date")
                else [
                    exp_dates.min() if exp_dates.size != 0 else today_ddt,
                    exp_dates.max() if exp_dates.size != 0 else today_ddt,
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
    if not value.count("Date"):
        fig.add_vline(
            x=spotprice,
            line_color="slategray",
            line_width=1,
            line_dash="dash",
            name=stock + " Spot",
            annotation_text="Last: " + str("{:,.0f}".format(spotprice)),
            annotation_position="top",
        )

    pagination_hidden = True
    if value.count("Profile") and name == "Vanna":
        pagination_hidden = False

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
                "label": monthly_options_dates[2].strftime("%Y %B %d"),
                "value": "0dte-btn",
            },
        ]
    else:
        monthly_options = no_update

    return fig, pagination_hidden, monthly_options


if __name__ == "__main__":
    cache.clear()
    app.run(debug=False)
