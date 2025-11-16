# =====================================================================================
# Online Market Data Service
# -------------------------------------------------------------------------------------
# This service handles fetching market data from online sources using Gemini API.
# It returns data in the same structure as the static config version, so all
# downstream processing (calculations, display, analysis) works identically.
# =====================================================================================

import config
import re
from normalization_engine import parse_spread, calculate_sofr_equivalent_spread, calculate_sofr_swap_rate
from services.market_data_service import get_market_context


def fetch_market_data_for_bonds_online(ingested_bonds):
    """
    Fetches market data for all bonds from online sources using Gemini API.
    This function replicates the logic from handle_fetch_market_data but specifically
    for online data sources. It returns the same data structure as the static config version.
    
    Args:
        ingested_bonds: List of bond dictionaries
        
    Returns:
        dict: Market data results in the same format as static config version
            {
                "market_data": [
                    {
                        "bond": {...},
                        "market_data": {...} or "error": "..."
                    },
                    ...
                ]
            }
    """
    print(f"\n[ONLINE MARKET DATA] Fetching market data for {len(ingested_bonds)} bond(s) from online sources.")
    
    # Fetch all market data using Gemini API in Excel format
    print(f"[ONLINE MARKET DATA] Fetching all market data from online sources using Gemini API...")
    try:
        from services.realtime_data_service import fetch_all_market_data_excel_format
        fetched_market_data = fetch_all_market_data_excel_format(ingested_bonds)
        
        # Extract fetched data
        excel_benchmark_rates = fetched_market_data.get("benchmark_rates", {})
        excel_spot_rates = fetched_market_data.get("spot_rates", {})
        excel_funding_rates = fetched_market_data.get("funding_rates", {})
        excel_fair_value_curves = fetched_market_data.get("fair_value_curves", {})
        excel_sofr_spread_data = fetched_market_data.get("sofr_spread_data", {})
        
        print(f"[ONLINE MARKET DATA] Successfully fetched market data from online sources")
        print(f"[ONLINE MARKET DATA] Fetched benchmark rates: {list(excel_benchmark_rates.keys())}")
        print(f"[ONLINE MARKET DATA] Fetched spot rates: {list(excel_spot_rates.keys())}")
        print(f"[ONLINE MARKET DATA] Fetched funding rates: {list(excel_funding_rates.keys())}")
        print(f"[ONLINE MARKET DATA] Fetched fair value curves: {list(excel_fair_value_curves.keys())}")
        print(f"[ONLINE MARKET DATA] Fetched SOFR spread data tenors: {list(excel_sofr_spread_data.keys())}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch market data from online sources: {e}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        raise ValueError(f"Could not fetch market data from online sources: {e}")

    # Extract unique tenors from all bonds to filter SOFR spread data
    unique_tenors = set()
    for bond in ingested_bonds:
        try:
            tenor = str(int(bond.get('tenor', 0)))
            if tenor and tenor != '0':
                unique_tenors.add(tenor)
        except (ValueError, TypeError):
            pass
    print(f"[ONLINE MARKET DATA] Unique tenors found in bonds: {sorted(unique_tenors)}")

    # Use fetched SOFR spread data, with config fallback if needed
    all_tenors_sofr_data = {}
    if excel_sofr_spread_data and len(excel_sofr_spread_data) > 0:
        # Use fetched SOFR spread data
        print(f"[ONLINE MARKET DATA] Using SOFR spread data from online sources")
        all_tenors_sofr_data = excel_sofr_spread_data
    else:
        # Fallback to config for missing tenors
        print(f"[ONLINE MARKET DATA] No SOFR spread data from online sources, using config fallback")
        for tenor in unique_tenors:
            if tenor in config.SOFR_SPREADS:
                all_tenors_sofr_data[tenor] = config.SOFR_SPREADS[tenor]
            else:
                print(f"[WARNING] No SOFR data available for {tenor}Y in config")

    # Process each bond - same logic as static config version
    market_data_results = []
    for bond in ingested_bonds:
        try:
            # Validate and parse spread to get benchmark
            spread_string = bond.get('spread', '').strip()
            if not spread_string:
                raise ValueError(f"Bond '{bond.get('bondName', 'Unknown')}' has an empty spread field")
            
            # Special handling for "SOFR equivalent" spreads (typically for Float bonds)
            # Check multiple variations to catch different formats from Gemini extraction
            spread_lower = spread_string.lower().strip()
            bond_name_lower = bond.get('bondName', '').lower()
            cpn_type = bond.get('cpnType', '').upper()
            
            # More robust detection: check for "sofr equivalent" in various forms
            # Also check if it's a Float bond with S+0bps (which Gemini might convert "SOFR equivalent" to)
            is_sofr_equivalent = (
                'sofr equivalent' in spread_lower or
                'sofr-equivalent' in spread_lower or
                spread_lower == 'sofr equivalent' or
                spread_lower == 'sofr-equivalent' or
                'sofr equivalent' in bond_name_lower or
                # Also check if Float bond with S+0bps (Gemini might convert "SOFR equivalent" to this)
                (cpn_type == 'FLOAT' and spread_lower in ['s+0bps', 's+0 bps', 'sofr+0bps', 'sofr+0 bps'])
            )
            
            print(f"[DEBUG] Checking SOFR equivalent for '{bond.get('bondName', 'Unknown')}': spread='{spread_string}', spread_lower='{spread_lower}', cpnType='{cpn_type}', is_sofr_equivalent={is_sofr_equivalent}")
            
            # For SOFR equivalent bonds, we need to determine the benchmark
            # Float bonds with "SOFR equivalent" should use the spread from their equivalent fixed-rate bond
            if is_sofr_equivalent:
                print(f"[DEBUG] Bond '{bond.get('bondName', 'Unknown')}' has 'SOFR equivalent' spread: '{spread_string}'")
                # For Float bonds with SOFR equivalent, find the equivalent fixed-rate bond
                # and use its Treasury spread (x) for the calculation
                if bond.get('cpnType', '').upper() == 'FLOAT':
                    benchmark_code = 'T'
                    # Find the equivalent fixed-rate bond (same ccy, tenor, rating, sector)
                    equivalent_fixed_bond = None
                    for other_bond in ingested_bonds:
                        if (other_bond.get('bondName') != bond.get('bondName') and
                            other_bond.get('cpnType', '').upper() == 'FIXED' and
                            other_bond.get('ccy') == bond.get('ccy') and
                            str(other_bond.get('tenor')) == str(bond.get('tenor')) and
                            other_bond.get('rating') == bond.get('rating') and
                            other_bond.get('sector') == bond.get('sector')):
                            equivalent_fixed_bond = other_bond
                            break
                    
                    if equivalent_fixed_bond:
                        # Parse the equivalent fixed bond's spread to get the Treasury spread (x)
                        try:
                            equiv_spread_str = equivalent_fixed_bond.get('spread', '').strip()
                            equiv_benchmark, equiv_spread_decimal = parse_spread(equiv_spread_str)
                            if equiv_benchmark == 'T':
                                spread_decimal = equiv_spread_decimal
                                print(f"[DEBUG] Float bond with SOFR equivalent: found equivalent fixed bond '{equivalent_fixed_bond.get('bondName')}' with T+{equiv_spread_decimal*10000:.0f}bps, using x={spread_decimal}")
                            else:
                                # If equivalent bond uses different benchmark, default to 0
                                spread_decimal = 0.0
                                print(f"[DEBUG] Float bond with SOFR equivalent: equivalent fixed bond '{equivalent_fixed_bond.get('bondName')}' uses {equiv_benchmark} benchmark, defaulting to x=0")
                        except Exception as e:
                            spread_decimal = 0.0
                            print(f"[DEBUG] Float bond with SOFR equivalent: could not parse equivalent bond spread, defaulting to x=0. Error: {e}")
                    else:
                        spread_decimal = 0.0
                        print(f"[DEBUG] Float bond with SOFR equivalent: no equivalent fixed bond found (same ccy={bond.get('ccy')}, tenor={bond.get('tenor')}, rating={bond.get('rating')}, sector={bond.get('sector')}), defaulting to x=0")
                else:
                    # For Fixed bonds, try to extract the actual spread if present
                    # Otherwise default to T+0bps
                    benchmark_code = 'T'
                    spread_decimal = 0.0
                    print(f"[DEBUG] Fixed bond with SOFR equivalent: treating as T+0bps for benchmark determination")
            else:
                # Check if spread is in valid format before parsing
                if not re.match(r'^[A-Z]+[+-]\d+bps$', spread_string, re.IGNORECASE):
                    raise ValueError(f"Bond '{bond.get('bondName', 'Unknown')}' has invalid spread format: '{spread_string}'. Expected format: 'BENCHMARK+/-XXbps' (e.g., 'T+50bps', 'S+25bps') or 'SOFR equivalent'")
                
                benchmark_code, spread_decimal = parse_spread(spread_string)
                
                # Additional check: If Float bond with S+XXbps, check if it matches a Fixed bond
                # (Gemini might convert "SOFR equivalent" to "S+XXbps" to match the format requirement)
                # If there's a matching Fixed bond with Treasury spread, treat as SOFR equivalent
                if cpn_type == 'FLOAT' and benchmark_code == 'S':
                    # Check if there's a matching Fixed bond (same ccy, tenor, rating, sector)
                    equivalent_fixed_bond = None
                    for other_bond in ingested_bonds:
                        if (other_bond.get('bondName') != bond.get('bondName') and
                            other_bond.get('cpnType', '').upper() == 'FIXED' and
                            other_bond.get('ccy') == bond.get('ccy') and
                            str(other_bond.get('tenor')) == str(bond.get('tenor')) and
                            other_bond.get('rating') == bond.get('rating') and
                            other_bond.get('sector') == bond.get('sector')):
                            equivalent_fixed_bond = other_bond
                            break
                    
                    if equivalent_fixed_bond:
                        # Check if the equivalent fixed bond has a Treasury spread
                        try:
                            equiv_spread_str = equivalent_fixed_bond.get('spread', '').strip()
                            equiv_benchmark, equiv_spread_decimal = parse_spread(equiv_spread_str)
                            if equiv_benchmark == 'T':
                                # This Float bond is likely SOFR equivalent to the Fixed bond
                                print(f"[DEBUG] Float bond with S+{spread_decimal*10000:.0f}bps detected - found matching Fixed bond '{equivalent_fixed_bond.get('bondName')}' with T+{equiv_spread_decimal*10000:.0f}bps, treating as SOFR equivalent")
                                is_sofr_equivalent = True
                                benchmark_code = 'T'  # Change to T for SOFR equivalent calculation
                                spread_decimal = equiv_spread_decimal  # Use the Treasury spread (x) from the equivalent fixed bond, not the Float bond's spread
                        except Exception as e:
                            print(f"[DEBUG] Could not parse equivalent fixed bond spread: {e}")
                
                # Legacy check: If Float bond with S+0bps, treat as SOFR equivalent
                # (Gemini might convert "SOFR equivalent" to "S+0bps" to match the format requirement)
                if cpn_type == 'FLOAT' and benchmark_code == 'S' and spread_decimal == 0.0 and not is_sofr_equivalent:
                    print(f"[DEBUG] Float bond with S+0bps detected - treating as SOFR equivalent")
                    is_sofr_equivalent = True
                    benchmark_code = 'T'  # Change to T for SOFR equivalent calculation
                    
                    # Find the equivalent fixed-rate bond and use its Treasury spread (x)
                    equivalent_fixed_bond = None
                    for other_bond in ingested_bonds:
                        if (other_bond.get('bondName') != bond.get('bondName') and
                            other_bond.get('cpnType', '').upper() == 'FIXED' and
                            other_bond.get('ccy') == bond.get('ccy') and
                            str(other_bond.get('tenor')) == str(bond.get('tenor')) and
                            other_bond.get('rating') == bond.get('rating') and
                            other_bond.get('sector') == bond.get('sector')):
                            equivalent_fixed_bond = other_bond
                            break
                    
                    if equivalent_fixed_bond:
                        # Parse the equivalent fixed bond's spread to get the Treasury spread (x)
                        try:
                            equiv_spread_str = equivalent_fixed_bond.get('spread', '').strip()
                            equiv_benchmark, equiv_spread_decimal = parse_spread(equiv_spread_str)
                            if equiv_benchmark == 'T':
                                spread_decimal = equiv_spread_decimal
                                print(f"[DEBUG] Float bond with S+0bps: found equivalent fixed bond '{equivalent_fixed_bond.get('bondName')}' with T+{equiv_spread_decimal*10000:.0f}bps, using x={spread_decimal}")
                            else:
                                spread_decimal = 0.0
                                print(f"[DEBUG] Float bond with S+0bps: equivalent fixed bond '{equivalent_fixed_bond.get('bondName')}' uses {equiv_benchmark} benchmark, defaulting to x=0")
                        except Exception as e:
                            spread_decimal = 0.0
                            print(f"[DEBUG] Float bond with S+0bps: could not parse equivalent bond spread, defaulting to x=0. Error: {e}")
                    else:
                        spread_decimal = 0.0
                        print(f"[DEBUG] Float bond with S+0bps: no equivalent fixed bond found, defaulting to x=0")
            
            bond['benchmark'] = benchmark_code
            print(f"[DEBUG] Bond '{bond.get('bondName', 'Unknown')}': benchmark={benchmark_code}, spread_decimal={spread_decimal}, is_sofr_equivalent={is_sofr_equivalent}")

            # Fetch market context using the fetched online data
            # Pass the fetched data as Excel-like data (same structure)
            market_context = get_market_context(
                bond,
                use_realtime=False,  # Set to False because we're using pre-fetched data
                sofr_data_override=all_tenors_sofr_data if all_tenors_sofr_data else None,
                excel_benchmark_rates=excel_benchmark_rates,
                excel_funding_rates=excel_funding_rates,
                excel_fair_value_curves=excel_fair_value_curves
            )
            
            # Calculate SOFR equivalent spread or fixed-equivalent yield
            sofr_equivalent_spread = None
            sofr_swap_rate = None
            fixed_equivalent_yield = None
            sofr_equivalent_bond_yield = None
            calculation_details = {}

            try:
                tenor_key = str(int(bond['tenor']))
                sofr_swap_rate = calculate_sofr_swap_rate(bond['tenor'], market_context["sofr_spread_data"])

                if benchmark_code == 'T':
                    # Only calculate SOFR equivalent spread if bond explicitly mentions "sofr equivalent"
                    spread_str = bond.get('spread', '').lower()
                    bond_name = bond.get('bondName', '').lower()
                    if is_sofr_equivalent or 'sofr equivalent' in spread_str or 'sofr equivalent' in bond_name:
                        # For Treasury-based spreads with SOFR equivalent: calculate SOFR equivalent spread and bond yield
                        treasury_rate = market_context["benchmark_rate"]
                        # Get T-SOFR spread from the data (tenor_key already defined above)
                        t_rate = market_context["sofr_spread_data"][tenor_key]['T_RATE']
                        t_sofr_spread = market_context["sofr_spread_data"][tenor_key]['T_SOFR_SPREAD']

                        # Calculate SOFR equivalent spread: z = x + T_SOFR_SPREAD
                        sofr_equivalent_spread = calculate_sofr_equivalent_spread(
                            spread_decimal,
                            treasury_rate,
                            t_sofr_spread
                        )

                        # Calculate bond yield: Bond Yield = SOFR Swap Rate + z
                        sofr_equivalent_bond_yield = sofr_swap_rate + sofr_equivalent_spread
                        
                        print(f"[DEBUG] SOFR Equivalent Calculation - spread_decimal={spread_decimal}, sofr_equivalent_spread={sofr_equivalent_spread}, sofr_equivalent_bond_yield={sofr_equivalent_bond_yield}")

                        # Store calculation details for display (ensure all values are JSON-serializable)
                        calculation_details = {
                            'treasury_spread_bps': float(round(spread_decimal * 10000, 0)),
                            't_sofr_spread_bps': float(round(t_sofr_spread * 10000, 0)),
                            'sofr_equivalent_spread_bps': float(round(sofr_equivalent_spread * 10000, 0)),
                            'treasury_rate': float(treasury_rate),
                            't_rate': float(t_rate),
                            'sofr_swap_rate': float(sofr_swap_rate),
                            'bond_yield': float(sofr_equivalent_bond_yield)
                        }
                        
                        # Debug logging
                        print(f"[DEBUG] SOFR Equivalent Calculation for {bond.get('bondName', 'Unknown')}:")
                        print(f"  - Treasury Spread (x): {calculation_details['treasury_spread_bps']:.0f} bps")
                        print(f"  - T-SOFR Spread: {calculation_details['t_sofr_spread_bps']:.0f} bps")
                        print(f"  - SOFR Equivalent Spread (z): {calculation_details['sofr_equivalent_spread_bps']:.0f} bps")
                        print(f"  - T Rate: {t_rate * 100:.2f}%")
                        print(f"  - SOFR Swap Rate (S): {sofr_swap_rate * 100:.2f}%")
                        print(f"  - Bond Yield: {sofr_equivalent_bond_yield * 100:.2f}%")
                        print(f"  - Calculation Details Dict: {calculation_details}")
                        print(f"  - Calculation Details Type: {type(calculation_details)}")
                        print(f"  - Calculation Details Keys: {list(calculation_details.keys())}")
                elif benchmark_code == 'S':
                    # Check if this is a SOFR equivalent bond (Float bond with S+0bps that was converted to T)
                    # If is_sofr_equivalent is True, it means this was already handled above
                    if is_sofr_equivalent:
                        # This should have been handled in the benchmark_code == 'T' block above
                        # But if we reach here, it means the bond was detected as SOFR equivalent
                        # but benchmark_code is still 'S'. This shouldn't happen, but handle it anyway.
                        print(f"[WARNING] Bond '{bond.get('bondName')}' is SOFR equivalent but benchmark_code is 'S'. This may indicate a logic error.")
                    else:
                        # For SOFR-based floating bonds: calculate fixed-equivalent yield
                        # Fixed-equivalent yield = S + z (where z is the SOFR spread)
                        fixed_equivalent_yield = sofr_swap_rate + spread_decimal
            except Exception as sofr_err:
                print(f"[WARNING] Could not calculate SOFR metrics for {bond.get('bondName')}: {sofr_err}")
            
            # Format for display
            # For SOFR equivalent bonds, use SOFR swap rate as the benchmark rate for display
            display_benchmark_rate = market_context["benchmark_rate"]
            display_benchmark_code = benchmark_code
            if is_sofr_equivalent and sofr_swap_rate is not None:
                display_benchmark_rate = sofr_swap_rate
                display_benchmark_code = 'S'  # Show as SOFR for display purposes
            
            market_data_result = {
                "bond": bond,
                "market_data": {
                    "benchmark_rate": display_benchmark_rate,  # SOFR swap rate for SOFR equivalent bonds
                    "benchmark_code": display_benchmark_code,  # 'S' for SOFR equivalent bonds
                    "spread_decimal": spread_decimal,
                    "fair_ytm_local": market_context["fair_ytm_local"],
                    "spot_rates": excel_spot_rates,
                    "funding_rates": market_context["funding_rates"],
                    "sofr_spread_data": market_context["sofr_spread_data"],
                    "sofr_swap_rate": sofr_swap_rate,
                    "sofr_equivalent_spread": sofr_equivalent_spread,
                    "sofr_equivalent_bond_yield": sofr_equivalent_bond_yield,
                    "calculation_details": calculation_details,
                    "fixed_equivalent_yield": fixed_equivalent_yield,
                    "is_sofr_equivalent": is_sofr_equivalent,  # Flag to indicate SOFR equivalent bond
                    "ccy": market_context["ccy"],
                    "tenor": market_context["tenor"],
                }
            }
            
            # Debug logging for SOFR equivalent bonds
            if benchmark_code == 'T':
                spread_str = bond.get('spread', '').lower()
                bond_name = bond.get('bondName', '').lower()
                if is_sofr_equivalent or 'sofr equivalent' in spread_str or 'sofr equivalent' in bond_name:
                    print(f"[DEBUG] Market data result for SOFR equivalent bond '{bond.get('bondName')}':")
                    print(f"  - sofr_equivalent_bond_yield: {sofr_equivalent_bond_yield}")
                    print(f"  - calculation_details keys: {list(calculation_details.keys()) if calculation_details else 'None'}")
                    print(f"  - calculation_details: {calculation_details}")
            
            market_data_results.append(market_data_result)
        except Exception as e:
            market_data_results.append({
                "bond": bond,
                "error": str(e)
            })
    
    # The SOFR spread data has already been filtered to unique tenors via all_tenors_sofr_data
    # All bonds now share the same filtered SOFR spread data
    print(f"[ONLINE MARKET DATA COMPLETE] Fetched data for {len(market_data_results)} bond(s).")
    print(f"[ONLINE MARKET DATA COMPLETE] SOFR spread data available for tenors: {sorted(all_tenors_sofr_data.keys())}")

    # Return detailed data sources information for display in UI
    data_sources_info = {
        "source_type": "online",
        "timestamp": "November 16, 2025",
        "sources": {
            "benchmark_rates": "Treasury.gov, FRED, TradingEconomics.com, CME Group",
            "spot_rates": "Bloomberg, OANDA, XE.com, TradingEconomics.com",
            "funding_rates": "CME SOFR, FRED, ECB, Bank of Canada, TradingEconomics.com",
            "fair_value_curves": "Bloomberg BVAL, ICE BofA indices, FRED credit spreads",
            "sofr_treasury_data": "Treasury.gov, FRED, CME SOFR, Chatham Financial"
        }
    }

    return {
        "market_data": market_data_results,
        "data_sources": data_sources_info
    }

