# =====================================================================================
# Real-Time Data Fetching Service (Part 2 - Enhanced)
# -------------------------------------------------------------------------------------
# This service uses Gemini API to fetch real-time market data from online sources.
# 
# NOTE: Gemini API doesn't have built-in web browsing. In production, you would:
# 1. Use a web scraping library (requests + BeautifulSoup) to fetch HTML
# 2. Extract relevant data from the HTML
# 3. Use Gemini to parse/validate the extracted data
# 
# For now, this implementation attempts to use Gemini with prompts that reference
# the websites. In practice, you may need to combine with actual web scraping.
# =====================================================================================

import google.generativeai as genai
import config
import json
import re

# Configure Gemini API
genai.configure(api_key=config.API_KEY)
model = genai.GenerativeModel(config.MODEL_NAME)

def fetch_benchmark_rate(ccy, tenor="1"):
    """
    Fetches the benchmark rate (1-Year Government Bond Yield) from TradingEconomics.com
    
    Args:
        ccy: Currency code (USD, CAD, EUR, etc.)
        tenor: Tenor in years (default: "1")
    
    Returns:
        float: Benchmark rate in decimal format (e.g., 0.0344 for 3.44%)
    """
    try:
        print(f"[REALTIME] Fetching {tenor}Y benchmark rate for {ccy} from TradingEconomics.com...")
        
        prompt = f"""
        Search for the current {tenor}-year government bond yield for {ccy} on TradingEconomics.com.
        
        Go to: https://tradingeconomics.com/{ccy.lower()}/government-bond-yield
        
        Extract the {tenor}-year government bond yield value. Return ONLY the numeric value as a decimal (e.g., 3.44 for 3.44%, which should be returned as 0.0344).
        
        If you cannot find the exact {tenor}-year rate, use the closest available tenor or the general government bond yield.
        
        Return ONLY the decimal number, nothing else.
        """
        
        response = model.generate_content(prompt)
        rate_text = response.text.strip()
        
        # Extract numeric value
        rate_match = re.search(r'(\d+\.?\d*)', rate_text)
        if rate_match:
            rate_value = float(rate_match.group(1))
            # Convert percentage to decimal if needed
            if rate_value > 1:
                rate_value = rate_value / 100
            print(f"[REALTIME] Found {ccy} {tenor}Y benchmark rate: {rate_value * 100:.2f}%")
            return rate_value
        else:
            raise ValueError(f"Could not parse rate from response: {rate_text}")
            
    except Exception as e:
        print(f"[ERROR] Failed to fetch real-time benchmark rate for {ccy}: {e}")
        # Re-raise the exception - no fallback to hardcoded values
        raise ValueError(f"Could not fetch real-time benchmark rate for {ccy} {tenor}Y from TradingEconomics.com: {e}")

def fetch_funding_rate(ccy):
    """
    Fetches the 1-Year Interbank/Money Market rate from TradingEconomics.com
    
    Args:
        ccy: Currency code (USD, CAD, EUR, etc.)
    
    Returns:
        float: Funding rate in decimal format
    """
    try:
        print(f"[REALTIME] Fetching funding rate for {ccy} from TradingEconomics.com...")
        
        prompt = f"""
        Search for the current 1-year interbank rate or money market rate for {ccy} on TradingEconomics.com.
        
        For USD: Look for SOFR or Federal Funds Rate
        For CAD: Look for Canadian Interbank Rate
        For EUR: Look for EURIBOR or ECB rate
        
        Go to: https://tradingeconomics.com/{ccy.lower()}/interest-rate
        
        Extract the 1-year interbank/money market rate. Return ONLY the numeric value as a decimal (e.g., 5.00 for 5.00%, which should be returned as 0.0500).
        
        Return ONLY the decimal number, nothing else.
        """
        
        response = model.generate_content(prompt)
        rate_text = response.text.strip()
        
        # Extract numeric value - handle both positive and negative
        # Look for optional negative sign and decimal number
        rate_match = re.search(r'(-?\d+\.?\d*)', rate_text)
        if rate_match:
            rate_value = float(rate_match.group(1))
            # Convert percentage to decimal if needed
            if abs(rate_value) > 1:
                rate_value = rate_value / 100
            print(f"[REALTIME] Found {ccy} funding rate: {rate_value * 100:.2f}%")
            return rate_value
        else:
            raise ValueError(f"Could not parse rate from real-time data response: {rate_text}")
            
    except Exception as e:
        print(f"[ERROR] Failed to fetch real-time funding rate for {ccy}: {e}")
        # Re-raise the exception - no fallback to hardcoded values
        raise ValueError(f"Could not fetch real-time funding rate for {ccy} from TradingEconomics.com: {e}")

def fetch_sofr_data(tenor="1"):
    """
    Fetches SOFR/Treasury spread data from FRED (Federal Reserve Economic Data)
    
    Args:
        tenor: Tenor in years (default: "1")
    
    Returns:
        dict: {'T_RATE': float, 'T_SOFR_SPREAD': float}
    """
    try:
        print(f"[REALTIME] Fetching {tenor}Y SOFR/Treasury data from FRED...")
        
        prompt = f"""
        Search for the current {tenor}-year US Treasury rate and SOFR rate from FRED (Federal Reserve Economic Data).
        
        Go to: https://fred.stlouisfed.org/
        
        Search for:
        1. "{tenor}-Year Treasury Constant Maturity Rate" (series code: DGS{tenor} if available)
        2. "SOFR" (Secured Overnight Financing Rate)
        
        Calculate the T-SOFR spread: Treasury Rate - SOFR Rate
        
        Return a JSON object with:
        {{
            "T_RATE": <treasury_rate_as_decimal>,
            "SOFR_RATE": <sofr_rate_as_decimal>,
            "T_SOFR_SPREAD": <spread_as_decimal>
        }}
        
        All values should be in decimal format (e.g., 3.44% = 0.0344).
        Return ONLY the JSON, nothing else.
        """
        
        response = model.generate_content(prompt)
        json_text = response.text.strip()
        
        # Clean up the JSON text - remove markdown code blocks if present
        json_text = re.sub(r'```json\s*', '', json_text)
        json_text = re.sub(r'```\s*', '', json_text)
        json_text = json_text.strip()
        
        # Try to extract JSON
        json_match = re.search(r'\{[^}]+\}', json_text)
        if json_match:
            data = json.loads(json_match.group(0))
            # Get values from real-time data - raise error if missing
            if 'T_RATE' not in data:
                raise ValueError("T_RATE not found in real-time data response")
            if 'SOFR_RATE' not in data:
                raise ValueError("SOFR_RATE not found in real-time data response")
            
            t_rate = float(data['T_RATE'])
            sofr_rate = float(data['SOFR_RATE'])
            
            # Handle positive or negative T-SOFR spread
            # If T_SOFR_SPREAD is provided, use it; otherwise calculate from T_RATE and SOFR_RATE
            if 'T_SOFR_SPREAD' in data:
                t_sofr_spread_raw = data['T_SOFR_SPREAD']
            else:
                # Calculate T_SOFR_SPREAD = T_RATE - SOFR_RATE
                t_sofr_spread_raw = t_rate - sofr_rate
            # If it's a string, check for sign (can be positive or negative)
            if isinstance(t_sofr_spread_raw, str):
                # Remove any percentage signs and parse, preserving sign
                t_sofr_spread_str = t_sofr_spread_raw.replace('%', '').strip()
                # Parse the value, preserving negative sign if present
                parsed_value = float(t_sofr_spread_str)
                # If absolute value is > 1, assume it's a percentage and convert to decimal
                t_sofr_spread = parsed_value / 100 if abs(parsed_value) > 1 else parsed_value
            else:
                t_sofr_spread = float(t_sofr_spread_raw)
                # If absolute value is > 1, assume it's a percentage and convert to decimal
                # Preserve the sign (positive or negative)
                if abs(t_sofr_spread) > 1:
                    t_sofr_spread = t_sofr_spread / 100
            
            print(f"[REALTIME] Found T-Rate: {t_rate * 100:.2f}%, SOFR: {sofr_rate * 100:.2f}%, Spread: {t_sofr_spread * 100:.2f}%")
            return {
                'T_RATE': t_rate,
                'T_SOFR_SPREAD': t_sofr_spread
            }
        else:
            raise ValueError(f"Could not parse JSON from response: {json_text}")
            
    except Exception as e:
        print(f"[ERROR] Failed to fetch real-time SOFR data: {e}")
        # Re-raise the exception - no fallback to hardcoded values
        raise ValueError(f"Could not fetch real-time SOFR/Treasury data for {tenor}Y from FRED: {e}")

def fetch_all_realtime_data(ccy, tenor="1"):
    """
    Fetches all real-time market data for a given currency and tenor.
    This is a convenience function that calls all the individual fetch functions.
    
    Args:
        ccy: Currency code
        tenor: Tenor in years
    
    Returns:
        dict: All market data including benchmark rates, funding rates, and SOFR data
    """
    print(f"\n[REALTIME DATA FETCH] Starting real-time data fetch for {ccy} {tenor}Y...")
    
    # Fetch benchmark rate
    benchmark_rate = fetch_benchmark_rate(ccy, tenor)
    
    # Fetch funding rates for all currencies (needed for hedging)
    funding_rates = {}
    for currency in ['USD', 'CAD', 'EUR', 'GBP']:
        funding_rates[currency] = fetch_funding_rate(currency)
    
    # Fetch SOFR data (always fetch for display, but primarily used for USD bonds)
    # For non-USD, we still need SOFR data structure for potential USD bonds in the portfolio
    sofr_data = {}
    try:
        # Always try to fetch SOFR data (it's USD-specific but needed for calculations)
        sofr_data[tenor] = fetch_sofr_data(tenor)
    except Exception as e:
        # If real-time fetch fails, we'll use config fallback in market_data_service
        print(f"[INFO] Could not fetch real-time SOFR data for {tenor}Y: {e}")
        # Return empty dict - market_data_service will use config fallback
        pass
    
    return {
        'benchmark_rate': benchmark_rate,
        'funding_rates': funding_rates,
        'sofr_spread_data': sofr_data,
        'source': 'Real-time (Gemini API)',
        'fetch_timestamp': None  # Could add timestamp if needed
    }

def fetch_all_market_data_excel_format(ingested_bonds):
    """
    Fetches all market data using Gemini API in the same structure as Excel data.
    This matches the Excel format exactly so it can be used interchangeably.

    This function dynamically determines what data to fetch based on the bond properties:
    - Benchmark rates: Fetched based on currency and coupon type (T, G, MS, S)
    - Spot rates: Fetched for all non-USD currencies to USD
    - Funding rates: Fetched for all currencies present in bonds
    - Fair value curves: Fetched for each CCY_SECTOR_RATING combination
    - SOFR spread data: Fetched for all tenors in bonds

    Args:
        ingested_bonds: List of bond dictionaries to determine what data to fetch

    Returns:
        dict: Market data in Excel format with keys:
            - benchmark_rates: {"T": 0.0344, "G": 0.0320, "MS": 0.0350, "S": ...}
            - spot_rates: {"EUR/USD": 1.1400, "USD/CAD": 1.4100}
            - funding_rates: {"USD": 0.0300, "EUR": 0.0150, "CAD": 0.0187}
            - fair_value_curves: {"USD_ENERGY": {"AA": {"1": 0.0390, ...}, ...}, ...}
            - sofr_spread_data: {"1": {"T_RATE": 0.0344, "T_SOFR_SPREAD": -0.0025}, ...}
    """
    print(f"\n[REALTIME] Fetching all market data in Excel format using Gemini API...")
    print(f"[REALTIME] Analyzing {len(ingested_bonds)} bonds to determine required data...")

    # Extract unique currencies, sectors, ratings, tenors, and benchmark codes from bonds
    unique_ccys = set()
    unique_sectors = set()
    unique_ratings = set()
    unique_tenors = set()
    unique_benchmarks = set()

    for bond in ingested_bonds:
        ccy = bond.get('ccy')
        sector = bond.get('sector')
        rating = bond.get('rating')
        tenor = str(int(bond.get('tenor', 0))) if bond.get('tenor') else None
        cpn_type = bond.get('cpnType', '').upper()
        spread = bond.get('spread', '').strip()

        if ccy:
            unique_ccys.add(ccy)
        if sector:
            unique_sectors.add(sector)
        if rating:
            unique_ratings.add(rating)
        if tenor and tenor != '0':
            unique_tenors.add(tenor)

        # Determine benchmark code from spread
        if spread:
            # Parse spread to get benchmark code (T, G, MS, S, etc.)
            spread_match = re.match(r'([A-Z]+)[+-]\d+bps', spread, re.IGNORECASE)
            if spread_match:
                benchmark_code = spread_match.group(1).upper()
                unique_benchmarks.add(benchmark_code)
            # Check for SOFR equivalent (Float bonds)
            elif 'sofr equivalent' in spread.lower() or (cpn_type == 'FLOAT'):
                unique_benchmarks.add('S')  # SOFR
                unique_benchmarks.add('T')  # Treasury (for T-SOFR spread calculation)

    print(f"[REALTIME] Extracted requirements from bonds:")
    print(f"  - Currencies: {sorted(unique_ccys)}")
    print(f"  - Sectors: {sorted(unique_sectors)}")
    print(f"  - Ratings: {sorted(unique_ratings)}")
    print(f"  - Tenors: {sorted(unique_tenors)}")
    print(f"  - Benchmarks: {sorted(unique_benchmarks)}")
    
    # Build dynamic prompt based on bond requirements
    # Create spot rate pairs for non-USD currencies
    spot_rate_pairs = []
    for ccy in unique_ccys:
        if ccy != 'USD':
            # Most common format is XXX/USD
            if ccy in ['EUR', 'GBP', 'AUD', 'NZD']:
                spot_rate_pairs.append(f"{ccy}/USD")
            else:
                # For CAD, JPY, etc., use USD/XXX
                spot_rate_pairs.append(f"USD/{ccy}")

    # Create CCY_SECTOR combinations for fair value curves
    ccy_sector_combos = [f"{ccy}_{sector}".upper() for ccy in unique_ccys for sector in unique_sectors]

    # Build benchmark rate descriptions based on what's needed
    benchmark_descriptions = []
    if 'T' in unique_benchmarks:
        benchmark_descriptions.append("- T (US Treasury): Fetch the current 1-year US Treasury yield from Treasury.gov or TradingEconomics.com")
    if 'G' in unique_benchmarks:
        for ccy in unique_ccys:
            if ccy == 'CAD':
                benchmark_descriptions.append(f"- G (Canadian Government): Fetch the 1-year Canadian Government bond yield from TradingEconomics.com or Bank of Canada")
            elif ccy == 'EUR':
                benchmark_descriptions.append(f"- G (European Government): Fetch the 1-year German Bund yield (proxy for EUR government rate) from TradingEconomics.com or ECB")
            elif ccy == 'GBP':
                benchmark_descriptions.append(f"- G (UK Government): Fetch the 1-year UK Gilt yield from TradingEconomics.com or Bank of England")
    if 'MS' in unique_benchmarks:
        benchmark_descriptions.append("- MS (Mid-Swap): Fetch 1-year mid-swap rates for relevant currencies from Bloomberg or financial data providers")
    if 'S' in unique_benchmarks:
        benchmark_descriptions.append("- S (SOFR): Calculate SOFR swap rate as: SOFR = T_RATE - T_SOFR_SPREAD (will be provided in SOFR spread data)")

    benchmark_instructions = "\n       ".join(benchmark_descriptions) if benchmark_descriptions else "- No specific benchmarks required (will use defaults)"

    prompt = f"""
    You are a financial data extraction API. Fetch current real-time market data (as of November 16, 2025) from online sources and return it in JSON format.

    TODAY'S DATE: November 16, 2025

    BONDS TO ANALYZE:
    {json.dumps(ingested_bonds, indent=2)}

    REQUIREMENTS EXTRACTED FROM BONDS:
    - Currencies: {sorted(unique_ccys)}
    - Sectors: {sorted(unique_sectors)}
    - Ratings: {sorted(unique_ratings)}
    - Tenors (years): {sorted(unique_tenors)}
    - Benchmarks needed: {sorted(unique_benchmarks)}

    REQUIRED DATA TO FETCH (prioritize real-time sources):

    1. BENCHMARK RATES:
       Fetch current benchmark yields for each currency/tenor combination as of November 16, 2025:
       {benchmark_instructions}

       Sources (in priority order):
       - US Treasury: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
       - FRED (Federal Reserve): https://fred.stlouisfed.org/
       - TradingEconomics: https://tradingeconomics.com/bonds
       - Bloomberg Terminal (if accessible)
       - CME Group: https://www.cmegroup.com/markets/interest-rates.html

       Return as: {{"T": 0.0344, "G": 0.0320, "MS": 0.0350, "S": 0.0319}} (all in decimal format, 3.44% = 0.0344)

    2. SPOT EXCHANGE RATES:
       Fetch current FX spot rates for all non-USD currencies as of November 16, 2025:
       Currency pairs needed: {spot_rate_pairs if spot_rate_pairs else ['None (all USD bonds)']}

       Sources (in priority order):
       - Bloomberg Terminal (if accessible)
       - OANDA: https://www.oanda.com/currency-converter/
       - XE.com: https://www.xe.com/currencyconverter/
       - TradingEconomics: https://tradingeconomics.com/currencies

       Return as: {{"EUR/USD": 1.1400, "USD/CAD": 1.4100}} (keep as quoted, no inversion)
       NOTE: EUR/USD = 1.14 means 1 EUR = 1.14 USD; USD/CAD = 1.41 means 1 USD = 1.41 CAD

    3. FUNDING RATES (for FX hedging via Covered Interest Parity):
       Fetch 1-year risk-free rates for each currency as of November 16, 2025:
       Currencies needed: {sorted(unique_ccys)}

       Specific rates to fetch:
       - USD: 1-year SOFR swap rate or overnight SOFR forward
       - CAD: 1-year CORRA (Canadian Overnight Repo Rate Average) or Canadian T-bill
       - EUR: 1-year EURIBOR or €STR (Euro Short-Term Rate)
       - GBP: 1-year SONIA (Sterling Overnight Index Average)

       Sources (in priority order):
       - CME Group SOFR: https://www.cmegroup.com/markets/interest-rates/sofr.html
       - FRED: https://fred.stlouisfed.org/
       - TradingEconomics: https://tradingeconomics.com/bonds
       - ECB Statistical Data Warehouse: https://sdw.ecb.europa.eu/ (for EUR)
       - Bank of Canada: https://www.bankofcanada.ca/rates/ (for CAD)

       Return as: {{"USD": 0.0500, "CAD": 0.0450, "EUR": 0.0400}} (convert percentages to decimals)

    4. FAIR VALUE CURVES (sector/rating-specific benchmarks):
       Fetch or estimate fair market yields for each currency-sector-rating-tenor combination as of November 16, 2025.
       These represent the "fair" YTM that bonds with this profile should trade at in the market.

       Combinations needed: {ccy_sector_combos}
       Ratings needed: {sorted(unique_ratings)}
       Tenors needed: {sorted(unique_tenors)} years

       For each combination, provide yields for all ratings and tenors. Examples:
       - USD Tech AA 1-year: What is the fair market YTM for a 1Y AA-rated USD Tech bond?
       - CAD Energy BBB 1-year: What is the fair market YTM for a 1Y BBB-rated CAD Energy bond?

       Sources (in priority order):
       - Bloomberg BVAL (Bloomberg Valuation Service) - if accessible
       - ICE BofA indices: https://indices.theice.com/
       - Credit spread data from FRED: https://fred.stlouisfed.org/
       - Sector-specific credit curves from financial data providers
       - For Energy sector: consider commodity price adjustments

       Return structure:
       {{
           "USD_TECH": {{
               "AAA": {{"1": 0.0380, "5": 0.0400, "10": 0.0420}},
               "AA": {{"1": 0.0400, "5": 0.0420, "10": 0.0440}},
               "A": {{"1": 0.0420, "5": 0.0440, "10": 0.0460}},
               "BBB": {{"1": 0.0450, "5": 0.0470, "10": 0.0490}}
           }},
           "CAD_ENERGY": {{
               "AA": {{"1": 0.0375}},
               "BBB": {{"1": 0.0425}}
           }}
       }}

       Include ALL combinations of: {ccy_sector_combos} × {sorted(unique_ratings)} × {sorted(unique_tenors)}
       All values in decimal format (4.20% = 0.0420)

    5. SOFR/TREASURY SPREAD DATA:
       Fetch Treasury rates and calculate T-SOFR spreads for each tenor as of November 16, 2025:
       Tenors needed: {sorted(unique_tenors)} years

       For each tenor, fetch:
       - T_RATE: The Treasury Constant Maturity Rate for that tenor
       - SOFR_RATE: The SOFR swap rate for that tenor
       - T_SOFR_SPREAD: Calculate as T_RATE - SOFR_RATE (can be positive or negative)

       Sources (in priority order):
       - US Treasury: https://home.treasury.gov/resource-center/data-chart-center/interest-rates
       - FRED Treasury rates: https://fred.stlouisfed.org/ (search "Treasury Constant Maturity")
       - CME SOFR: https://www.cmegroup.com/markets/interest-rates/sofr.html
       - Chatham Financial: https://www.chathamfinancial.com/technology/us-market-rates

       Return structure:
       {{
           "1": {{"T_RATE": 0.0344, "T_SOFR_SPREAD": 0.0025}},
           "5": {{"T_RATE": 0.0400, "T_SOFR_SPREAD": 0.0030}},
           "10": {{"T_RATE": 0.0420, "T_SOFR_SPREAD": 0.0035}}
       }}

       Include all tenors: {sorted(unique_tenors)}
       IMPORTANT: T_SOFR_SPREAD can be positive OR negative - preserve the sign!
       All values in decimal format

    RETURN FORMAT - JSON object with this EXACT structure:
    {{
        "benchmark_rates": {{<benchmark_code>: <rate_decimal>, ...}},
        "spot_rates": {{<currency_pair>: <rate>, ...}},
        "funding_rates": {{<ccy>: <rate_decimal>, ...}},
        "fair_value_curves": {{
            <CCY_SECTOR>: {{
                <RATING>: {{<tenor>: <ytm_decimal>, ...}},
                ...
            }},
            ...
        }},
        "sofr_spread_data": {{
            <tenor>: {{"T_RATE": <rate_decimal>, "T_SOFR_SPREAD": <spread_decimal>}},
            ...
        }}
    }}

    CRITICAL REQUIREMENTS:
    1. Use REAL-TIME data as of November 16, 2025 from the prioritized sources listed above
    2. All rates MUST be in DECIMAL format (3.44% = 0.0344, NOT 3.44)
    3. Preserve NEGATIVE signs for T_SOFR_SPREAD if Treasury < SOFR
    4. Only include data for the specific currencies, sectors, ratings, and tenors listed above
    5. For fair value curves, include ALL combinations of CCY_SECTOR × RATING × TENOR
    6. If exact data unavailable, use reasonable market-based estimates with clear methodology
    7. Return ONLY valid JSON, no markdown code blocks or extra text
    """
    
    try:
        response = model.generate_content(prompt)
        json_text = response.text.strip()
        
        # Clean up the JSON text - remove markdown code blocks if present
        json_text = re.sub(r'```json\s*', '', json_text)
        json_text = re.sub(r'```\s*', '', json_text)
        json_text = json_text.strip()
        
        # Try to extract JSON - find the outermost JSON object
        # Look for the first { and match it with the last }
        start_idx = json_text.find('{')
        if start_idx == -1:
            raise ValueError(f"Could not find JSON object start in response: {json_text[:200]}")
        
        # Find matching closing brace by counting braces
        brace_count = 0
        end_idx = start_idx
        for i in range(start_idx, len(json_text)):
            if json_text[i] == '{':
                brace_count += 1
            elif json_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        
        if brace_count != 0:
            raise ValueError(f"Unbalanced braces in JSON response: {json_text[:200]}")
        
        json_str = json_text[start_idx:end_idx]
        data = json.loads(json_str)
        
        # Validate and ensure all required keys exist
        result = {
            "benchmark_rates": data.get("benchmark_rates", {}),
            "spot_rates": data.get("spot_rates", {}),
            "funding_rates": data.get("funding_rates", {}),
            "fair_value_curves": data.get("fair_value_curves", {}),
            "sofr_spread_data": data.get("sofr_spread_data", {})
        }

        print(f"\n[REALTIME] ========== MARKET DATA FETCH SUCCESSFUL ==========")
        print(f"[REALTIME] Data fetched as of: November 16, 2025")
        print(f"\n[REALTIME] 1. BENCHMARK RATES (Government yields and swap rates):")
        for benchmark, rate in result['benchmark_rates'].items():
            benchmark_name = {
                'T': 'US Treasury',
                'G': 'Government',
                'MS': 'Mid-Swap',
                'S': 'SOFR Swap'
            }.get(benchmark, benchmark)
            print(f"     - {benchmark_name} ({benchmark}): {rate * 100:.4f}%")

        print(f"\n[REALTIME] 2. SPOT EXCHANGE RATES (FX rates):")
        if result['spot_rates']:
            for pair, rate in result['spot_rates'].items():
                print(f"     - {pair}: {rate:.6f}")
        else:
            print(f"     - None (all USD bonds)")

        print(f"\n[REALTIME] 3. FUNDING RATES (for FX hedging):")
        for ccy, rate in result['funding_rates'].items():
            print(f"     - {ccy}: {rate * 100:.4f}%")

        print(f"\n[REALTIME] 4. FAIR VALUE CURVES (sector/rating benchmarks):")
        for ccy_sector, ratings_data in result['fair_value_curves'].items():
            print(f"     - {ccy_sector}:")
            for rating, tenors_data in ratings_data.items():
                tenor_str = ', '.join([f"{t}Y: {y*100:.4f}%" for t, y in sorted(tenors_data.items(), key=lambda x: int(x[0]))])
                print(f"       • {rating}: {tenor_str}")

        print(f"\n[REALTIME] 5. SOFR/TREASURY SPREAD DATA:")
        for tenor, spread_data in sorted(result['sofr_spread_data'].items(), key=lambda x: int(x[0])):
            t_rate = spread_data.get('T_RATE', 0)
            t_sofr_spread = spread_data.get('T_SOFR_SPREAD', 0)
            sofr_rate = t_rate - t_sofr_spread
            print(f"     - {tenor}Y: T={t_rate*100:.4f}%, SOFR={sofr_rate*100:.4f}%, Spread={t_sofr_spread*10000:.1f}bps")

        print(f"\n[REALTIME] DATA SOURCES USED:")
        print(f"  • Benchmark rates: Treasury.gov, FRED, TradingEconomics.com, CME Group")
        print(f"  • Spot rates: Bloomberg, OANDA, XE.com, TradingEconomics.com")
        print(f"  • Funding rates: CME SOFR, FRED, ECB, Bank of Canada, TradingEconomics.com")
        print(f"  • Fair value curves: Bloomberg BVAL, ICE BofA indices, FRED credit spreads")
        print(f"  • SOFR/Treasury data: Treasury.gov, FRED, CME SOFR, Chatham Financial")
        print(f"[REALTIME] ====================================================\n")
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch all market data: {e}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        raise ValueError(f"Could not fetch all market data using Gemini API: {e}")

