📊 Bond Relative Value (RV) Comparator

This is a Python Flask application designed for quantitative bond relative value analysis [cite: app.py]. It automates the process of normalizing differences in currency, coupon type, and benchmark to provide a true "like-for-like" comparison, resulting in a Rich/Cheap/Fair assessment for a portfolio of bonds [cite: services/analysis_service.py].

The application utilizes the Gemini API for intelligent Excel ingestion and optional real-time market data fetching [cite: app.py, services/realtime_data_service.py].

✨ Key Features

Ingestion Flexibility: Add bonds manually via a web form or upload a full Excel/CSV file containing bond details and market rates [cite: templates/index.html].

AI-Powered Parsing: Uses the Gemini API to intelligently parse complex Excel/CSV files, extracting structured bond and market data (e.g., Fair Value Curves, SOFR Spreads, Funding Rates) [cite: services/ingestion_service.py].

Normalization Engine (Part 3): Contains core reusable mathematical functions for neutralizing differences [cite: normalization_engine.py].

FX Hedging: Normalizes foreign currency bonds to a USD-hedged yield using the Covered Interest Parity (CIP) principle [cite: normalization_engine.py].

SOFR Equivalent Spreads: Converts floating-rate (SOFR) bonds into their fixed-rate equivalent yields for comparison against fixed-rate Treasury-linked bonds [cite: normalization_engine.py].

Interactive Workflow: A simple three-step UI process (Add Bonds → Review Market Data → Analysis Results) [cite: templates/index.html].

🚀 Getting Started

Prerequisites

Python 3.x

Gemini API Key: You must have a Gemini API key.

Installation

Set up your environment: Clone the repository or navigate to the project directory.

Install dependencies: This project uses a few standard libraries for web serving, AI interaction, and data handling.

pip install -r requirements.txt


The required packages are: Flask, google-generativeai, pandas, and openpyxl [cite: requirements.txt].

Configure API Key: Open config.py and replace the placeholder with your actual Gemini API Key.

# config.py
API_KEY = "YOUR_GEMINI_API_KEY_HERE"


How to Run

Execute the main application file from your terminal:

python app.py


The application will start in debug mode. Access the web interface at:
➡️ http://localhost:8080

🛠️ Application Structure

The code is organized into a clean, modular structure following a typical service-oriented pattern:

Bonds/
├── app.py                      # Main Flask entry point and controller routes [cite: app.py].
├── config.py                   # Configuration constants, API key, and static fallback data [cite: config.py].
├── normalization_engine.py       # Core pure math functions (FX, SOFR conversion, spread parsing) [cite: normalization_engine.py].
├── requirements.txt              # Project dependencies [cite: requirements.txt].
├── templates/
│   └── index.html              # Frontend user interface (3-step workflow) [cite: templates/index.html].
└── services/
    ├── __init__.py             # Python package marker.
    ├── ingestion_service.py    # Handles file upload and uses Gemini to parse Excel data [cite: services/ingestion_service.py].
    ├── market_data_service.py  # Consolidates benchmark, funding, and fair value data for analysis [cite: services/market_data_service.py].
    ├── realtime_data_service.py # Uses Gemini to fetch real-time market data from online sources (e.g., FRED, TradingEconomics) [cite: services/realtime_data_service.py].
    └── analysis_service.py     # Orchestrates Parts 2-5: ties market data and math together for final Rich/Cheap assessment [cite: services/analysis_service.py].


💡 Workflow and Core Logic

The analysis follows a 5-part structure to ensure true like-for-like comparison:

1 & 2. Data Ingestion and Market Context

Bonds are ingested, and the necessary market data (benchmark rates, funding rates, fair value curves, SOFR spreads) is gathered. The user can choose between using static data from config.py or fetching real-time data via Gemini [cite: app.py].

3. Normalization Engine (normalization_engine.py)

This module performs two critical normalization calculations:

FX Hedging (calculate_usd_hedged_yield): Converts a bond's local yield ($Y_{\text{Local}}$) to a USD-equivalent yield ($Y_{\text{Hedged}}$) by factoring in the interest rate differential (FX Hedge Cost) based on Covered Interest Parity (CIP) [cite: normalization_engine.py].
$$ Y_{\text{Hedged}} \approx Y_{\text{Local}} + (r_{\text{USD}} - r_{\text{FCY}}) $$

SOFR Equivalent Spread (calculate_sofr_equivalent_spread): Converts a fixed-rate bond's Treasury spread ($x$) into a floating-rate SOFR equivalent spread ($z$), crucial for comparing fixed vs. floating USD bonds [cite: normalization_engine.py].
$$ z = x + \text{T_SOFR_SPREAD} $$

4 & 5. Analysis and Assessment

The analysis_service.py calculates the final comparison metric using the USD-hedged yields [cite: services/analysis_service.py]:

$$ \text{Excess Yield (bps)} = \text{Offered Hedged Yield} - \text{Fair Hedged Yield} $$

The bond's final assessment is determined based on the following business logic thresholds:

Cheap (BUY): $\text{Excess Yield} > +5 \text{ bps}$ [cite: services/analysis_service.py]

Rich (PASS): $\text{Excess Yield} < -5 \text{ bps}$ [cite: services/analysis_service.py]

Fair (HOLD): $\text{Excess Yield}$ is between $-5 \text{ bps}$ and $+5 \text{ bps}$ [cite: services/analysis_service.py]
