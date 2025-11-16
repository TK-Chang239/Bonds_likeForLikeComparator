# =====================================================================================
# Configuration File
# -------------------------------------------------------------------------------------
# This file stores global constants and configuration settings
# for the application, like API keys and model names.
# =====================================================================================

# Leave the API key as an empty string.
# Canvas will automatically provide it in the runtime environment.
API_KEY = "AIzaSyBaa-s00WF6kVf-XtTuqkThRvARtVGBsfU"

# Define the model we want to use for parsing
MODEL_NAME = 'gemini-2.5-flash-preview-09-2025'

# =====================================================================================
# Market Data Constants (Part 2)
# -------------------------------------------------------------------------------------
# These constants simulate real-time market data that would normally come from APIs.
# In production, these would be fetched from:
# - Treasury yields: https://home.treasury.gov/resource-center/data-chart-center/interest-rates
# - SOFR swap rates: https://www.chathamfinancial.com/technology/us-market-rates
# - SOFR rates: https://www.cmegroup.com/markets/interest-rates/sofr.html
# - Funding rates: TradingEconomics.com, Investing.com
# - Fair value curves: Bloomberg BVAL, ICE BofA (paid APIs)
# =====================================================================================

# Data Sources Attribution
DATA_SOURCES = {
    "treasury_yields": "U.S. Department of the Treasury - Resource Center",
    "sofr_rates": "CME Group / Chatham Financial",
    "funding_rates": "TradingEconomics.com / Investing.com",
    "fair_value_curves": "Bloomberg BVAL / ICE BofA (simulated)",
    "last_updated": "Simulated data - In production, would fetch real-time"
}

# Basis points conversion: 1 bps = 0.0001 (1/10000)
BPS_CONVERSION = 10000

# Benchmark rates (T = Treasury, G = Government, MS = Mid-Swap, etc.)
# Values are in decimal format (e.g., 0.0344 = 3.44%)
MARKET_RATES = {
    'T': 0.0344,    # 1-Year US Treasury
    'G': 0.0320,    # 1-Year Canadian Government
    'MS': 0.0350,   # Mid-Swap rate
}

# Funding rates for currency hedging (Covered Interest Parity)
# Values are in decimal format (annual rates)
FUNDING_RATES = {
    'USD': 0.0500,  # 5.00% USD funding rate
    'CAD': 0.0450,  # 4.50% CAD funding rate
    'EUR': 0.0400,  # 4.00% EUR funding rate
    'GBP': 0.0425,  # 4.25% GBP funding rate
}

# SOFR Spread Data (Treasury - SOFR spreads by tenor)
# Structure: {tenor: {'T_RATE': decimal, 'T_SOFR_SPREAD': decimal}}
SOFR_SPREADS = {
    '1': {
        'T_RATE': 0.0344,      # 1-Year Treasury rate
        'T_SOFR_SPREAD': 0.0025,  # T - SOFR spread (25 bps)
    },
    '5': {
        'T_RATE': 0.0400,
        'T_SOFR_SPREAD': 0.0030,
    },
    '10': {
        'T_RATE': 0.0420,
        'T_SOFR_SPREAD': 0.0035,
    },
}

# Fair Value Curves (Part 4 - The "Answer Key")
# Structure: {CURRENCY_SECTOR: {RATING: fair_ytm_decimal}}
# These represent the "fair" YTM for bonds of a given profile
FAIR_CURVES = {
    'USD_TECH': {
        'AAA': 0.0380,
        'AA': 0.0400,
        'A': 0.0420,
        'BBB': 0.0450,
    },
    'USD_ENERGY': {
        'AAA': 0.0375,
        'AA': 0.0395,
        'A': 0.0415,
        'BBB': 0.0445,
    },
    'USD_FINANCIALS': {
        'AAA': 0.0385,
        'AA': 0.0405,
        'A': 0.0425,
        'BBB': 0.0455,
    },
    'CAD_TECH': {
        'AAA': 0.0360,
        'AA': 0.0380,
        'A': 0.0400,
        'BBB': 0.0430,
    },
    'CAD_ENERGY': {
        'AAA': 0.0355,
        'AA': 0.0375,
        'A': 0.0395,
        'BBB': 0.0425,
    },
    'CAD_FINANCIALS': {
        'AAA': 0.0365,
        'AA': 0.0385,
        'A': 0.0405,
        'BBB': 0.0435,
    },
    'EUR_TECH': {
        'AAA': 0.0350,
        'AA': 0.0370,
        'A': 0.0390,
        'BBB': 0.0420,
    },
    'EUR_ENERGY': {
        'AAA': 0.0345,
        'AA': 0.0365,
        'A': 0.0385,
        'BBB': 0.0415,
    },
    'EUR_FINANCIALS': {
        'AAA': 0.0355,
        'AA': 0.0375,
        'A': 0.0395,
        'BBB': 0.0425,
    },
}