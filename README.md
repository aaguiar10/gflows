# G|Flows

G|Flows, aka Greek Flows, provides 30-minute updates every Monday-Friday from 9:30am-4:30pm EST.

## Features:

- Measure delta, gamma, vanna, and charm exposure for the SPX, NDX, and RUT indexes using CBOE data (delayed 15min).
- Choose between exploring data for the current month or all expirations
- Need a refresh? View what each of the four available greeks mean and how they can interpreted

## Installation

Install the app's required packages

```{.sourceCode .bash}
$ pip install -r requirements.txt
```

(Recommended) To keep the package installation local/within a virtual environment, run these before the `pip` command

```{.sourceCode .bash}
$ python -m venv venv
$ source venv/bin/activate
```

Options data for your preferred ticker can be downloaded [here](https://www.cboe.com/delayed_quotes/cboe/quote_table) to update existing files in the `data` directory (which the **calc** module uses).

Upon completion, run the Dash app (available at http://localhost:8050)

```{.sourceCode .bash}
$ python my_app.py
```
