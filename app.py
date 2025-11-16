# =====================================================================================
# Bond Ingestion Server (Part 1 - Backend)
# -------------------------------------------------------------------------------------
# This is the main backend "traffic cop" application.
# Logic has been moved to the /services/ ingestion_service.py file.
#
# How to Run:
# 1. Ensure your folder structure is correct (see instructions).
# 2. Install dependencies:
#    pip install Flask google-generativeai pandas openpyxl
# 3. Run this file: python app.py
# 4. Open your browser to: http://localhost:8080
# =====================================================================================

import json
import re
from flask import Flask, request, jsonify, render_template

# Import the necessary service functions
from services.ingestion_service import call_gemini_parsing
from services.analysis_service import run_full_analysis # NEW IMPORT
import config  # Import config for SOFR_SPREADS fallback

# Initialize the Flask application
app = Flask(__name__)

# =====================================================================================
# FLASK BACKEND ROUTES (Controller Functions)
# =====================================================================================

@app.route('/')
def index():
    """
    Serves the main HTML page (the user interface) from the 'templates' folder.
    """
    return render_template('index.html')

@app.route('/submitBond', methods=['POST'])
def handle_form():
    """
    Handles the manual form submission from the user.
    """
    try:
        form_data = request.form
        spread_string = form_data.get("spread", "").strip()
        
        # Validate spread format
        if not spread_string:
            return jsonify({"error": "Spread field cannot be empty. Expected format: 'BENCHMARK+/-XXbps' (e.g., 'T+50bps', 'S+25bps')"}), 400
        
        if not re.match(r'^[A-Z]+[+-]\d+bps$', spread_string, re.IGNORECASE):
            return jsonify({"error": f"Invalid spread format: '{spread_string}'. Expected format: 'BENCHMARK+/-XXbps' (e.g., 'T+50bps', 'S+25bps', 'G+47bps')"}), 400
        
        bond = {
            "bondName": form_data.get("bondName", ""),
            "cpnType": form_data.get("cpnType", ""),
            "ccy": form_data.get("ccy", ""),
            "tenor": form_data.get("tenor", ""),
            "rating": form_data.get("rating", ""),
            "sector": form_data.get("sector", ""),
            "spread": spread_string
        }
        print(f"Received manual bond: {bond.get('bondName')} with spread: {spread_string}")
        # Return the single bond as a list with one item
        return jsonify([bond])
    except Exception as e:
        print(f"Error in /submitBond: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/uploadExcel', methods=['POST'])
def handle_upload():
    """
    Handles the file upload and delegates the heavy lifting (parsing)
    to the dedicated ingestion service.
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No 'file' part in the request"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file:
            file_bytes = file.read()
            print(f"[DEBUG] Received file: {file.filename}, size: {len(file_bytes)} bytes")

            # === CALL DEDICATED INGESTION SERVICE ===
            parsed_data = call_gemini_parsing(file_bytes, file.filename)
            # ========================================

            # Check if the response is an error dictionary
            if isinstance(parsed_data, dict) and "error" in parsed_data:
                error_msg = parsed_data.get("error", "Unknown error occurred")
                print(f"[ERROR] Ingestion service returned error: {error_msg}")
                return jsonify({"error": error_msg}), 500

            # New structure: {"bonds": [...], "benchmark_rates": {...}, "spot_rates": {...}, "funding_rates": {...}, "fair_value_curves": {...}, "sofr_spread_data": {...}}
            if isinstance(parsed_data, dict) and "bonds" in parsed_data:
                bonds = parsed_data.get("bonds", [])
                benchmark_rates = parsed_data.get("benchmark_rates", {})
                spot_rates = parsed_data.get("spot_rates", {})
                funding_rates = parsed_data.get("funding_rates", {})
                fair_value_curves = parsed_data.get("fair_value_curves", {})
                sofr_spread_data = parsed_data.get("sofr_spread_data", {})

                print(f"[INFO] Extracted {len(bonds)} bonds, {len(benchmark_rates)} benchmark rates, {len(spot_rates)} spot rates, {len(funding_rates)} funding rates, {len(fair_value_curves)} fair value curves, {len(sofr_spread_data)} SOFR spread tenors")

                return jsonify({
                    "bonds": bonds,
                    "benchmark_rates": benchmark_rates,
                    "spot_rates": spot_rates,
                    "funding_rates": funding_rates,
                    "fair_value_curves": fair_value_curves,
                    "sofr_spread_data": sofr_spread_data
                })
            else:
                error_msg = f"Unexpected response structure from ingestion service: {type(parsed_data)}"
                print(f"[ERROR] {error_msg}")
                return jsonify({"error": error_msg}), 500

        return jsonify({"error": "File upload failed for unknown reasons"}), 500
    except Exception as e:
        error_type = type(e).__name__
        error_msg = f"Unexpected error in /uploadExcel: {error_type} - {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        return jsonify({"error": error_msg}), 500

@app.route('/fetchMarketData', methods=['POST'])
def handle_fetch_market_data():
    """
    Fetches market data for all bonds so the user can review before analysis.
    This is Step 2 of the workflow.
    """
    try:
        from normalization_engine import parse_spread, calculate_sofr_equivalent_spread, calculate_sofr_swap_rate
        from services.market_data_service import get_market_context
        
        request_data = request.json
        # Handle both old format (list of bonds) and new format (dict with bonds and use_realtime)
        if isinstance(request_data, list):
            ingested_bonds = request_data
            use_realtime = True  # Default to real-time for backward compatibility
            excel_benchmark_rates = {}
            excel_spot_rates = {}
            excel_funding_rates = {}
            excel_fair_value_curves = {}
            excel_sofr_spread_data = {}
        else:
            ingested_bonds = request_data.get('bonds', [])
            use_realtime = request_data.get('use_realtime', True)
            excel_benchmark_rates = request_data.get('benchmark_rates', {})
            excel_spot_rates = request_data.get('spot_rates', {})
            excel_funding_rates = request_data.get('funding_rates', {})
            excel_fair_value_curves = request_data.get('fair_value_curves', {})
            excel_sofr_spread_data = request_data.get('sofr_spread_data', {})
        
        print(f"\n[MARKET DATA FETCH] Fetching market data for {len(ingested_bonds)} bond(s).")
        print(f"[MARKET DATA FETCH] User selected data source: {'Real-time (Online)' if use_realtime else 'Static (Excel/Config)'}")

        # Check if Excel provided market data
        has_excel_data = bool(excel_benchmark_rates or excel_spot_rates or excel_funding_rates or excel_fair_value_curves or excel_sofr_spread_data)

        if has_excel_data:
            print(f"[MARKET DATA FETCH] Excel file contains market data:")
            print(f"  - Benchmark rates: {list(excel_benchmark_rates.keys()) if excel_benchmark_rates else 'None'}")
            print(f"  - Spot rates: {list(excel_spot_rates.keys()) if excel_spot_rates else 'None'}")
            print(f"  - Funding rates: {list(excel_funding_rates.keys()) if excel_funding_rates else 'None'}")
            print(f"  - Fair value curves: {list(excel_fair_value_curves.keys()) if excel_fair_value_curves else 'None'}")
            print(f"  - SOFR spread data: {list(excel_sofr_spread_data.keys()) if excel_sofr_spread_data else 'None'}")

        # Route to appropriate handler based on USER'S data source choice
        if use_realtime:
            # User chose "Fetch from Online Sources" - route to online service
            # NOTE: Even if Excel contains market data, we IGNORE it and fetch online because user requested it
            print(f"[MARKET DATA FETCH] *** USER REQUESTED ONLINE DATA - IGNORING EXCEL DATA (if any) ***")
            print(f"[MARKET DATA FETCH] Routing to online market data service...")
            try:
                from services.online_market_data_service import fetch_market_data_for_bonds_online
                result = fetch_market_data_for_bonds_online(ingested_bonds)
                return jsonify(result)
            except Exception as e:
                print(f"[ERROR] Failed to fetch market data from online sources: {e}")
                import traceback
                print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
                return jsonify({"error": f"Failed to fetch market data from online sources: {str(e)}"}), 500
        else:
            # User chose "Use Static Data from Config" - use Excel data if available, otherwise config
            if has_excel_data:
                print(f"[MARKET DATA FETCH] Using static data from Excel file")
            else:
                print(f"[MARKET DATA FETCH] Using static data from config.py")

        # =====================================================================================
        # STATIC CONFIG PROCESSING PATH (for Excel data or config.py)
        # =====================================================================================
        
        # Extract unique tenors from all bonds to filter SOFR spread data
        unique_tenors = set()
        for bond in ingested_bonds:
            try:
                tenor = str(int(bond.get('tenor', 0)))
                if tenor and tenor != '0':
                    unique_tenors.add(tenor)
            except (ValueError, TypeError):
                pass
        print(f"[MARKET DATA FETCH] Unique tenors found in bonds: {sorted(unique_tenors)}")

        # Prioritize Excel SOFR spread data, then real-time, then config
        all_tenors_sofr_data = {}
        if excel_sofr_spread_data and len(excel_sofr_spread_data) > 0:
            # Use Excel SOFR spread data (already filtered to unique tenors during ingestion)
            print(f"[MARKET DATA FETCH] Using SOFR spread data from Excel file")
            all_tenors_sofr_data = excel_sofr_spread_data
        elif use_realtime:
            # Fetch real-time SOFR data
            try:
                from services.realtime_data_service import fetch_sofr_data
                for tenor in unique_tenors:
                    try:
                        print(f"[MARKET DATA FETCH] Fetching SOFR data for {tenor}Y tenor...")
                        all_tenors_sofr_data[tenor] = fetch_sofr_data(tenor)
                    except Exception as sofr_err:
                        print(f"[WARNING] Could not fetch SOFR data for {tenor}Y: {sofr_err}")
                        # Use config fallback for this tenor if available
                        if tenor in config.SOFR_SPREADS:
                            all_tenors_sofr_data[tenor] = config.SOFR_SPREADS[tenor]
            except ImportError:
                print(f"[INFO] Real-time data service not available, will use config values")

        # If no Excel or real-time SOFR data was fetched, use config for the unique tenors
        if not all_tenors_sofr_data:
            for tenor in unique_tenors:
                if tenor in config.SOFR_SPREADS:
                    all_tenors_sofr_data[tenor] = config.SOFR_SPREADS[tenor]
                else:
                    print(f"[WARNING] No SOFR data available for {tenor}Y in config")

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

                # Fetch market context with user's data source preference
                # Pass the pre-fetched SOFR data for all tenors and Excel market data if available
                market_context = get_market_context(
                    bond,
                    use_realtime=use_realtime,
                    sofr_data_override=all_tenors_sofr_data if all_tenors_sofr_data else None,
                    excel_benchmark_rates=excel_benchmark_rates if has_excel_data else None,
                    excel_funding_rates=excel_funding_rates if has_excel_data else None,
                    excel_fair_value_curves=excel_fair_value_curves if has_excel_data else None
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

                            # For Float bonds with "SOFR equivalent", spread_decimal is 0
                            # The SOFR equivalent spread (z) = x + T_SOFR_SPREAD = 0 + T_SOFR_SPREAD = T_SOFR_SPREAD
                            # Calculate SOFR equivalent spread: z = x + T_SOFR_SPREAD
                            sofr_equivalent_spread = calculate_sofr_equivalent_spread(
                                spread_decimal,  # This is 0 for Float bonds with "SOFR equivalent"
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
                        "spot_rates": excel_spot_rates if has_excel_data else {},
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
        print(f"[MARKET DATA FETCH COMPLETE] Fetched data for {len(market_data_results)} bond(s).")
        print(f"[MARKET DATA FETCH COMPLETE] SOFR spread data available for tenors: {sorted(all_tenors_sofr_data.keys())}")

        # Create data sources info for static config/Excel path
        if has_excel_data:
            data_sources_info = {
                "source_type": "excel",
                "timestamp": "From uploaded Excel file",
                "sources": {
                    "benchmark_rates": "Excel file",
                    "spot_rates": "Excel file",
                    "funding_rates": "Excel file",
                    "fair_value_curves": "Excel file",
                    "sofr_treasury_data": "Excel file"
                }
            }
        else:
            data_sources_info = {
                "source_type": "config",
                "timestamp": "Static configuration",
                "sources": {
                    "benchmark_rates": "config.py (Static)",
                    "spot_rates": "config.py (Static)",
                    "funding_rates": "config.py (Static)",
                    "fair_value_curves": "config.py (Static/Proprietary - Bloomberg BVAL / ICE BofA)",
                    "sofr_treasury_data": "config.py (Static)"
                }
            }

        return jsonify({
            "market_data": market_data_results,
            "data_sources": data_sources_info
        })

    except Exception as e:
        print(f"Error in /fetchMarketData: {e}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route('/analyze', methods=['POST'])
def handle_analysis():
    """
    This route handles the "Analyze" button click and triggers the full RV pipeline.
    (Parts 2-5 are executed here via the run_full_analysis service)
    Uses market data from the review page instead of fetching new data.
    """
    try:
        request_data = request.json
        
        # Handle both old format (just bonds list) and new format (bonds + market_data_map)
        if isinstance(request_data, list):
            ingested_bonds = request_data
            market_data_map = {}
            print(f"\n[ANALYSIS TRIGGERED] Analyzing {len(ingested_bonds)} bond(s) (no market data provided, will fetch).")
        else:
            ingested_bonds = request_data.get('bonds', [])
            market_data_map = request_data.get('market_data_map', {})
            print(f"\n[ANALYSIS TRIGGERED] Analyzing {len(ingested_bonds)} bond(s) using market data from review page.")
            print(f"[ANALYSIS] Market data available for {len(market_data_map)} bond(s).")
        
        # === CALL DEDICATED ANALYSIS SERVICE (Executes Parts 2, 3, 4, 5) ===
        # Pass market_data_map so analysis service can use pre-fetched data
        analysis_results = run_full_analysis(ingested_bonds, market_data_map=market_data_map)
        # ==================================================================
        
        print(f"[ANALYSIS COMPLETE] Sending results back to frontend.")
        return jsonify({"results": analysis_results})

    except Exception as e:
        print(f"Error in /analyze: {e}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =====================================================================================
# MAIN EXECUTION
# =====================================================================================

if __name__ == '__main__':
    print("==========================================================")
    print("  Bond Ingestion Server (Part 1) IS STARTING...")
    print("  Flask debug mode is ON.")
    print("  Access the UI at: http://localhost:8080")
    print("==========================================================")
    app.run(debug=True, port=8080)