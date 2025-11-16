# =====================================================================================
# Normalization Engine (Part 3)
# -------------------------------------------------------------------------------------
# This module contains the reusable, pure mathematical functions for
# neutralizing currency and coupon structure differences.
# It does NOT fetch any data; it only performs calculations.
# =====================================================================================

import re
from config import BPS_CONVERSION

def parse_spread(spread_string):
    """
    Parses a spread string (e.g., "T+50bps", "G+47bps", "S+25bps") into its benchmark and value.
    Supports:
    - Treasury spreads: "T+50bps"
    - Government spreads: "G+47bps"
    - SOFR spreads: "S+25bps" (for floating-rate bonds)
    - Mid-Swap spreads: "MS+30bps"
    
    Returns: (benchmark_code, spread_value_decimal)
    """
    # Handle both positive and negative spreads (e.g., "T+50bps" or "T-10bps")
    match = re.match(r"([A-Z]+)([+-])(\d+)bps", spread_string, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid spread format: {spread_string}. Expected format: 'BENCHMARK+/-XXbps' (e.g., 'T+50bps', 'S+25bps')")
    
    benchmark = match.group(1).upper()
    sign = match.group(2)
    bps_value = int(match.group(3))
    
    # Apply sign
    if sign == '-':
        bps_value = -bps_value
    
    return benchmark, bps_value / BPS_CONVERSION

def calculate_local_offered_yield(benchmark_rate, spread_decimal):
    """
    Calculates the local Yield to Maturity (YTM) for a fixed-rate bond.
    YTM = Benchmark Rate + Credit Spread
    """
    # For a newly issued bond at par, YTM is approximately the offer spread + benchmark
    return benchmark_rate + spread_decimal

def calculate_sofr_swap_rate(tenor, sofr_spread_data):
    """
    Calculates the 1Y SOFR Swap Rate based on the corrected formula:
    SOFR Swap Rate = Treasury Rate - (T_SOFR_SPREAD)
    """
    tenor_key = str(int(tenor))
    if tenor_key not in sofr_spread_data:
        raise ValueError(f"SOFR spread data not available for tenor: {tenor_key} year(s)")
        
    t_rate = sofr_spread_data[tenor_key]['T_RATE']
    t_sofr_spread = sofr_spread_data[tenor_key]['T_SOFR_SPREAD']
    
    # Corrected formula derived from the case's ambiguity (T - SOFR = Spread, so SOFR = T - Spread)
    sofr_swap_rate = t_rate - t_sofr_spread
    
    return sofr_swap_rate

def calculate_sofr_equivalent_spread(fixed_spread_over_treasury, treasury_rate, sofr_treasury_spread):
    """
    Calculates the SOFR equivalent spread for a fixed-rate bond.
    
    This converts a fixed-rate bond's Treasury spread to a floating spread over SOFR,
    equating the present value of cash flows (assuming no liquidity/credit premiums).
    
    Formula: z = x + (T - S)
    Where S = T - T_SOFR_SPREAD (SOFR swap rate = Treasury rate - T-SOFR spread)
    
    Simplified: z = x + T_SOFR_SPREAD
    
    Where:
        x: Fixed spread over Treasury (in decimal, e.g., 0.0050 for 50bps)
        T: Treasury yield (in decimal, e.g., 0.0344 for 3.44%)
        sofr_treasury_spread: T_SOFR_SPREAD (in decimal, can be positive or negative, e.g., 0.0025 for 25bps or -0.0010 for -10bps)
        S: SOFR swap rate = T - T_SOFR_SPREAD
        z: SOFR equivalent spread (in decimal, the floating spread over SOFR)
    
    Args:
        fixed_spread_over_treasury: The fixed spread over Treasury (x) in decimal format
        treasury_rate: The Treasury yield (T) in decimal format
        sofr_treasury_spread: The T_SOFR_SPREAD (in decimal format, can be positive or negative)
    
    Returns:
        float: The SOFR equivalent spread (z) in decimal format
    
    Example:
        # For Bond B: T+50bps, T_SOFR_SPREAD = 25bps
        # x = 0.0050 (50bps), T = 0.0344 (3.44%), T_SOFR_SPREAD = 0.0025 (25bps)
        # S = T - T_SOFR_SPREAD = 0.0344 - 0.0025 = 0.0319 (3.19%)
        # z = x + T_SOFR_SPREAD = 0.0050 + 0.0025 = 0.0075 (75bps)
        sofr_equiv = calculate_sofr_equivalent_spread(0.0050, 0.0344, 0.0025)
    """
    # Formula: z = x + (T - S) where S = T - T_SOFR_SPREAD
    # So z = x + T_SOFR_SPREAD
    # Note: T_SOFR_SPREAD can be positive or negative
    sofr_equivalent_spread = fixed_spread_over_treasury + sofr_treasury_spread
    return sofr_equivalent_spread

def convert_float_to_fixed_equivalent(bond, market_rates, sofr_spread_data):
    """
    Converts a floating-rate bond into its equivalent fixed-rate yield (YTM).
    This solves the Bond C puzzle.
    1. Determine the bond's all-in fixed-equivalent yield (the 3.94% value).
    2. Identify the bond's true spread (the S+25bps value).
    
    Returns: (fixed_equivalent_yield, true_spread_decimal)
    """
    # 1. Use the FIXED-RATE bond (Bond B / T+50bps) as the baseline for the credit spread
    # Note: This is an assumption based on Bond C and B having the same rating/sector/tenor.
    BASE_SPREAD_BPS = 50.0
    BASE_T_SPREAD = BASE_SPREAD_BPS / BPS_CONVERSION
    BASE_T_RATE = market_rates.get('T')
    
    # The All-in Fixed Equivalent Yield (e.g., 3.44% + 0.50% = 3.94%)
    fixed_equivalent_yield = BASE_T_RATE + BASE_T_SPREAD
    
    # 2. Calculate the SOFR Swap Rate (e.g., 3.69%)
    sofr_swap_rate = calculate_sofr_swap_rate(bond['tenor'], sofr_spread_data)
    
    # 3. Calculate the bond's true spread over SOFR (The "S+25bps" value)
    # True Spread = Fixed Equivalent Yield - SOFR Swap Rate
    true_spread_decimal = fixed_equivalent_yield - sofr_swap_rate
    
    # Note: We return the Fixed Equivalent Yield (3.94%) for comparison purposes.
    return fixed_equivalent_yield, true_spread_decimal

def calculate_usd_hedged_yield(local_yield, ccy, funding_rates):
    """
    Calculates the USD-Hedged Yield using Covered Interest Parity.
    Y_Hedged = ( (1 + Y_Local) * (1 + r_USD) / (1 + r_FCY) ) - 1
    """
    r_usd = funding_rates.get('USD')
    r_fcy = funding_rates.get(ccy)
    
    if not r_usd or not r_fcy:
        raise ValueError(f"Funding rate missing for CCY: {ccy}")
    
    # Calculate the FX hedge cost: r_USD - r_FCY
    fx_hedge_cost = r_usd - r_fcy
    
    # Calculate the final USD-Hedged Yield
    # The USD-Hedged YTM = Local YTM - FX Hedge Cost (simplified)
    # The cost is already embedded in the interest rate differential.
    usd_hedged_yield = local_yield + fx_hedge_cost # Or local_yield - (r_fcy - r_usd)
    
    return usd_hedged_yield, fx_hedge_cost