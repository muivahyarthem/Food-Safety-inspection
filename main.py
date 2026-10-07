"""
Main Execution Script
=====================
End-to-End Pipeline for Chicago Food Safety Inspection Analytics:
1. Verifies/Creates database and Star Schema tables in Microsoft SQL Server.
2. Extracts inspection data from the API specified in API.txt.
3. Cleans, standardizes, and parses raw text violations using regex.
4. Loads data into Dimension and Fact tables in SQL Server.
5. Builds Feature Engineering & Analytical Risk Marts (lag days, chronic offenders).
6. Runs analytical queries answering the core business questions.

Usage:
    python main.py
"""

import sys
import time
from database.connection import initialize_database
from pipeline.extractor import fetch_inspections
from pipeline.transformer import transform_raw_records
from pipeline.loader import load_all
from analytics.run_analytics import display_business_insights
import config

def run_pipeline():
    start_time = time.time()
    print("=" * 80)
    print("FOOD SAFETY INSPECTION ANALYTICS SYSTEM (FIAS)")
    print("Target Database: Microsoft SQL Server (SSMS)")
    print(f"API Endpoint:    {config.API_URL}")
    print(f"Record Limit:    {config.RECORD_LIMIT} records")
    print("=" * 80)

    # Step 1: Initialize Database & Schema in SQL Server
    print("\n[STEP 1/5] Initializing Database & Star Schema...")
    initialize_database()

    # Step 2: Extract data from API
    print("\n[STEP 2/5] Extracting Data from Chicago Open Data Portal...")
    raw_records = fetch_inspections(total_records=config.RECORD_LIMIT, batch_size=config.BATCH_SIZE)
    if not raw_records:
        print("[!] No records extracted. Pipeline terminating.")
        return

    # Step 3: Transform and Parse Violations
    print("\n[STEP 3/5] Transforming Data & Parsing Unstructured Violations...")
    transformed_data = transform_raw_records(raw_records)

    # Step 4: Load into SQL Server
    print("\n[STEP 4/6] Loading Data into Microsoft SQL Server...")
    load_all(transformed_data)

    # Step 5: Feature Engineering & Risk Marts
    print("\n[STEP 5/6] Building Feature Engineering & Analytical Risk Marts...")
    feature_sql = config.BASE_DIR / "database" / "feature_engineering.sql"
    if feature_sql.exists():
        from scripts.run_feature_engineering import execute_sql_file
        execute_sql_file(feature_sql)

    # Step 6: Execute Analytics & Business Queries
    print("\n[STEP 6/6] Running Analytical KPI Queries...")
    display_business_insights()

    elapsed = round(time.time() - start_time, 2)
    print(f"\n[DONE] Pipeline completed successfully in {elapsed} seconds!")
    print(f"[Tip] Open Microsoft SQL Server Management Studio (SSMS) and connect to '{config.DB_SERVER}' to query 'FoodInspectionDB'.")

if __name__ == "__main__":
    run_pipeline()
