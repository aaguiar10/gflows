from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime, timedelta


def monthly_exp():
    currdate = datetime.now()
    # if weekend, use friday's month/year for expiration
    if currdate.weekday() == 5:
        currdate = currdate - timedelta(1)
    elif currdate.weekday() == 6:
        currdate = currdate - timedelta(2)
    return str(currdate.year) + " " + currdate.strftime("%B")


def serve_layout():
    return dbc.Container(
        [
            dbc.Row(
                children=[
                    dbc.Button(
                        html.I(className="bi bi-info"),
                        color="info",
                        outline=True,
                        class_name="d-flex align-items-center justify-content-center",
                        style={
                            "width": "30px",
                            "height": "22px",
                            "font-size": "1.1rem",
                        },
                        id="info-btn",
                    ),
                    dbc.Popover(
                        dbc.PopoverBody(
                            children=[
                                "G|Flows, or Greek Flows, can measure various market risks that \
                            influence option prices. ",
                                html.Br(),
                                html.Span(
                                    "Monday-Friday: 30-minute updates from 9:30am-4:30pm ET (CBOE delayed data)",
                                    className="fst-italic",
                                ),
                            ]
                        ),
                        style={"font-size": "12px"},
                        target="info-btn",
                        trigger="hover",
                        placement="left",
                    ),
                ],
                class_name="d-flex justify-content-end m-auto mt-1",
            ),
            dbc.Row(
                html.Div(
                    html.H2("G|Flows"),
                    className="m-auto d-flex justify-content-center",
                )
            ),
            dbc.Row(
                dbc.Tabs(
                    id="tabs",
                    active_tab="spx",
                    children=[
                        dbc.Tab(
                            label="S&P 500 (SPX) Index",
                            tab_id="spx",
                        ),
                        dbc.Tab(
                            label="NASDAQ 100 (NDX) Index",
                            tab_id="ndx",
                        ),
                        dbc.Tab(
                            label="RUSSELL 2000 (RUT) Index",
                            tab_id="rut",
                        ),
                    ],
                    class_name="fs-5 p-0 nav-fill",
                )
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div(html.H4("Expirations"), className="mx-auto"),
                            dbc.ButtonGroup(
                                children=[
                                    dbc.Button(
                                        monthly_exp(),
                                        id="monthly-btn",
                                        color="primary",
                                        active=True,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "All",
                                        id="all-btn",
                                        color="primary",
                                        active=False,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                ],
                                id="exp-btns",
                            ),
                        ],
                        class_name="d-flex flex-column mt-2",
                    ),
                    dbc.Col(
                        [
                            html.Div(html.H4("Greeks"), className="mx-auto"),
                            dbc.ButtonGroup(
                                children=[
                                    dbc.Button(
                                        "Delta",
                                        id="delta-btn",
                                        color="primary",
                                        active=True,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "Gamma",
                                        id="gamma-btn",
                                        color="primary",
                                        active=False,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "Vanna",
                                        id="vanna-btn",
                                        color="primary",
                                        active=False,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        "Charm",
                                        id="charm-btn",
                                        color="primary",
                                        active=False,
                                        outline=True,
                                        n_clicks=0,
                                    ),
                                ],
                                id="greek-btns",
                                class_name="overflow-auto",
                            ),
                        ],
                        class_name="d-flex flex-column mt-2",
                    ),
                ],
            ),
            html.Div(id="exp-button-timestamp", hidden=True),
            html.Div(id="greek-button-timestamp", hidden=True),
            dbc.Row(
                dcc.Dropdown(
                    options=[
                        "Absolute Delta Exposure",
                        "Absolute Delta Exposure By Calls/Puts",
                        "Delta Exposure Profile",
                    ],
                    value="Absolute Delta Exposure",
                    clearable=False,
                    searchable=False,
                    id="live-dropdown",
                ),
                class_name="mt-2",
            ),
            dbc.Row(
                html.Div(
                    dbc.Pagination(
                        id="pagination",
                        active_page=1,
                        max_value=2,
                        size="sm",
                        class_name="d-flex justify-content-end mt-2 mb-0 me-1",
                    ),
                    id="pagination-div",
                    hidden=True,
                )
            ),
            dcc.Loading(
                id="loading-icon",
                children=[
                    dbc.Row(
                        dcc.Graph(id="live-chart", responsive=True),
                        class_name="vw-100 vh-100 mt-0",
                    )
                ],
                type="default",
            ),
            dbc.Row(
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            children=[
                                "Delta measures how much an option's price changes due to \
                        a change in the underlying asset's price. \
                        G|Flows measures the delta exposure for a 1% move in asset price, \
                        which shows how much an option's price will change from that asset \
                        move.\n\n\
                        Long (+) delta: long calls and short puts have positive delta that \
                        will benefit from an asset's increase\nShort (-) delta: long \
                        puts and short calls have negative delta that will benefit \
                        from an asset's decrease\n\n\
                        Options that are ",
                                html.Span(
                                    "in the money",
                                    id="tooltip1",
                                    style={
                                        "textDecoration": "underline",
                                        "cursor": "pointer",
                                    },
                                ),
                                " (ITM) have a higher delta than ",
                                html.Span(
                                    "out of the money",
                                    id="tooltip2",
                                    style={
                                        "textDecoration": "underline",
                                        "cursor": "pointer",
                                    },
                                ),
                                " (OTM) options.",
                                dbc.Tooltip(
                                    "call: asset price above option strike\n\
                                    put: asset price under option strike",
                                    target="tooltip1",
                                    style={"white-space": "pre-line"},
                                    placement="bottom",
                                ),
                                dbc.Tooltip(
                                    "call: asset price under option strike\n\
                                    put: asset price above option strike",
                                    target="tooltip2",
                                    style={"white-space": "pre-line"},
                                    placement="bottom",
                                ),
                            ],
                            title="Delta (∂V/∂S)",
                        ),
                        dbc.AccordionItem(
                            "Gamma measures how much an option's delta changes due to \
                        a change in the underlying asset's price.\
                        G|Flows measures the gamma exposure for a 1% move in asset price, \
                        which shows how much an option's delta will change from that asset move.\n\
                        \nLong (+) gamma: hedging goes against the market \
                        (buy the dip, sell rallies), \
                        which reduces volatility and stabilizes the market\
                        \nLong (+) gamma: in positive gamma, the strikes with large + exposures \
                        are 'walls' to break through and often push price away to \
                        the nearest significant - exposure\
                        \nShort (-) gamma: hedging goes with the market (selling more as the \
                        price falls / buying more as it moves up), \
                        which brings volatility and destabilizes the market\
                        \nShort (-) gamma: in negative gamma, the strikes with large - \
                        exposures are 'walls' to break through but often are price magnets\n\
                        \nFor example, if total \
                        gamma was 1.2 billion, that amount would be sold for a 1% move up and \
                        bought for a 1% move down. If it was -1.2 billion, that amount would be \
                        sold for a 1% move down and bought for a 1% move up.",
                            title="Gamma (∂Δ/∂S)",
                        ),
                        dbc.AccordionItem(
                            "Vanna measures how much an option's delta changes due to a change in \
                        the underlying asset's implied volatility (IV). \
                        G|Flows measures the vanna exposure for a 1% move in IV, \
                        which shows how much an option's delta will change from that IV move.\n\
                        \nLong (+) vanna: every 1% IV decrease will decrease delta (induces buying)\n\
                        Long (+) vanna: every 1% IV increase will increase delta (induces selling)\n\
                        Short (-) vanna: every 1% IV increase will decrease delta (induces buying)\n\
                        Short (-) vanna: every 1% IV decrease will increase delta (induces selling)\n\
                        \nSupportive vanna flows are strongest the week before / of \
                        options expiration (OPEX). This is usually the 3rd Friday of \
                        each month for monthly options or end-of-quarter (EOQ) for \
                        quarterly options. \
                        VIX expiration (usually on a Wednesday and 30 days before the next monthly OPEX) \
                        removes some of the flows and opens a window of vulnerability, while\
                        OPEX removes all flows. Once expired, the market is more vulnerable \
                        to events until the end of the month when its flows pick up again.",
                            title="Vanna (∂Δ/∂σ)",
                        ),
                        dbc.AccordionItem(
                            "Charm measures how much an option's delta changes due to time passing. \
                        G|Flows measures the charm exposure for each day until an option expires, \
                        which shows how much an option's delta will change from 1 day passing.\n\
                        \nLong (+) charm: each day passing will increase delta \
                        for ITM calls and OTM puts (induces selling)\n\
                        Short (-) charm: each day passing will decrease delta \
                        for ITM puts and OTM calls (induces buying)\n\
                        \nSupportive charm flows are strongest the week before / of \
                        options expiration (OPEX). This is usually the 3rd Friday of \
                        each month for monthly options or end-of-quarter (EOQ) for \
                        quarterly options. \
                        VIX expiration (usually on a Wednesday and 30 days before the next monthly OPEX) \
                        removes some of the flows and opens a window of vulnerability, while\
                        OPEX removes all flows. Once expired, the market is more vulnerable \
                        to events until the end of the month when its flows pick up again.",
                            title="Charm (∂Δ/∂t)",
                        ),
                    ],
                    start_collapsed=True,
                    style={"white-space": "pre-line"},
                ),
                class_name="vw-100",
            ),
            html.Hr(className="mb-0"),
            html.Footer(
                html.Div(
                    children=[
                        dbc.Button(
                            html.Span(
                                children=[
                                    html.Img(
                                        src="assets/cup.webp",
                                        style={"width": "30px", "height": "auto"},
                                    ),
                                    html.Span(
                                        "Support the Creator",
                                        className="ms-1",
                                        style={"font-size": "14px"},
                                    ),
                                ],
                                className="d-inline-flex align-items-center justify-content-center",
                            ),
                            color="light",
                            class_name="d-flex",
                            id="kofi-btn",
                        ),
                        dbc.Popover(
                            children=[
                                dbc.PopoverBody(
                                    html.Iframe(
                                        id="kofiframe",
                                        src="https://ko-fi.com/aaguiar/?hidefeed=true&widget=true&embed=true&preview=true",
                                        style={
                                            "border": "none",
                                            "width": "100%",
                                            "background": "#f9f9f9",
                                        },
                                        height="360",
                                        title="aguiar",
                                    ),
                                    class_name="pb-0",
                                ),
                                dbc.PopoverHeader(
                                    html.A(
                                        "View page",
                                        href="https://ko-fi.com/aaguiar",
                                        target="_blank",
                                        className="link-dark",
                                    ),
                                    class_name="d-flex justify-content-center",
                                    style={
                                        "border-top": "2px solid rgba(0,0,0,.5)",
                                        "font-size": "0.9rem",
                                    },
                                ),
                            ],
                            target="kofi-btn",
                            trigger="legacy",
                            placement="top",
                            class_name="mw-100",
                        ),
                    ],
                    className="d-flex justify-content-center",
                ),
                className="mt-auto py-2",
            ),
        ],
        class_name="vw-100 vh-100",
        fluid=True,
    )
