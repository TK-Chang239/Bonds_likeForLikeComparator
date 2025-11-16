# =====================================================================================
# Analysis Service (Parts 4 & 5)
# -------------------------------------------------------------------------------------
# This service orchestrates the analysis. It ties the market data (Part 2)
# and the core math (Part 3) together to produce the final rich/cheap assessment.
# =====================================================================================

from services.market_data_service import get_market_context
from normalization_engine import (
    parse_spread,
    calculate_local_offered_yield,
    convert_float_to_fixed_equivalent,
    calculate_usd_hedged_yield,
)
from config import BPS_CONVERSION

# --- Decision Thresholds (Business Logic from Automation Proposal) ---
RICH_THRESHOLD = -0.0005 # -5 bps
CHEAP_THRESHOLD = 0.0005  # +5 bps
# --------------------------------------------------------------------

def determine_assessment(excess_yield):
    """Determines the Rich/Cheap/Fair status based on thresholds."""
    if excess_yield > CHEAP_THRESHOLD:
        return "Cheap (BUY)"
    elif excess_yield < RICH_THRESHOLD:
        return "Rich (PASS)"
    else:
        return "Fair (HOLD)"

def run_single_bond_analysis(bond, market_data_map=None):
    """
    Runs the full relative value analysis for a single bond.
    
    Args:
        bond: Bond dictionary with bond details
        market_data_map: Optional dictionary mapping bond names to their market data from review page
    """
    try:
        # Step 1: Parse Offered Spread (needed before fetching market context)
        # Handle "SOFR equivalent" spreads specially
        spread_string = bond.get('spread', '').strip()
        spread_lower = spread_string.lower()
        is_sofr_equivalent = 'sofr equivalent' in spread_lower or 'sofr-equivalent' in spread_lower
        
        if is_sofr_equivalent:
            # For SOFR equivalent bonds, use the benchmark code and spread from market data if available
            if market_data_map:
                bond_name = bond.get('bondName')
                if bond_name and bond_name in market_data_map:
                    review_market_data = market_data_map[bond_name]
                    # Get benchmark code and spread from review market data
                    benchmark_code = review_market_data.get('benchmark_code', 'T')
                    spread_decimal = review_market_data.get('spread_decimal', 0.0)
                    bond['benchmark'] = benchmark_code
                else:
                    # Default for SOFR equivalent
                    benchmark_code = 'T'
                    spread_decimal = 0.0
                    bond['benchmark'] = benchmark_code
            else:
                # Default for SOFR equivalent
                benchmark_code = 'T'
                spread_decimal = 0.0
                bond['benchmark'] = benchmark_code
        else:
            benchmark_code, spread_decimal = parse_spread(spread_string)
            bond['benchmark'] = benchmark_code # Inject benchmark code for later reference
        
        # Step 2: Get Market Context (Part 2)
        # Use pre-fetched market data from review page if available, otherwise fetch new data
        market_context = None
        bond_name = bond.get('bondName', 'Unknown')
        print(f"[DEBUG] ========== ANALYZING BOND: {bond_name} ==========")
        print(f"[DEBUG] Bond details: ccy={bond.get('ccy')}, tenor={bond.get('tenor')}, cpnType={bond.get('cpnType')}, spread={bond.get('spread')}")
        print(f"[DEBUG] market_data_map provided: {market_data_map is not None}")
        if market_data_map:
            print(f"[DEBUG] market_data_map keys: {list(market_data_map.keys())}")
            if bond_name in market_data_map:
                # Use market data from review page
                review_market_data = market_data_map[bond_name]
                print(f"[DEBUG] Found market data for '{bond_name}' in market_data_map")
                print(f"[DEBUG] review_market_data keys: {list(review_market_data.keys())}")
                
                # Debug: Check all values before creating market_context
                benchmark_rate = review_market_data.get("benchmark_rate")
                benchmark_code_val = review_market_data.get("benchmark_code", "T")
                funding_rates = review_market_data.get("funding_rates", {})
                sofr_spread_data = review_market_data.get("sofr_spread_data", {})
                fair_ytm_local = review_market_data.get("fair_ytm_local")
                ccy = review_market_data.get("ccy")
                tenor = review_market_data.get("tenor")
                sofr_equivalent_bond_yield = review_market_data.get("sofr_equivalent_bond_yield")
                
                print(f"[DEBUG] Extracted values from review_market_data:")
                print(f"  - benchmark_rate: {benchmark_rate} (type: {type(benchmark_rate)})")
                print(f"  - benchmark_code: {benchmark_code_val}")
                print(f"  - funding_rates: {funding_rates} (type: {type(funding_rates)})")
                print(f"  - sofr_spread_data: {sofr_spread_data} (type: {type(sofr_spread_data)})")
                print(f"  - fair_ytm_local: {fair_ytm_local} (type: {type(fair_ytm_local)})")
                print(f"  - ccy: {ccy}")
                print(f"  - tenor: {tenor}")
                print(f"  - sofr_equivalent_bond_yield: {sofr_equivalent_bond_yield} (type: {type(sofr_equivalent_bond_yield)})")
                
                # Convert review page market data format to market_context format
                market_context = {
                    "benchmark_rate": benchmark_rate,
                    "market_rates": {benchmark_code_val: benchmark_rate},
                    "funding_rates": funding_rates,
                    "sofr_spread_data": sofr_spread_data,
                    "fair_ytm_local": fair_ytm_local,
                    "ccy": ccy,
                    "tenor": tenor,
                    "data_source": "Review Page (User Reviewed)"
                }
                print(f"[ANALYSIS] Using market data from review page for bond '{bond_name}'")
            else:
                print(f"[DEBUG] Bond '{bond_name}' NOT found in market_data_map")
        
        if not market_context:
            # Fallback: fetch market context if not provided from review page
            print(f"[ANALYSIS] Fetching new market data for bond '{bond_name}'")
            market_context = get_market_context(bond)
            print(f"[DEBUG] Fetched market_context keys: {list(market_context.keys())}")

        # --- Calculate OFFERED VALUE (The Actual Price We Are Paying) ---
        # At this stage, all yields have already been converted to fixed equivalents on the review page
        # We just need to use the bond yield from the review page and perform hedging calculations
        
        print(f"[DEBUG] Starting offered yield calculation for '{bond_name}'")
        print(f"[DEBUG] Using market data from review page - all yields already converted to fixed equivalents")
        
        offered_yield_local = None
        
        # Use the bond yield from review page (already calculated and converted to fixed equivalent)
        if market_data_map and bond_name in market_data_map:
            review_market_data = market_data_map[bond_name]
            
            # Try to get the bond yield from review page in order of preference:
            # 1. sofr_equivalent_bond_yield (for SOFR equivalent bonds)
            # 2. fixed_equivalent_yield (for float bonds converted to fixed)
            # 3. Calculate from benchmark_rate + spread_decimal (for standard fixed bonds)
            
            bond_yield = review_market_data.get('sofr_equivalent_bond_yield')
            print(f"[DEBUG] sofr_equivalent_bond_yield from review_market_data: {bond_yield} (type: {type(bond_yield)})")
            
            if bond_yield is not None:
                offered_yield_local = float(bond_yield)
                print(f"[ANALYSIS] Using sofr_equivalent_bond_yield from review page: {offered_yield_local * 100:.2f}%")
            else:
                # Try fixed_equivalent_yield (for float bonds)
                fixed_equiv_yield = review_market_data.get('fixed_equivalent_yield')
                print(f"[DEBUG] fixed_equivalent_yield from review_market_data: {fixed_equiv_yield} (type: {type(fixed_equiv_yield)})")
                
                if fixed_equiv_yield is not None:
                    offered_yield_local = float(fixed_equiv_yield)
                    print(f"[ANALYSIS] Using fixed_equivalent_yield from review page: {offered_yield_local * 100:.2f}%")
                else:
                    # Fallback: calculate from benchmark_rate + spread_decimal
                    benchmark_rate = market_context.get("benchmark_rate")
                    spread_decimal = review_market_data.get("spread_decimal", 0.0)
                    print(f"[DEBUG] Calculating from benchmark_rate + spread_decimal")
                    print(f"[DEBUG] benchmark_rate: {benchmark_rate} (type: {type(benchmark_rate)})")
                    print(f"[DEBUG] spread_decimal: {spread_decimal} (type: {type(spread_decimal)})")
                    
                    if benchmark_rate is None:
                        raise ValueError(f"Benchmark rate is None for bond '{bond_name}' and no bond yield available from review page")
                    
                    offered_yield_local = calculate_local_offered_yield(
                        benchmark_rate, spread_decimal
                    )
                    print(f"[ANALYSIS] Calculated bond yield from benchmark + spread: {offered_yield_local * 100:.2f}%")
        else:
            # Fallback: calculate from market_context if review data not available
            benchmark_rate = market_context.get("benchmark_rate")
            if benchmark_rate is None:
                raise ValueError(f"Benchmark rate is None for bond '{bond_name}'")
            offered_yield_local = calculate_local_offered_yield(
                benchmark_rate, spread_decimal
            )
            print(f"[ANALYSIS] Calculated bond yield from market_context: {offered_yield_local * 100:.2f}%")

        # Validate that offered_yield_local is set and not None
        print(f"[DEBUG] Final offered_yield_local before hedging: {offered_yield_local} (type: {type(offered_yield_local)})")
        if offered_yield_local is None:
            raise ValueError(f"offered_yield_local is None for bond '{bond.get('bondName', 'Unknown')}'")
        
        # 2c. Hedge the Offered Yield to USD (same calculation for all bonds including SOFR equivalent)
        funding_rates = market_context.get("funding_rates", {})
        print(f"[DEBUG] funding_rates: {funding_rates} (type: {type(funding_rates)})")
        print(f"[DEBUG] bond['ccy']: {bond.get('ccy')}")
        if not funding_rates:
            raise ValueError(f"Funding rates are missing for bond '{bond.get('bondName', 'Unknown')}'")
        
        print(f"[DEBUG] Calling calculate_usd_hedged_yield with:")
        print(f"  - offered_yield_local: {offered_yield_local} (type: {type(offered_yield_local)})")
        print(f"  - ccy: {bond.get('ccy')}")
        print(f"  - funding_rates: {funding_rates}")
        try:
            offered_hedged_yield, fx_cost = calculate_usd_hedged_yield(
                offered_yield_local, bond['ccy'], funding_rates
            )
            print(f"[DEBUG] calculate_usd_hedged_yield returned:")
            print(f"  - offered_hedged_yield: {offered_hedged_yield} (type: {type(offered_hedged_yield)})")
            print(f"  - fx_cost: {fx_cost} (type: {type(fx_cost)})")
        except Exception as e:
            print(f"[DEBUG] ERROR in calculate_usd_hedged_yield: {e}")
            print(f"[DEBUG] Error type: {type(e)}")
            import traceback
            print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
            raise
        
        # --- Calculate FAIR VALUE (The Price We Should Be Paying) ---
        
        fair_ytm_local = market_context.get("fair_ytm_local")
        print(f"[DEBUG] fair_ytm_local: {fair_ytm_local} (type: {type(fair_ytm_local)})")
        if fair_ytm_local is None:
            raise ValueError(f"fair_ytm_local is None for bond '{bond.get('bondName', 'Unknown')}'")
        
        # 3. Hedge the Fair YTM to USD (same calculation for all bonds including SOFR equivalent)
        print(f"[DEBUG] Calling calculate_usd_hedged_yield for fair value with:")
        print(f"  - fair_ytm_local: {fair_ytm_local} (type: {type(fair_ytm_local)})")
        print(f"  - ccy: {bond.get('ccy')}")
        print(f"  - funding_rates: {funding_rates}")
        try:
            fair_hedged_yield, _ = calculate_usd_hedged_yield(
                fair_ytm_local, bond['ccy'], funding_rates
            )
            print(f"[DEBUG] calculate_usd_hedged_yield (fair) returned: {fair_hedged_yield} (type: {type(fair_hedged_yield)})")
        except Exception as e:
            print(f"[DEBUG] ERROR in calculate_usd_hedged_yield (fair): {e}")
            print(f"[DEBUG] Error type: {type(e)}")
            import traceback
            print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
            raise
        
        # --- Final Comparison (Part 5) ---
        
        print(f"[DEBUG] Calculating excess yield:")
        print(f"  - offered_hedged_yield: {offered_hedged_yield} (type: {type(offered_hedged_yield)})")
        print(f"  - fair_hedged_yield: {fair_hedged_yield} (type: {type(fair_hedged_yield)})")
        try:
            excess_yield = offered_hedged_yield - fair_hedged_yield
            print(f"[DEBUG] excess_yield: {excess_yield} (type: {type(excess_yield)})")
            excess_yield_bps = excess_yield * BPS_CONVERSION
            print(f"[DEBUG] excess_yield_bps: {excess_yield_bps}")
            assessment = determine_assessment(excess_yield)
            print(f"[DEBUG] assessment: {assessment}")
        except Exception as e:
            print(f"[DEBUG] ERROR in excess yield calculation: {e}")
            print(f"[DEBUG] Error type: {type(e)}")
            import traceback
            print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
            raise

        # Store detailed calculation steps for display
        calculation_steps = {
            "offered_yield_local": offered_yield_local,
            "offered_yield_local_bps": round(offered_yield_local * BPS_CONVERSION, 2),
            "fair_ytm_local": fair_ytm_local,
            "fair_ytm_local_bps": round(fair_ytm_local * BPS_CONVERSION, 2),
            "fx_cost": fx_cost,
            "fx_cost_bps": round(fx_cost * BPS_CONVERSION, 2),
            "benchmark_rate": market_context["benchmark_rate"],
            "spread_decimal": spread_decimal,
            "spread_bps": round(spread_decimal * BPS_CONVERSION, 0),
            "cpn_type": bond['cpnType'],
            "benchmark_code": benchmark_code,
        }
        
        # Add SOFR-specific calculations if applicable
        if benchmark_code == 'S' and bond['cpnType'].upper() == 'FIXED':
            from normalization_engine import calculate_sofr_swap_rate
            sofr_swap_rate = calculate_sofr_swap_rate(bond['tenor'], market_context["sofr_spread_data"])
            calculation_steps["sofr_swap_rate"] = sofr_swap_rate
            calculation_steps["sofr_swap_rate_bps"] = round(sofr_swap_rate * BPS_CONVERSION, 2)
        elif benchmark_code == 'T':
            # Only calculate SOFR equivalent if bond explicitly mentions "sofr equivalent"
            spread_str = bond.get('spread', '').lower()
            bond_name = bond.get('bondName', '').lower()
            if 'sofr equivalent' in spread_str or 'sofr equivalent' in bond_name:
                from normalization_engine import calculate_sofr_swap_rate, calculate_sofr_equivalent_spread
                sofr_swap_rate = calculate_sofr_swap_rate(bond['tenor'], market_context["sofr_spread_data"])
                tenor_key = str(int(bond['tenor']))
                t_sofr_spread = market_context["sofr_spread_data"][tenor_key]['T_SOFR_SPREAD']
                sofr_equiv_spread = calculate_sofr_equivalent_spread(
                    spread_decimal, 
                    market_context["benchmark_rate"], 
                    t_sofr_spread
                )
                calculation_steps["sofr_swap_rate"] = sofr_swap_rate
                calculation_steps["sofr_swap_rate_bps"] = round(sofr_swap_rate * BPS_CONVERSION, 2)
                calculation_steps["t_sofr_spread"] = t_sofr_spread
                calculation_steps["t_sofr_spread_bps"] = round(t_sofr_spread * BPS_CONVERSION, 0)
                calculation_steps["sofr_equivalent_spread"] = sofr_equiv_spread
                calculation_steps["sofr_equivalent_spread_bps"] = round(sofr_equiv_spread * BPS_CONVERSION, 1)
        
        return {
            "name": bond['bondName'],
            "ccy": bond['ccy'],
            "rating": bond['rating'],
            "sector": bond['sector'],
            "offered_spread": bond['spread'],
            "offered_hedged_yield_bps": round(offered_hedged_yield * BPS_CONVERSION, 2),
            "fair_hedged_yield_bps": round(fair_hedged_yield * BPS_CONVERSION, 2),
            "excess_yield_bps": round(excess_yield_bps, 2),
            "fx_hedge_cost_bps": round(fx_cost * BPS_CONVERSION, 2),
            "assessment": assessment,
            "calculation_steps": calculation_steps,
            "data_source": market_context.get("data_source", "Config"),
        }

    except ValueError as e:
        return {
            "name": bond.get('bondName', 'N/A'),
            "error": str(e),
            "assessment": "Error/N/A"
        }
    except Exception as e:
        return {
            "name": bond.get('bondName', 'N/A'),
            "error": f"Critical Error: {e}",
            "assessment": "Error/N/A"
        }


def run_full_analysis(ingested_bonds, market_data_map=None):
    """
    Processes a list of bonds and returns the final analysis results.
    
    Args:
        ingested_bonds: List of bond dictionaries
        market_data_map: Optional dictionary mapping bond names to their market data from review page
    """
    results = []
    for bond in ingested_bonds:
        results.append(run_single_bond_analysis(bond, market_data_map=market_data_map))
    return results