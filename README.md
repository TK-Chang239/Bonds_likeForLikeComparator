# Bond Relative Value Analysis System

An intelligent bond analysis platform that performs comprehensive relative value (RV) analysis on corporate bonds. The system uses AI-powered data extraction, real-time market data fetching, and sophisticated financial calculations to determine if bonds are fairly priced, cheap (buy opportunity), or rich (overvalued).

## Features

### 🤖 AI-Powered Bond Data Extraction
- **Gemini API Integration**: Automatically extracts bond details from Excel files using Google's Gemini AI
- **Flexible Input**: Upload Excel files containing bond information or manually enter bond details
- **Smart Parsing**: Extracts coupon type, currency, tenor, rating, sector, and spread information

### 📊 Dual Data Source Options
1. **Real-time Online Sources** (via Gemini API):
   - US Treasury yields from Treasury.gov and FRED
   - SOFR rates from CME Group
   - FX spot rates from Bloomberg, OANDA, XE.com
   - Funding rates from central banks (Fed, ECB, Bank of Canada)
   - Fair value curves from Bloomberg BVAL and ICE BofA indices

2. **Static Configuration**:
   - Use data from uploaded Excel files
   - Fall back to predefined config.py values
   - Useful for testing and offline scenarios

### 💰 Comprehensive Financial Analysis
- **Local Yield Calculation**: Computes offered yields in local currency
- **SOFR Equivalent Spreads**: Converts fixed-rate bonds to floating equivalents
- **FX Hedging**: Uses Covered Interest Parity to hedge non-USD bonds to USD
- **Fair Value Comparison**: Compares offered yields to sector/rating benchmarks
- **Rich/Cheap Assessment**: Determines investment recommendation based on excess yield

### 🔄 Multi-Step Workflow
1. **Step 1**: Upload Excel or manually enter bond details
2. **Step 2**: Review and edit market data (benchmark rates, FX rates, fair value curves)
3. **Step 3**: View comprehensive analysis results with recommendations

## Architecture

```
Bonds/
├── app.py                      # Main Flask application (routing & orchestration)
├── config.py                   # Configuration (API keys, market data constants)
├── config.example.py           # Example configuration template
├── normalization_engine.py     # Core financial calculations
├── requirements.txt            # Python dependencies
├── services/
│   ├── ingestion_service.py        # Excel parsing & Gemini API integration
│   ├── market_data_service.py      # Market data retrieval (static/config)
│   ├── online_market_data_service.py  # Online data fetching orchestration
│   ├── realtime_data_service.py    # Gemini API real-time data fetching
│   └── analysis_service.py         # Relative value analysis logic
└── templates/
    └── index.html              # Single-page application UI
```

## Installation

### Prerequisites
- Python 3.8+
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Bonds
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the application**
   ```bash
   # Copy the example config file
   cp config.example.py config.py

   # Edit config.py and add your Gemini API key
   # Replace YOUR_GEMINI_API_KEY_HERE with your actual key
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the UI**
   Open your browser to: [http://localhost:8080](http://localhost:8080)

## Usage

### Option 1: Upload Excel File

1. Prepare an Excel file with bond information:
   - **Sheet 1 (Case)**: Bond details (Name, CPN Type, CCY, Tenor, Rating, Sector, Spread)
   - **Sheet 2 (FX Information)**: Spot rates and funding rates (optional)
   - **Sheet 3 (SOFR & Treasury Information)**: T-SOFR spreads (optional)
   - **Sheet 4 (Curves Information)**: Fair value curves by sector/rating (optional)

2. Upload the file in Step 1
3. Choose data source:
   - **Fetch from Online Sources**: Uses Gemini API to get real-time market data
   - **Use Data From Excel File**: Uses data from your Excel file or config.py

### Option 2: Manual Entry

1. Click "Add Bond Manually"
2. Fill in bond details:
   - Bond Name (e.g., "Bond A")
   - Coupon Type: Fixed or Float
   - Currency: USD, CAD, EUR, etc.
   - Tenor: Years to maturity
   - Rating: AAA, AA, A, BBB, etc.
   - Sector: Tech, Energy, Financials, etc.
   - Spread: Format as `BENCHMARK+XXbps` (e.g., `T+50bps`, `G+47bps`, `S+25bps`)

3. Add multiple bonds as needed
4. Choose data source and proceed

## Financial Methodology

### Yield Calculation

**For Fixed-Rate Bonds:**
```
Local YTM = Benchmark Rate + Credit Spread
```

**For Floating-Rate Bonds:**
```
SOFR Swap Rate = Treasury Rate - T_SOFR_SPREAD
Fixed Equivalent Yield = SOFR Swap Rate + SOFR Spread
```

**For SOFR Equivalent Bonds:**
```
z = x + T_SOFR_SPREAD
Bond Yield = SOFR Swap Rate + z
```
Where:
- `x` = Treasury spread from equivalent fixed bond
- `z` = SOFR equivalent spread
- `T_SOFR_SPREAD` = Treasury - SOFR spread

### FX Hedging (Covered Interest Parity)

```
USD Hedged Yield = Local Yield + (r_USD - r_FCY)
```
Where:
- `r_USD` = USD funding rate (e.g., 1Y SOFR)
- `r_FCY` = Foreign currency funding rate (e.g., EURIBOR, CORRA)

### Relative Value Assessment

```
Excess Yield = Offered Hedged Yield - Fair Hedged Yield
```

**Decision Thresholds:**
- **Cheap (BUY)**: Excess Yield > +5 bps
- **Fair (HOLD)**: -5 bps ≤ Excess Yield ≤ +5 bps
- **Rich (PASS)**: Excess Yield < -5 bps

## Data Sources

### When Using "Fetch from Online Sources"

| Data Type | Sources |
|-----------|---------|
| **Benchmark Rates** | Treasury.gov, FRED, TradingEconomics.com, CME Group |
| **Spot Exchange Rates** | Bloomberg, OANDA, XE.com, TradingEconomics.com |
| **Funding Rates** | CME SOFR, FRED, ECB, Bank of Canada, TradingEconomics.com |
| **Fair Value Curves** | Bloomberg BVAL, ICE BofA indices, FRED credit spreads |
| **SOFR/Treasury Data** | Treasury.gov, FRED, CME SOFR, Chatham Financial |

### When Using "Static Data"
- Uses market data from your Excel file if provided
- Falls back to `config.py` for missing data
- Useful for backtesting or offline analysis

## API Endpoints

### POST `/uploadExcel`
Uploads and parses an Excel file containing bond data.

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "bonds": [...],
  "benchmark_rates": {...},
  "spot_rates": {...},
  "funding_rates": {...},
  "fair_value_curves": {...},
  "sofr_spread_data": {...}
}
```

### POST `/submitBond`
Manually submits a single bond.

**Request:**
```json
{
  "bondName": "Bond A",
  "cpnType": "Fixed",
  "ccy": "CAD",
  "tenor": 1,
  "rating": "AA",
  "sector": "Tech",
  "spread": "G+47bps"
}
```

### POST `/fetchMarketData`
Fetches market data for bonds.

**Request:**
```json
{
  "bonds": [...],
  "use_realtime": true,  // or false for static data
  "benchmark_rates": {...},  // optional, from Excel
  ...
}
```

**Response:**
```json
{
  "market_data": [...],
  "data_sources": {
    "source_type": "online",  // or "excel" or "config"
    "timestamp": "November 16, 2025",
    "sources": {...}
  }
}
```

### POST `/analyze`
Runs relative value analysis on bonds.

**Request:**
```json
{
  "bonds": [...],
  "market_data_map": {...}  // optional, from review page
}
```

**Response:**
```json
{
  "results": [
    {
      "name": "Bond A",
      "assessment": "Cheap (BUY)",
      "excess_yield_bps": 12.50,
      ...
    }
  ]
}
```

## Configuration

### Market Data Constants

Edit `config.py` to customize static market data:

```python
# Benchmark rates (decimal format: 0.0344 = 3.44%)
MARKET_RATES = {
    'T': 0.0344,    # 1-Year US Treasury
    'G': 0.0320,    # 1-Year Canadian Government
    'MS': 0.0350,   # Mid-Swap rate
}

# Funding rates for FX hedging
FUNDING_RATES = {
    'USD': 0.0500,
    'CAD': 0.0450,
    'EUR': 0.0400,
    'GBP': 0.0425,
}

# Fair value curves (sector/rating specific)
FAIR_CURVES = {
    'USD_TECH': {
        'AA': 0.0400,
        'A': 0.0420,
        'BBB': 0.0450,
    },
    ...
}
```

## Development

### Project Structure

- **app.py**: Main Flask application, routing, and request handling
- **services/**: Modular business logic services
  - `ingestion_service.py`: Gemini AI parsing
  - `market_data_service.py`: Static data retrieval
  - `online_market_data_service.py`: Online data orchestration
  - `realtime_data_service.py`: Gemini API real-time fetching
  - `analysis_service.py`: RV analysis calculations
- **normalization_engine.py**: Pure financial calculation functions
- **templates/**: HTML UI with embedded JavaScript

### Adding New Features

1. **New Benchmark Rate**: Add to `MARKET_RATES` in config.py
2. **New Currency**: Add to `FUNDING_RATES` and update `FAIR_CURVES`
3. **New Sector**: Add curves to `FAIR_CURVES` for each currency
4. **New Data Source**: Modify `services/realtime_data_service.py`

## Troubleshooting

### Issue: "Config file not found"
**Solution**: Copy `config.example.py` to `config.py` and add your API key

### Issue: "Gemini API error"
**Solution**: Verify your API key in `config.py` is correct and has quota remaining

### Issue: "Excel parsing failed"
**Solution**: Ensure Excel file has sheets named "Case", "FX Information", etc.

### Issue: "No fair value curve found"
**Solution**: Add the CCY_SECTOR_RATING combination to `FAIR_CURVES` in config.py

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Acknowledgments

- **Google Gemini API**: For AI-powered data extraction and real-time market data fetching
- **Market Data Sources**: Treasury.gov, FRED, CME Group, Bloomberg, ICE BofA
- **Financial Methodology**: Based on standard fixed income relative value analysis techniques

## Contact

For questions or support, please open an issue on GitHub.

---

**Built with ❤️ using Flask, Gemini AI, and modern financial analysis techniques**
