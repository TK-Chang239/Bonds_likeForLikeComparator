# =====================================================================================
# Bond Ingestion Service (Part 1 Logic)
# -------------------------------------------------------------------------------------
# This file contains all the logic for parsing bond data,
# including reading files and calling the Gemini API.
# =====================================================================================

import json
import io
import pandas as pd
import google.generativeai as genai

# Import constants from our new config file
import config

# =====================================================================================
# GEMINI API CONFIGURATION
# =====================================================================================

# Configure the API from the config file
genai.configure(api_key=config.API_KEY)
model = genai.GenerativeModel(config.MODEL_NAME)

# =====================================================================================
# AI PARSING FUNCTION
# =====================================================================================

def call_gemini_parsing(file_bytes, filename):
    """
    Calls the Gemini API to parse the uploaded file bytes.
    1. Reads the file (CSV/Excel) into a DataFrame.
    2. Converts the DataFrame to a text string.
    3. Sends the text to Gemini with a prompt to extract bond data as JSON.
    4. Parses and returns the JSON response (a list of bond objects).
    """
    print(f"Parsing '{filename}' with Gemini...")
    
    # 1. Read file bytes into a pandas DataFrame (ALL SHEETS for Excel files)
    try:
        file_extension = filename.lower().split('.')[-1] if '.' in filename else 'unknown'
        print(f"[DEBUG] File extension detected: {file_extension}")
        print(f"[DEBUG] File size: {len(file_bytes)} bytes")

        if filename.lower().endswith('.csv'):
            print("[DEBUG] Attempting to read CSV file...")
            df = pd.read_csv(io.BytesIO(file_bytes))
            print(f"[DEBUG] CSV read successfully. Shape: {df.shape}")
            file_text = df.to_string()
        elif filename.lower().endswith(('.xls', '.xlsx')):
            print("[DEBUG] Attempting to read Excel file (ALL SHEETS)...")
            # Read ALL sheets from Excel file
            try:
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine='openpyxl')
                sheet_names = excel_file.sheet_names
                print(f"[DEBUG] Excel file contains {len(sheet_names)} sheets: {sheet_names}")

                # Read all sheets and combine their text
                all_sheets_text = []
                for sheet_name in sheet_names:
                    try:
                        df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name)
                        if not df_sheet.empty:
                            sheet_text = f"\n{'='*80}\nSHEET: {sheet_name}\n{'='*80}\n{df_sheet.to_string()}\n"
                            all_sheets_text.append(sheet_text)
                            print(f"[DEBUG] ✓ Read sheet '{sheet_name}' successfully. Shape: {df_sheet.shape}")
                        else:
                            print(f"[DEBUG] Sheet '{sheet_name}' is empty, skipping...")
                    except Exception as sheet_err:
                        print(f"[WARNING] Could not read sheet '{sheet_name}': {sheet_err}")

                if not all_sheets_text:
                    error_msg = f"File '{filename}' contains no readable data in any sheet."
                    print(f"[ERROR] {error_msg}")
                    return {"error": error_msg}

                # Combine all sheets into one text string
                file_text = "\n".join(all_sheets_text)
                print(f"[DEBUG] Combined text from {len(all_sheets_text)} sheets. Total length: {len(file_text)} characters")

            except Exception as xls_error:
                print(f"[DEBUG] openpyxl failed: {xls_error}. Trying default engine...")
                df = pd.read_excel(io.BytesIO(file_bytes))
                print(f"[DEBUG] Excel read successfully with default engine. Shape: {df.shape}")
                file_text = df.to_string()
        else:
            error_msg = f"Unsupported file type: '{file_extension}'. Supported formats: CSV (.csv), Excel (.xls, .xlsx)"
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        # 2. Check if combined text is empty
        if not file_text or len(file_text.strip()) == 0:
            error_msg = f"File '{filename}' is empty or contains no data."
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        # Increase character limit to ensure we capture all market data tables from ALL sheets
        if len(file_text) > 20000: # Allow more content to capture all sheets
            file_text = file_text[:20000] + "\n... (file truncated)"

        print(f"--- Extracted Text from {filename} (ALL SHEETS) ---")
        print(file_text)
        print("----------------------------------------")

        # Debug: Check if Assumptions section is present
        if 'assumption' in file_text.lower() or 'fx' in file_text.lower() or 'rate' in file_text.lower():
            print("[DEBUG] ✓ Found keywords 'Assumptions', 'FX', or 'Rate' in extracted text")
        else:
            print("[WARNING] Keywords 'Assumptions', 'FX', or 'Rate' NOT found in extracted text!")

        # Debug: Check if Curves Information sheet is present
        if 'curve' in file_text.lower() and 'yield to maturity' in file_text.lower():
            print("[DEBUG] ✓ Found 'Curves Information' sheet with YTM tables")
            # Find and print a sample of the Curves section
            lines = file_text.split('\n')
            for i, line in enumerate(lines):
                if 'yield to maturity' in line.lower():
                    print(f"[DEBUG] Curves section found at line {i}:")
                    print('\n'.join(lines[max(0, i-1):min(len(lines), i+10)]))
                    break
        else:
            print("[WARNING] 'Curves Information' sheet or YTM tables NOT found in extracted text!")

    except pd.errors.EmptyDataError as e:
        error_msg = f"File '{filename}' is empty or contains no readable data. Details: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return {"error": error_msg}
    except pd.errors.ParserError as e:
        error_msg = f"Failed to parse file '{filename}'. The file may be corrupted or in an unexpected format. Details: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return {"error": error_msg}
    except ImportError as e:
        error_msg = f"Missing required library. Please ensure 'openpyxl' is installed: pip install openpyxl. Details: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return {"error": error_msg}
    except Exception as e:
        error_type = type(e).__name__
        error_msg = f"Error reading file '{filename}': {error_type} - {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        return {"error": error_msg}

    # 3. Send to Gemini for extraction
    # This prompt instructs the AI to act as a parser and return *only* JSON.
    prompt = f"""
    You are an expert financial data extraction API.
    A user has uploaded a file with the following text content from MULTIPLE SHEETS:

    --- FILE CONTENT START (ALL SHEETS) ---
    {file_text}
    --- FILE CONTENT END ---

    CRITICAL INSTRUCTIONS:
    - This file may contain MULTIPLE SHEETS (indicated by "SHEET: <name>" markers)
    - You MUST search ALL sheets to find the required data
    - If you cannot find specific data in ANY sheet, return an EMPTY object/array for that section
    - DO NOT make up or infer data that is not explicitly present in the file
    - DO NOT add currencies, rates, or bonds that are not in the file

    Extract the following information from this file and return as a JSON object:

    1. BONDS: Extract ALL bonds mentioned with these attributes: "bondName", "cpnType", "ccy", "tenor", "rating", "sector", "spread".
       - "bondName" should be the name of the bond (e.g., "Bond A", "Bond B", "Bond C").
       - "cpnType" must be "Fixed" or "Float".
       - "ccy" must be the 3-letter currency code (e.g., "USD", "CAD", "EUR").
       - "tenor" must be a number (in years).
       - "rating" must be the credit rating (e.g., "AA", "BBB").
       - "sector" must be the industry sector (e.g., "Tech", "Energy").
       - "spread" must be in format "BENCHMARK+/-XXbps" (e.g., "T+50bps", "S+0bps", "G+47bps").
         Valid benchmarks: T (Treasury), S (SOFR/Overnight SOFR), G (Government), MS (Mid-Swap).

    2. MARKET REFERENCE RATES: Look for a section titled "Market Reference Rate" with a table showing Abbreviation, Definition, and Rate.
       You MUST extract ALL FOUR benchmark rates (T, S, MS, G). The table will show:

       Row 1: Abbreviation=T,  Definition=Treasury,        Rate=3.44% (or similar)
       Row 2: Abbreviation=S,  Definition=Overnight SOFR,  Rate=3.25% (or similar)
       Row 3: Abbreviation=MS, Definition=Mid-Swap,        Rate=2.08% (or similar)
       Row 4: Abbreviation=G,  Definition=Government,      Rate=2.41% (or similar)

       Convert percentages to decimals (e.g., 3.44% = 0.0344).
       Return ALL FOUR rates as: {{"T": 0.0344, "S": 0.0325, "MS": 0.0208, "G": 0.0241}}

       CRITICAL: You must extract all 4 rates (T, S, MS, G). Do not stop after finding T. Read the entire table.

    3. FX/CURRENCY ASSUMPTIONS: Look for a section titled "Assumptions", "FX Information", or similar that contains currency exchange rates and funding rates.
       This section may appear on ANY sheet/page (Sheet1, FX Information, SOFR & Treasury Information, etc.).

       The table typically looks like this (VERTICAL FORMAT):

       | Description     | Value  |
       |-----------------|--------|
       | EUR/USD Spot    | 1.1400 |
       | USD/CAD Spot    | 1.4100 |
       | USD Rate        | 3.00%  |
       | EUR Rate        | 1.50%  |
       | CAD Rate        | 1.87%  |

       You need to extract TWO types of currency data:

       A) SPOT EXCHANGE RATES: Currency pair exchange rates (e.g., EUR/USD Spot, USD/CAD Spot)
          - Look for rows with pattern: "CCY1/CCY2 Spot" in the FIRST column
          - Extract the numeric value from the SECOND column
          - Do NOT convert these values - keep as-is
          - Examples:
            Row: "EUR/USD Spot | 1.1400"  → Extract as "EUR/USD": 1.1400
            Row: "USD/CAD Spot | 1.4100"  → Extract as "USD/CAD": 1.4100
          - IGNORE any rows with just "Spot" - only extract rows with currency pairs

       B) FUNDING RATES: Currency-specific interest rates (e.g., USD Rate, EUR Rate, CAD Rate)
          - Look for rows with pattern: "CCY Rate" in the FIRST column (where CCY is USD, EUR, CAD, GBP, etc.)
          - Extract the percentage value from the SECOND column
          - MUST convert percentages to decimals: 3.00% → 0.0300, 1.50% → 0.0150, 1.87% → 0.0187
          - Examples:
            Row: "USD Rate | 3.00%"  → Extract as "USD": 0.0300
            Row: "EUR Rate | 1.50%"  → Extract as "EUR": 0.0150
            Row: "CAD Rate | 1.87%"  → Extract as "CAD": 0.0187
          - ONLY extract currencies that appear in the table - do NOT add GBP, JPY, etc. if they are not present

       CRITICAL EXTRACTION RULES:
       - Read the ENTIRE Assumptions table - do not stop after first few rows
       - Extract ALL currency rates shown (USD, EUR, CAD, and any others present)
       - Do NOT extract currencies that are not in the table
       - The table may have 10-20 rows - read all of them
       - Search ALL sheets/pages in the file for this data
       - Look for keywords: "Assumptions", "FX", "Currency", "Exchange Rate", "Spot", "Rate"

       Return two separate objects:
       - "spot_rates": {{"EUR/USD": 1.1400, "USD/CAD": 1.4100}}
       - "funding_rates": {{"USD": 0.0300, "EUR": 0.0150, "CAD": 0.0187}}

    4. FAIR VALUE YTM (CURVES INFORMATION): Look for a sheet named "Curves Information" or similar with tables showing Fair Value Yield to Maturity.

       CRITICAL: This data is ESSENTIAL. You MUST extract it if present.

       Each table has:
       - A HEADER: "CCY SECTOR Sector: Yield to Maturity" (e.g., "CAD Tech Sector: Yield to Maturity", "USD Energy Sector: Yield to Maturity")
       - A ROW with column headers: "Tenor" (or "Tenor (Yr.)"), then rating columns: "AAA", "AA", "A", "BBB"
       - DATA ROWS: First column is tenor (1, 2, 3), followed by percentage values (3.89%, 3.95%, 4.02%, 4.10%)

       EXACT FORMAT YOU WILL SEE:

       CAD Tech Sector: Yield to Maturity
                Rating
       Tenor    AAA      AA       A       BBB
       1        3.89%    3.95%    4.02%   4.10%
       2        3.92%    3.98%    4.05%   4.13%
       3        3.96%    4.02%    4.09%   4.19%

       USD Energy Sector: Yield to Maturity
                Rating
       Tenor    AAA      AA       A       BBB
       1        3.82%    3.90%    3.98%   4.03%
       2        3.85%    3.93%    4.01%   4.06%
       3        3.89%    3.97%    4.05%   4.10%

       EUR Financials Sector: Yield to Maturity
                Rating
       Tenor    AAA      AA       A       BBB
       1        3.91%    3.98%    4.06%   4.13%
       2        3.94%    4.01%    4.09%   4.16%
       3        3.98%    4.05%    4.14%   4.21%

       EXTRACTION INSTRUCTIONS:
       1. Find the "Curves Information" sheet (or sheet with "Curve" in the name)
       2. Identify each table by its header (e.g., "CAD Tech Sector: Yield to Maturity")
       3. Extract currency (CAD, USD, EUR) and sector (Tech, Energy, Financials) from the header
       4. Create key in format "CCY_SECTOR" in UPPERCASE: "CAD Tech" → "CAD_TECH", "USD Energy" → "USD_ENERGY", "EUR Financials" → "EUR_FINANCIALS"
       5. For EACH rating column (AAA, AA, A, BBB):
          - Read ALL tenor rows (1, 2, 3, etc.)
          - Convert percentage values to decimals: 3.89% → 0.0389, 4.10% → 0.0410
          - Store as: rating → {{tenor_as_string: decimal_value}}

       CRITICAL CONVERSION:
       - 3.89% = 0.0389
       - 3.95% = 0.0395
       - 4.02% = 0.0402
       - 4.10% = 0.0410
       - Values are already in decimal format (0.0389) - do NOT convert again!

    5. SOFR/TREASURY SPREAD DATA: Look for a table showing "Tenor (Yr.)", "Treasury", and "SOFR/Treasury Spread" columns.

       CRITICAL: This data is ESSENTIAL for SOFR equivalent calculations.

       The table looks like:

       | Tenor (Yr.) | Treasury | SOFR/Treasury Spread |
       |-------------|----------|----------------------|
       | 1           | 3.44%    | -0.25%              |
       | 2           | 3.56%    | -0.26%              |
       | 3           | 3.75%    | -0.30%              |

       EXTRACTION INSTRUCTIONS:
       - Find the table with columns: "Tenor (Yr.)", "Treasury", "SOFR/Treasury Spread"
       - For EACH tenor row, extract:
         * Tenor as string (e.g., "1", "2", "3")
         * Treasury rate as decimal (3.44% → 0.0344)
         * SOFR/Treasury spread as decimal (-0.25% → -0.0025, -0.26% → -0.0026)
       - CRITICAL: Preserve the NEGATIVE sign for SOFR/Treasury spread! (-0.25% is -0.0025, NOT 0.0025)

       OUTPUT FORMAT:
       "sofr_spread_data": {{
           "1": {{
               "T_RATE": 0.0344,
               "T_SOFR_SPREAD": -0.0025
           }},
           "2": {{
               "T_RATE": 0.0356,
               "T_SOFR_SPREAD": -0.0026
           }},
           "3": {{
               "T_RATE": 0.0375,
               "T_SOFR_SPREAD": -0.0030
           }}
       }}

       If no SOFR spread table exists, return an empty object: {{}}

    OUTPUT FORMAT (EXACT STRUCTURE):
       "fair_value_curves": {{
           "CAD_TECH": {{
               "AAA": {{"1": 0.0389, "2": 0.0392, "3": 0.0396}},
               "AA": {{"1": 0.0395, "2": 0.0398, "3": 0.0402}},
               "A": {{"1": 0.0402, "2": 0.0405, "3": 0.0409}},
               "BBB": {{"1": 0.0410, "2": 0.0413, "3": 0.0419}}
           }},
           "USD_ENERGY": {{
               "AAA": {{"1": 0.0382, "2": 0.0385, "3": 0.0389}},
               "AA": {{"1": 0.0390, "2": 0.0393, "3": 0.0397}},
               "A": {{"1": 0.0398, "2": 0.0401, "3": 0.0405}},
               "BBB": {{"1": 0.0403, "2": 0.0406, "3": 0.0410}}
           }},
           "EUR_FINANCIALS": {{
               "AAA": {{"1": 0.0391, "2": 0.0394, "3": 0.0398}},
               "AA": {{"1": 0.0398, "2": 0.0401, "3": 0.0405}},
               "A": {{"1": 0.0406, "2": 0.0409, "3": 0.0414}},
               "BBB": {{"1": 0.0413, "2": 0.0416, "3": 0.0421}}
           }}
       }}

       If no Curves Information sheet exists, return an empty object: {{}}

    Return a JSON object with this structure:
    {{
        "bonds": [list of bond objects],
        "benchmark_rates": {{abbreviation: rate as decimal}},
        "spot_rates": {{currency_pair: exchange_rate}},
        "funding_rates": {{currency: rate as decimal}},
        "fair_value_curves": {{currency_sector_key: {{rating: {{tenor: ytm}}}}}},
        "sofr_spread_data": {{tenor_string: {{"T_RATE": decimal, "T_SOFR_SPREAD": decimal}}}}
    }}

    If any section is not found in the file, return an EMPTY object or array for that section.
    DO NOT make up data. Return ONLY the JSON, no other text.

    FINAL REMINDER:
    - Search ALL SHEETS
    - Extract ALL data from ALL sections
    - Do not skip any rates or currencies
    - Do not invent data
    - PRESERVE NEGATIVE SIGNS in SOFR/Treasury spreads!
    """

    try:
        # 4. Call the API and parse the JSON response
        print("[DEBUG] Sending text to Gemini for JSON extraction...")
        print(f"[DEBUG] Prompt length: {len(prompt)} characters")
        
        if not config.API_KEY or config.API_KEY.strip() == "":
            error_msg = "Gemini API key is not configured. Please set API_KEY in config.py"
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}
        
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
        )
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # The response text should be a clean JSON string
        json_response = response.text
        print(f"[DEBUG] Gemini JSON Response (first 500 chars): {json_response[:500]}")

        # Debug: Show full funding_rates, spot_rates, and fair_value_curves from raw JSON
        try:
            temp_parse = json.loads(json_response)
            if isinstance(temp_parse, dict):
                print(f"[DEBUG] Raw JSON funding_rates: {temp_parse.get('funding_rates', {})}")
                print(f"[DEBUG] Raw JSON spot_rates: {temp_parse.get('spot_rates', {})}")
                print(f"[DEBUG] Raw JSON fair_value_curves keys: {list(temp_parse.get('fair_value_curves', {}).keys())}")
        except:
            pass

        # Parse the JSON string into a Python object
        try:
            parsed_data = json.loads(json_response)
        except json.JSONDecodeError as json_err:
            error_msg = f"Failed to parse Gemini response as JSON. Response: {json_response[:200]}... Error: {str(json_err)}"
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        # Check if the response has the expected structure
        if not isinstance(parsed_data, dict):
            error_msg = f"Gemini did not return a dict. Got type: {type(parsed_data)}, value: {parsed_data}"
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        # Extract bonds, benchmark rates, spot rates, funding rates, fair value curves, and SOFR spread data
        parsed_bonds = parsed_data.get('bonds', [])
        benchmark_rates = parsed_data.get('benchmark_rates', {})
        spot_rates = parsed_data.get('spot_rates', {})
        funding_rates = parsed_data.get('funding_rates', {})
        fair_value_curves = parsed_data.get('fair_value_curves', {})
        sofr_spread_data_excel = parsed_data.get('sofr_spread_data', {})

        if not isinstance(parsed_bonds, list):
            error_msg = f"'bonds' field is not a list. Got type: {type(parsed_bonds)}, value: {parsed_bonds}"
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        if len(parsed_bonds) == 0:
            error_msg = "Gemini returned an empty bonds list. No bonds were extracted from the file."
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        print(f"[INFO] Extracted {len(benchmark_rates)} benchmark rates: {benchmark_rates}")
        print(f"[INFO] Extracted {len(spot_rates)} spot rates: {spot_rates}")
        print(f"[INFO] Extracted {len(funding_rates)} funding rates: {funding_rates}")
        print(f"[INFO] Extracted {len(fair_value_curves)} fair value curves: {list(fair_value_curves.keys())}")
        print(f"[INFO] Extracted {len(sofr_spread_data_excel)} SOFR spread tenors: {list(sofr_spread_data_excel.keys())}")

        # Debug: Print detailed extraction info
        print(f"[DEBUG] Benchmark rates detail:")
        for abbr, rate in benchmark_rates.items():
            print(f"  {abbr}: {rate} ({rate * 100:.2f}%)")

        print(f"[DEBUG] Spot rates detail:")
        for pair, rate in spot_rates.items():
            print(f"  {pair}: {rate}")

        print(f"[DEBUG] Funding rates detail:")
        for ccy, rate in funding_rates.items():
            print(f"  {ccy}: {rate} ({rate * 100:.2f}%)")

        print(f"[DEBUG] Fair Value Curves detail:")
        for curve_key, ratings_data in fair_value_curves.items():
            print(f"  {curve_key}: {len(ratings_data)} ratings ({list(ratings_data.keys())})")

        print(f"[DEBUG] SOFR Spread Data detail:")
        for tenor, data in sofr_spread_data_excel.items():
            t_rate = data.get('T_RATE', 0)
            t_sofr_spread = data.get('T_SOFR_SPREAD', 0)
            print(f"  {tenor}Y: T_RATE={t_rate} ({t_rate*100:.2f}%), T_SOFR_SPREAD={t_sofr_spread} ({t_sofr_spread*100:.2f}%)")

        # Validate that we have all expected benchmark rates
        expected_benchmarks = {'T', 'S', 'MS', 'G'}
        missing_benchmarks = expected_benchmarks - set(benchmark_rates.keys())
        if missing_benchmarks and len(benchmark_rates) > 0:
            print(f"[WARNING] Missing benchmark rates: {missing_benchmarks}. This may cause errors for bonds using these benchmarks.")

        # Validate that we have FX data
        if len(spot_rates) == 0:
            print(f"[WARNING] No spot exchange rates extracted.")
        if len(funding_rates) == 0:
            print(f"[WARNING] No funding rates extracted. This may cause issues with currency hedging calculations.")
        
        # Validate spread format for each bond
        import re
        validated_bonds = []
        for bond in parsed_bonds:
            spread = bond.get('spread', '').strip()
            if not spread:
                print(f"[WARNING] Bond '{bond.get('bondName', 'Unknown')}' has empty spread. Skipping.")
                continue
            
            # Validate spread format
            if not re.match(r'^[A-Z]+[+-]\d+bps$', spread, re.IGNORECASE):
                print(f"[WARNING] Bond '{bond.get('bondName', 'Unknown')}' has invalid spread format: '{spread}'. Expected format: 'BENCHMARK+/-XXbps'. Attempting to fix...")
                # Try to extract valid spread from the string
                spread_match = re.search(r'([A-Z]+)[+-]?(\d+)\s*bps?', spread, re.IGNORECASE)
                if spread_match:
                    benchmark = spread_match.group(1).upper()
                    bps = spread_match.group(2)
                    bond['spread'] = f"{benchmark}+{bps}bps"
                    print(f"[INFO] Fixed spread to: {bond['spread']}")
                else:
                    print(f"[ERROR] Could not fix spread for bond '{bond.get('bondName', 'Unknown')}'. Skipping bond.")
                    continue
            
            validated_bonds.append(bond)
        
        if len(validated_bonds) == 0:
            error_msg = "No valid bonds found after validation. Please check the spread format in your file."
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        print(f"[SUCCESS] Gemini extracted {len(validated_bonds)} valid bond(s) from {len(parsed_bonds)} total.")

        # Return bonds along with market data
        return {
            "bonds": validated_bonds,
            "benchmark_rates": benchmark_rates,
            "spot_rates": spot_rates,
            "funding_rates": funding_rates,
            "fair_value_curves": fair_value_curves,
            "sofr_spread_data": sofr_spread_data_excel
        }

    except Exception as e:
        error_type = type(e).__name__
        error_msg = f"Error calling Gemini API: {error_type} - {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
        return {"error": error_msg}