import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.io as pio
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
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.themes.FLATLY,
        dbc.icons.BOOTSTRAP,
    ],
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    ],
    title="G|Flows",
)
server = app.server
app.layout = serve_layout

cache = Cache(
    server,
    config={
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": "cache",
        "CACHE_THRESHOLD": 150,
    },
)

cache.clear()


@cache.memoize(timeout=60 * 15)  # cache charts for 15 min
def analyze_data(ticker, expir):
    # Analyze stored data of specified ticker and expiry
    # defaults: json format, timezone 'America/New_York'
    result = get_options_data(
        ticker,
        expir,
        is_json=True,  # False for CSV
        tz="America/New_York",
    )
    return (None,) * 26 if result is None else result


def sensor():
    # default: json format
    dwn_data(is_json=True)  # False for CSV
    cache.delete("cached_data")
    cache.delete_memoized(analyze_data)


# respond to prompt if env variable not set
response = environ.get("AUTO_RESPONSE")
if not response:
    try:
        response = input("\nDownload recent data? (y/n): ")
    except EOFError:
        response = "n"
if response.strip().lower() == "y":  # download data at start
    sensor()
else:
    print("\nUsing existing data...\n")

# schedule when to redownload data
sched = BackgroundScheduler(daemon=True)
sched.add_job(
    sensor,
    CronTrigger.from_crontab(
        "0,15,30,45 9-15 * * 0-4", timezone=timezone("America/New_York")
    ),
)
sched.add_job(
    sensor,
    CronTrigger.from_crontab(
        "0,15,30 16 * * 0-4", timezone=timezone("America/New_York")
    ),
)
sched.start()


app.clientside_callback(  # toggle light or dark theme
    """ 
    (themeToggle, theme) => {
        let themeLink = themeToggle ? theme[1] : theme[0]
        let kofiBtn = themeToggle ? "dark" : "light"
        let kofiLink = themeToggle ? "link-light" : "link-dark"
        let stylesheets = document.querySelectorAll(
            'link[rel=stylesheet][href^="https://cdn.jsdelivr"]'
        )      
        stylesheets[1].href = themeLink
        // Update theme after a short delay
        setTimeout(() => {stylesheets[0].href = themeLink;}, 100)
        return [window.dash_clientside.no_update, kofiBtn, kofiLink]
    }
    """,
    Output("switch", "id"),
    Output("kofi-btn", "color"),
    Output("kofi-link-color", "className"),
    Input("switch", "value"),
    Input("theme-store", "data"),
)


@app.callback(  # handle selected expiration
    Output("exp-value", "data"),
    Output("all-btn", "active"),
    Output("monthly-options", "value"),
    Input("monthly-options", "value"),
    Input("all-btn", "n_clicks"),
)
def on_click(value, btn):
    button_map = {
        "monthly-btn": ("monthly", False, "monthly-btn"),
        "opex-btn": ("opex", False, "opex-btn"),
        "0dte-btn": ("0dte", False, "0dte-btn"),
    }
    if "all-btn" == ctx.triggered_id:
        return "all", True, ""
    else:
        return button_map.get(value, (no_update, no_update, no_update))


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
    is_active1, is_active2, is_active3, is_active4 = True, False, False, False
    options, value = [
        "Absolute Delta Exposure",
        "Absolute Delta Exposure By Calls/Puts",
        "Delta Exposure Profile",
    ], "Absolute Delta Exposure"
    page = 1
    if "gamma-btn" == ctx.triggered_id:
        is_active1, is_active2, is_active3, is_active4 = False, True, False, False
        options, value = [
            "Absolute Gamma Exposure",
            "Absolute Gamma Exposure By Calls/Puts",
            "Gamma Exposure Profile",
        ], "Absolute Gamma Exposure"
    elif "vanna-btn" == ctx.triggered_id:
        is_active1, is_active2, is_active3, is_active4 = False, False, True, False
        options, value = [
            "Absolute Vanna Exposure",
            "Implied Volatility Average",
            "Vanna Exposure Profile",
        ], "Absolute Vanna Exposure"
    elif "charm-btn" == ctx.triggered_id:
        is_active1, is_active2, is_active3, is_active4 = False, False, False, True
        options, value = [
            "Absolute Charm Exposure",
            "Charm Exposure Profile",
        ], "Absolute Charm Exposure"
    return is_active1, is_active2, is_active3, is_active4, page, options, value


@app.callback(
    Output("sensor", "data"),
    Input("interval", "n_intervals"),
)
def check_cache_key(n_intervals):
    return (not cache.has("cached_data")) or no_update


@app.callback(  # handle chart display based on inputs
    Output("live-chart", "figure"),
    Output("pagination-div", "hidden"),
    Output("monthly-options", "options"),
    Input("live-dropdown", "value"),
    Input("tabs", "active_tab"),
    Input("exp-value", "data"),
    Input("pagination", "active_page"),
    Input("sensor", "data"),
    Input("switch", "value"),
)
def update_live_chart(value, stock, expiration, active_page, refresh, toggle_dark):
    stock = f"{stock[1:]}" if stock[0] == "^" else stock
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
    ) = analyze_data(stock.lower(), expiration)
    cache.set("cached_data", True)

    xaxis, yaxis = dict(
        gridcolor="lightgray", minor=dict(ticklen=5, tickcolor="#000", showgrid=True)
    ), dict(gridcolor="lightgray", minor=dict(tickcolor="#000"))
    layout = {
        "title_x": 0.5,
        "title_font_size": 12.5,
        "title_xref": "paper",
        "legend": dict(
            orientation="v",
            yanchor="top",
            xanchor="right",
            y=0.98,
            x=0.98,
            bgcolor="rgba(0,0,0,0.1)",
            font_size=10,
        ),
        "showlegend": True,
        "margin": dict(l=0, r=40),
        "xaxis": xaxis,
        "yaxis": yaxis,
        "dragmode": "pan",
    }
    if not toggle_dark:
        pio.templates["custom_template"] = pio.templates["seaborn"]
    else:
        pio.templates["custom_template"] = pio.templates["plotly_dark"]
        for axis in [xaxis, yaxis]:
            axis["gridcolor"], axis["minor"]["tickcolor"] = "#373737", "#707070"
        layout["paper_bgcolor"] = "#222222"
        layout["plot_bgcolor"] = "rgba(40, 40, 50, 0.8)"
    pio.templates["custom_template"].update(layout=layout)
    pio.templates.default = "custom_template"

    if df is None:
        return (
            go.Figure(layout={"title_text": f"{stock} data unavailable, retry later"}),
            True,
            no_update,
        )

    date_condition = active_page == 2 and not "Profile" in value
    if not date_condition:
        df_agg = (
            df.groupby(["strike_price"])
            .sum(numeric_only=True)
            .loc[from_strike:to_strike]
        )
    else:  # use dates
        df_agg = (
            df.groupby(["expiration_date"])
            .sum(numeric_only=True)
            .loc[: today_ddt + timedelta(weeks=26)]
        )
        call_ivs, put_ivs = call_ivs_exp, put_ivs_exp

    if len(monthly_options_dates) != 0:
        date_formats = {
            "monthly": monthly_options_dates[0].strftime("%Y %b"),
            "opex": monthly_options_dates[1].strftime("%Y %b %d"),
            "0dte": monthly_options_dates[0].strftime("%Y %b %d"),
        }
        legend_title = date_formats[expiration]
        monthly_options = [  # provide monthly option labels
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
        legend_title = "All Expirations"
        monthly_options = no_update

    strikes = df_agg.index.to_numpy()

    is_profile_or_volatility = "Profile" in value or "Average" in value
    value_split = value.split()
    name = value_split[1] if not is_profile_or_volatility else value_split[0]
    name_to_vars = {
        "Delta": (f"per 1% {stock} Move", f"{name} Exposure (price / 1% move)"),
        "Gamma": (f"per 1% {stock} Move", f"{name} Exposure (delta / 1% move)"),
        "Vanna": (
            f"per 1% {stock} IV Move",
            f"{name} Exposure (delta / 1% IV move)",
        ),
        "Charm": (
            f"a day til {stock} Expiry",
            f"{name} Exposure (delta / day til expiry)",
        ),
        "Implied": ("", "Implied Volatility (IV) Average"),
    }

    description, y_title = name_to_vars[name]
    yaxis.update(title_text=y_title)
    scale = 10**9

    if "Absolute" in value and not "Calls/Puts" in value:
        fig = go.Figure(
            data=[
                go.Bar(
                    name=name + " Exposure",
                    x=strikes,
                    y=df_agg[f"total_{name.lower()}"].to_numpy(),
                    marker=dict(
                        line=dict(
                            width=0.25,
                            color=("#2B5078" if not toggle_dark else "#8795FA"),
                        ),
                    ),
                )
            ]
        )
    elif "Calls/Puts" in value:
        fig = go.Figure(
            data=[
                go.Bar(
                    name="Call " + name,
                    x=strikes,
                    y=df_agg[f"call_{name[:1].lower()}ex"].to_numpy() / scale,
                    marker=dict(
                        line=dict(
                            width=0.25,
                            color=("#2B5078" if not toggle_dark else "#8795FA"),
                        ),
                    ),
                ),
                go.Bar(
                    name="Put " + name,
                    x=strikes,
                    y=df_agg[f"put_{name[:1].lower()}ex"].to_numpy() / scale,
                    marker=dict(
                        line=dict(
                            width=0.25,
                            color=("#9B5C30" if not toggle_dark else "#F5765B"),
                        ),
                    ),
                ),
            ]
        )

    if not is_profile_or_volatility:
        split_title = textwrap.wrap(
            f"Total {name}: $"
            + str("{:,.2f}".format(df[f"total_{name.lower()}"].sum() * scale))
            + f" {description}, {today_ddt_string}",
            width=50,
        )
        fig.update_layout(  # bar chart layout
            title_text="<br>".join(split_title),
            legend_title_text=legend_title,
            xaxis=xaxis,
            yaxis=yaxis,
            barmode="relative",
            modebar_remove=["autoscale", "lasso2d"],
        )
    if is_profile_or_volatility:
        fig = make_subplots(rows=1, cols=1)
        if not date_condition and name != "Implied":  # chart profiles
            split_title = textwrap.wrap(
                f"{stock} {name} Exposure Profile, {today_ddt_string}", width=50
            )
            name_to_vars = {
                "Delta": (totaldelta, totaldelta_exnext, totaldelta_exfri, zerodelta),
                "Gamma": (totalgamma, totalgamma_exnext, totalgamma_exfri, zerogamma),
                "Vanna": (totalvanna, totalvanna_exnext, totalvanna_exfri, None),
                "Charm": (totalcharm, totalcharm_exnext, totalcharm_exfri, None),
            }
            all_ex, ex_next, ex_fri, zeroflip = name_to_vars[name]
            fig.add_trace(go.Scatter(x=levels, y=all_ex, name="All Expiries"))
            fig.add_trace(go.Scatter(x=levels, y=ex_next, name="Next Expiry"))
            fig.add_trace(go.Scatter(x=levels, y=ex_fri, name="Next Monthly Expiry"))
            # show - &/or + areas of exposure depending on condition
            if name == "Charm" or name == "Vanna":
                all_ex_min, all_ex_max = all_ex.min(), all_ex.max()
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
            # greek has a - to + flip
            elif zeroflip.size > 0:
                fig.add_vline(
                    x=zeroflip,
                    line_color="dimgray",
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
            # flip unknown, assume - dominance
            elif all_ex[0] < 0:
                fig.add_vrect(
                    x0=from_strike,
                    x1=to_strike,
                    fillcolor="red",
                    opacity=0.1,
                    line_width=0,
                )
            # flip unknown, assume + dominance
            elif all_ex[0] > 0:
                fig.add_vrect(
                    x0=from_strike,
                    x1=to_strike,
                    fillcolor="green",
                    opacity=0.1,
                    line_width=0,
                )
        elif name == "Implied":  # in IV section, chart put/call IV averages
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
        fig.add_hline(
            y=0,
            line_width=1,
            line_color="dimgray",
        )
        fig.update_layout(  # scatter chart layout
            title_text="<br>".join(split_title),
            legend_title_text=legend_title,
            xaxis=xaxis,
            yaxis=yaxis,
            modebar_remove=["autoscale"],
        )

    fig.update_xaxes(
        title="Strike" if not date_condition else "Date",
        showgrid=True,
        range=(
            [spot_price * 0.9, spot_price * 1.1]
            if not date_condition
            else [
                today_ddt,
                today_ddt + timedelta(days=31),
            ]
        ),
        gridwidth=1,
        rangeslider=dict(visible=True),
    )
    fig.update_yaxes(
        showgrid=True,
        fixedrange=True,
        minor_ticks="inside",
        gridwidth=1,
    )

    if not date_condition:
        fig.add_vline(
            x=spot_price,
            line_color="#707070",
            line_width=1,
            line_dash="dash",
            name=stock + " Spot",
            annotation_text="Last: " + str("{:,.2f}".format(spot_price)),
            annotation_position="top",
        )

    is_pagination_hidden = "Profile" in value

    return fig, is_pagination_hidden, monthly_options


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port="8050")
