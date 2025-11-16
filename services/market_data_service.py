# =====================================================================================
# Market Data Service (Part 2)
# -------------------------------------------------------------------------------------
# This service is responsible for fetching all real-time market context
# required for the analysis based on the bond's specifications.
# Uses Gemini API to fetch real-time data from online sources.
# =====================================================================================

import config
import time
import random

# Try to import real-time data service, fallback to config if not available
try:
    from services.realtime_data_service import fetch_all_realtime_data
    USE_REALTIME_DATA = True
except ImportError:
    USE_REALTIME_DATA = False
    print("[WARNING] Real-time data service not available, using config values")

def get_market_context(bond, use_realtime=True, sofr_data_override=None, excel_benchmark_rates=None, excel_funding_rates=None, excel_fair_value_curves=None):
    """
    Fetches all necessary real-time and structural data based on the bond.

    Args:
        bond: Bond dictionary with ccy, tenor, rating, sector, benchmark
        use_realtime: Whether to fetch real-time data (default: True)
        sofr_data_override: Pre-fetched SOFR data for all tenors (dict) - if provided, use this instead of fetching
        excel_benchmark_rates: Benchmark rates from Excel file (dict) - if provided, use these instead of fetching
        excel_funding_rates: Funding rates from Excel file (dict) - if provided, use these instead of fetching
        excel_fair_value_curves: Fair value curves from Excel file (dict) - if provided, use these instead of config

    Returns:
        dict: Market context with all rates and data
    """

    ccy = bond['ccy']
    tenor = str(int(bond['tenor']))
    rating = bond['rating']
    sector = bond['sector']

    # Check if Excel provided market data
    use_excel_data = bool(excel_benchmark_rates or excel_funding_rates or excel_fair_value_curves)

    # Use SOFR data override if provided (already fetched for all tenors)
    if sofr_data_override is not None:
        sofr_spread_data = sofr_data_override
    else:
        sofr_spread_data = None

    # Determine data source priority: Excel > Real-time > Config
    if use_excel_data:
        # Use Excel data (only log once at the beginning)
        # Only use Excel data if it's not empty, otherwise fall back to config
        if excel_benchmark_rates and len(excel_benchmark_rates) > 0:
            market_rates = excel_benchmark_rates
        else:
            market_rates = config.MARKET_RATES

        if excel_funding_rates and len(excel_funding_rates) > 0:
            funding_rates = excel_funding_rates
        else:
            funding_rates = config.FUNDING_RATES

        if sofr_spread_data is None:
            sofr_spread_data = config.SOFR_SPREADS
        data_source = 'Excel file'
    elif use_realtime and USE_REALTIME_DATA:
        # Use real-time data
        try:
            realtime_data = fetch_all_realtime_data(ccy, tenor)
            market_rates = {bond.get('benchmark', 'T'): realtime_data['benchmark_rate']}
            funding_rates = realtime_data['funding_rates']
            # Use override SOFR data if provided, otherwise use fetched data
            if sofr_spread_data is None:
                sofr_spread_data = realtime_data['sofr_spread_data']
                # If SOFR data is empty from real-time, use config fallback to ensure it's always available
                if not sofr_spread_data or len(sofr_spread_data) == 0:
                    print(f"[INFO] SOFR data empty from real-time, using config fallback...")
                    sofr_spread_data = config.SOFR_SPREADS
            data_source = realtime_data.get('source', 'Real-time')
        except Exception as e:
            print(f"[WARNING] Real-time fetch failed: {e}. Using config values...")
            market_rates = config.MARKET_RATES
            funding_rates = config.FUNDING_RATES
            if sofr_spread_data is None:
                sofr_spread_data = config.SOFR_SPREADS
            data_source = 'Config (fallback)'
    else:
        # Use config values
        market_rates = config.MARKET_RATES
        funding_rates = config.FUNDING_RATES
        if sofr_spread_data is None:
            sofr_spread_data = config.SOFR_SPREADS
        data_source = 'Config (static)'
    
    # Simulate API/Network latency
    time.sleep(random.uniform(0.1, 0.5))

    # 1. Fetch Benchmark Rate
    # For SOFR-based spreads (S+XXbps), we need to calculate the SOFR swap rate
    benchmark_code = bond.get('benchmark', '').upper()
    
    if benchmark_code == 'S':
        # For SOFR spreads, calculate the SOFR swap rate from Treasury and spread
        tenor_key = str(int(bond['tenor']))
        if tenor_key not in sofr_spread_data:
            raise ValueError(f"SOFR spread data not available for tenor: {tenor_key} year(s)")
        
        t_rate = sofr_spread_data[tenor_key]['T_RATE']
        t_sofr_spread = sofr_spread_data[tenor_key]['T_SOFR_SPREAD']
        # SOFR swap rate = T - (T - SOFR spread)
        benchmark_rate = t_rate - t_sofr_spread
    else:
        # For other benchmarks (T, G, MS, etc.), get from market_rates
        benchmark_rate = market_rates.get(benchmark_code)
        if benchmark_rate is None:
            raise ValueError(f"Benchmark rate not found for: {benchmark_code}. Available benchmarks: {list(market_rates.keys())}")
        
    # 2. Fetch Fair Value YTM (Excel 'Curves Information' sheet or config)
    curve_key = f"{ccy}_{sector}".upper()

    # Use Excel fair value curves if available, otherwise use config
    if excel_fair_value_curves and curve_key in excel_fair_value_curves:
        print(f"[INFO] Using Fair Value YTM from Excel for {curve_key}")
        fair_curve_set = excel_fair_value_curves[curve_key]
        # Excel format: {rating: {tenor: ytm}}
        # We need to extract the YTM for this specific rating and tenor
        if rating in fair_curve_set:
            tenor_ytm_dict = fair_curve_set[rating]
            if tenor in tenor_ytm_dict:
                fair_ytm_local = tenor_ytm_dict[tenor]
            else:
                raise ValueError(f"Fair YTM not found for tenor {tenor} in {curve_key}/{rating}. Available tenors: {list(tenor_ytm_dict.keys())}")
        else:
            raise ValueError(f"Fair YTM not found for rating {rating} in {curve_key}. Available ratings: {list(fair_curve_set.keys())}")
    else:
        # Use config values
        fair_curve_set = config.FAIR_CURVES.get(curve_key)
        if not fair_curve_set:
            raise ValueError(f"Fair curve not found for sector/ccy: {curve_key}")

        fair_ytm_local = fair_curve_set.get(rating)
        if not fair_ytm_local:
            raise ValueError(f"Fair YTM not found for rating {rating} in {curve_key}")
        
    # 3. Compile Market Data Context
    market_context = {
        # General Rates
        "benchmark_rate": benchmark_rate,
        "market_rates": market_rates,  # May be real-time or from config
        "funding_rates": funding_rates,  # May be real-time or from config
        "sofr_spread_data": sofr_spread_data,  # May be real-time or from config
        
        # Fair Value (The comparison point) - Always from config (proprietary)
        "fair_ytm_local": fair_ytm_local,
        
        # Used for FX hedging
        "ccy": ccy,
        "tenor": tenor,
        
        # Data source information
        "data_source": data_source,
    }
    
    return market_context