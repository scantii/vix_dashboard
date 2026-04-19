# VIX dashboard

A small **Plotly Dash** app that shows **VIX term structure**, **VVIX** context, and simple **regime / signal** summaries using the [Tastytrade](https://developer.tastytrade.com/) API for live data, with **Yahoo Finance** (via `yfinance`) for daily index history when REST candles are unavailable.

## Requirements

- **Python 3.10+** (3.11+ recommended)
- A [Tastytrade](https://tastytrade.com/) account and OAuth **application** credentials (client secret + refresh token) for live quotes and chain data

## Install

Clone or download this repository, then from your environment:

```bash
pip install -r requirements.txt
```

The package expects to be importable as `vix_dashboard`. Typical layout:

```text
your-workspace/
  vix_dashboard/          # this repository (the Python package)
    __init__.py
    main.py
    config.py
    ...
```

Add the **parent** of the `vix_dashboard` folder to `PYTHONPATH`, or run commands with that parent as the current working directory (see below).

## Configuration

1. Copy `.env.example` to `.env` inside the `vix_dashboard` package directory (next to `config.py`).
2. Set **required** variables for live API access:

| Variable       | Purpose                                      |
|----------------|----------------------------------------------|
| `TT_SECRET`    | OAuth client secret from Tastytrade          |
| `TT_REFRESH`   | OAuth refresh token                          |

Optional: `TT_API_VERSION`, `TT_USER_AGENT`, and `VIX_PANEL_CSV` (offline panel CSV). See `.env.example` for details.

## Run

From the directory that **contains** the `vix_dashboard` package (the parent of `vix_dashboard/`):

```bash
# Windows PowerShell example — adjust the path
cd path\to\parent
set PYTHONPATH=%CD%
python -m vix_dashboard.main
```

Or on macOS/Linux:

```bash
cd /path/to/parent
export PYTHONPATH="$PWD"
python -m vix_dashboard.main
```

The app serves at **http://127.0.0.1:8050/** by default.

Alternatively, from the same parent directory:

```bash
python path/to/vix_dashboard/launcher.py
```

That starts the app and opens your default browser.

## Security and privacy

- Treat `TT_SECRET` and `TT_REFRESH` like passwords; **never** commit `.env` (it is gitignored).
- The dev server is intended for **local use** (`127.0.0.1`). Do not expose it on the public internet without authentication, TLS, and `debug=False` in production settings.
- Historical index data may be fetched from **Yahoo Finance** when Tastytrade REST history is unavailable.

## Disclaimer

This is an educational / personal tooling project. It is **not** financial advice. Market data may be delayed or inaccurate. Use at your own risk.
