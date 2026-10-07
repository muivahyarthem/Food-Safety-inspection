"""
Step 1: API to Microsoft SQL Server (Beginner Friendly)
======================================================
This script performs Step 1 of your project:
1. Reads the API endpoint from API.txt.
2. Connects to your local Microsoft SQL Server (SQLEXPRESS).
3. Automatically creates the database 'FoodInspectionDB' and required tables if they don't exist.
4. Fetches inspection data from the City of Chicago API.
5. Cleans and saves the records directly into Microsoft SQL Server.

To run this script:
    python step1_api_to_sqlserver.py
"""

import time
import requests
import pyodbc
from pathlib import Path

# ============================================================================
# 1. CONFIGURATION
# ============================================================================

# Read API endpoint from API.txt (checks both scripts folder and root folder)
API_FILE = Path(__file__).resolve().parent / "API.txt"
if not API_FILE.exists():
    API_FILE = Path(__file__).resolve().parent.parent / "API.txt"

if API_FILE.exists():
    with open(API_FILE, "r", encoding="utf-8") as f:
        API_URL = f.read().strip()
else:
    API_URL = "https://data.cityofchicago.org/api/v3/views/4ijn-s7e5/query.json"

# SQL Server connection settings (for SQL Server Management Studio / SSMS)
# If your SSMS server name is different, you can edit SERVER_NAME below:
SERVER_NAME = r"localhost\SQLEXPRESS"
DATABASE_NAME = "FoodInspectionDB"

# Number of records to download for Step 1 (you can increase or decrease this)
TOTAL_RECORDS_TO_FETCH = 5000
BATCH_SIZE = 2500


# ============================================================================
# 2. DATABASE CONNECTION & SETUP
# ============================================================================

def get_odbc_driver():
    """Detects which SQL Server ODBC driver is installed on your computer."""
    drivers = pyodbc.drivers()
    for drv in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
        if drv in drivers:
            return drv
    return "ODBC Driver 18 for SQL Server"

def get_sql_connection(db_name="master"):
    """Creates a connection to Microsoft SQL Server using Windows Authentication."""
    driver = get_odbc_driver()
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={SERVER_NAME};"
        f"DATABASE={db_name};"
        f"Trusted_Connection=yes;"
    )
    if "18" in driver:
        conn_str += "TrustServerCertificate=yes;"
    return pyodbc.connect(conn_str, autocommit=True)

def setup_database_and_tables():
    """Creates the database and inspection tables in SQL Server if not already created."""
    print("\n--- [1] Setting up Microsoft SQL Server Database & Tables ---")
    
    # 1. Ensure Database exists
    master_conn = get_sql_connection(db_name="master")
    cursor = master_conn.cursor()
    cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{DATABASE_NAME}'")
    if not cursor.fetchone():
        print(f"[*] Creating database '{DATABASE_NAME}' in SQL Server...")
        cursor.execute(f"CREATE DATABASE [{DATABASE_NAME}];")
        print(f"[+] Database '{DATABASE_NAME}' created!")
    else:
        print(f"[+] Database '{DATABASE_NAME}' is ready.")
    master_conn.close()

    # 2. Create the clean tables in FoodInspectionDB
    db_conn = get_sql_connection(db_name=DATABASE_NAME)
    cur = db_conn.cursor()

    # Table 1: Inspections table
    cur.execute("""
    IF OBJECT_ID('raw_inspections', 'U') IS NULL
    BEGIN
        CREATE TABLE raw_inspections (
            inspection_id BIGINT PRIMARY KEY,
            dba_name VARCHAR(255),
            aka_name VARCHAR(255),
            license_number INT,
            facility_type VARCHAR(100),
            risk_level VARCHAR(50),
            address VARCHAR(255),
            city VARCHAR(50),
            state VARCHAR(10),
            zip_code VARCHAR(10),
            inspection_date DATE,
            inspection_type VARCHAR(100),
            results VARCHAR(50),
            latitude DECIMAL(9,6),
            longitude DECIMAL(9,6)
        );
        PRINT 'Table raw_inspections created.';
    END
    """)

    # Table 2: Violations table
    cur.execute("""
    IF OBJECT_ID('raw_violations', 'U') IS NULL
    BEGIN
        CREATE TABLE raw_violations (
            violation_id BIGINT IDENTITY(1,1) PRIMARY KEY,
            inspection_id BIGINT,
            violation_code INT,
            violation_description VARCHAR(255),
            severity_tier VARCHAR(50),
            inspector_comment NVARCHAR(MAX)
        );
        PRINT 'Table raw_violations created.';
    END
    """)

    db_conn.close()
    print("[+] SQL Server tables are ready for incoming data.")


# ============================================================================
# 3. API EXTRACTION
# ============================================================================

def fetch_data_from_api(total_records=TOTAL_RECORDS_TO_FETCH, batch_size=BATCH_SIZE):
    """Fetches data from the Chicago Food Safety API using pagination."""
    print(f"\n--- [2] Fetching Data from API: {API_URL} ---")
    print(f"[*] Fetching up to {total_records} records in batches of {batch_size}...")

    records = []
    offset = 0

    while len(records) < total_records:
        current_limit = min(batch_size, total_records - len(records))
        query = f"SELECT * ORDER BY inspection_date DESC, inspection_id DESC LIMIT {current_limit} OFFSET {offset}"
        
        print(f"    --> Requesting rows {offset + 1} to {offset + current_limit} from API...", end=" ", flush=True)
        try:
            res = requests.get(API_URL, params={"query": query}, timeout=30)
            if res.status_code != 200:
                print(f"\n[!] API error status: {res.status_code}")
                break

            batch = res.json()
            if not batch:
                print("No more data.")
                break

            records.extend(batch)
            print(f"Received {len(batch)} records. (Total: {len(records)})")

            if len(batch) < current_limit:
                break

            offset += len(batch)
            time.sleep(0.5)  # Friendly pause between requests

        except Exception as e:
            print(f"\n[!] Error connecting to API: {e}")
            break

    print(f"[+] Download complete: retrieved {len(records)} records from the API.")
    return records


# ============================================================================
# 4. SAVE DATA INTO MICROSOFT SQL SERVER
# ============================================================================

def save_to_sql_server(raw_records):
    """Inserts the API records into Microsoft SQL Server tables."""
    print("\n--- [3] Saving Data into Microsoft SQL Server ---")
    if not raw_records:
        print("[!] No records to save.")
        return

    conn = get_sql_connection(db_name=DATABASE_NAME)
    cur = conn.cursor()

    # Get already existing inspection IDs to avoid duplicates
    cur.execute("SELECT inspection_id FROM raw_inspections")
    existing_ids = {row[0] for row in cur.fetchall()}

    inspections_to_insert = []
    violations_to_insert = []

    for r in raw_records:
        try:
            insp_id = int(r.get("inspection_id"))
        except (ValueError, TypeError):
            continue

        if insp_id in existing_ids:
            continue

        # Extract & clean fields
        dba = (r.get("dba_name") or "").strip().upper()[:255]
        aka = (r.get("aka_name") or dba).strip().upper()[:255]
        
        try:
            lic = int(r.get("license_") or 0)
        except (ValueError, TypeError):
            lic = 0
            
        facility = (r.get("facility_type") or "Restaurant").strip().title()[:100]
        risk = (r.get("risk") or "Unassigned").strip()[:50]
        address = (r.get("address") or "").strip().upper()[:255]
        city = (r.get("city") or "CHICAGO").strip().upper()[:50]
        state = (r.get("state") or "IL").strip().upper()[:10]
        zip_code = (r.get("zip") or "")[:10]
        
        raw_date = r.get("inspection_date")
        date_str = raw_date[:10] if raw_date else "2000-01-01"
        
        insp_type = (r.get("inspection_type") or "Routine").strip()[:100]
        results = (r.get("results") or "Pass").strip()[:50]

        # Coordinates
        try:
            lat = float(r.get("latitude")) if r.get("latitude") else None
            lon = float(r.get("longitude")) if r.get("longitude") else None
        except (ValueError, TypeError):
            lat, lon = None, None

        inspections_to_insert.append((
            insp_id, dba, aka, lic, facility, risk,
            address, city, state, zip_code, date_str,
            insp_type, results, lat, lon
        ))

        # Extract violations text if present
        v_text = r.get("violations")
        if v_text:
            # Chicago violations are separated by ' | '
            parts = v_text.split(" | ")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Example: "10. ADEQUATE HANDWASHING SINKS - Comments: NO SOAP..."
                code_match = part.split(".", 1)
                if len(code_match) == 2 and code_match[0].isdigit():
                    code_num = int(code_match[0])
                    rest = code_match[1]
                else:
                    code_num = 0
                    rest = part

                if " - Comments:" in rest:
                    desc_part, comment_part = rest.split(" - Comments:", 1)
                else:
                    desc_part, comment_part = rest, ""

                desc = desc_part.strip()[:255]
                comm = comment_part.strip()

                if 1 <= code_num <= 14:
                    tier = "Priority (Critical)"
                elif 15 <= code_num <= 29:
                    tier = "Priority Foundation (Serious)"
                else:
                    tier = "Core (Minor)"

                violations_to_insert.append((
                    insp_id, code_num, desc, tier, comm
                ))

    # Fast batch insert into SQL Server
    cur.fast_executemany = True

    if inspections_to_insert:
        cur.executemany("""
            INSERT INTO raw_inspections (
                inspection_id, dba_name, aka_name, license_number, facility_type, risk_level,
                address, city, state, zip_code, inspection_date, inspection_type, results, latitude, longitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, inspections_to_insert)
        print(f"[+] Saved {len(inspections_to_insert)} inspection records into table 'raw_inspections'.")
    else:
        print("[+] All inspection records are already up to date in SQL Server.")

    if violations_to_insert:
        # Insert in chunks of 5000
        chunk_size = 5000
        for i in range(0, len(violations_to_insert), chunk_size):
            chunk = violations_to_insert[i:i + chunk_size]
            cur.executemany("""
                INSERT INTO raw_violations (
                    inspection_id, violation_code, violation_description, severity_tier, inspector_comment
                )
                VALUES (?, ?, ?, ?, ?)
            """, chunk)
        print(f"[+] Saved {len(violations_to_insert)} violation records into table 'raw_violations'.")

    # Display counts from SQL Server
    cur.execute("SELECT COUNT(*) FROM raw_inspections")
    total_insp = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM raw_violations")
    total_viol = cur.fetchone()[0]

    conn.close()

    print("\n" + "=" * 70)
    print("VERIFICATION: CURRENT ROWS IN MICROSOFT SQL SERVER")
    print(f"  Database:        {DATABASE_NAME}")
    print(f"  raw_inspections: {total_insp} rows")
    print(f"  raw_violations:  {total_viol} rows")
    print("=" * 70)


# ============================================================================
# 5. MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("=================================================================")
    print("FOOD SAFETY INSPECTION - STEP 1: API TO SQL SERVER")
    print("=================================================================")
    
    # 1. Setup Database & Tables in SQL Server
    setup_database_and_tables()

    # 2. Extract Data from API (API.txt)
    data = fetch_data_from_api(total_records=TOTAL_RECORDS_TO_FETCH, batch_size=BATCH_SIZE)

    # 3. Save into SQL Server
    save_to_sql_server(data)

    print("\n[SUCCESS] Step 1 finished successfully!")
    print(f"You can now open SQL Server Management Studio (SSMS), connect to '{SERVER_NAME}',")
    print(f"and browse the database '{DATABASE_NAME}'.")
