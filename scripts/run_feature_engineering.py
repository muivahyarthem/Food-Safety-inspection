"""
Feature Engineering & Analytical Risk Mart Runner
==================================================
This script executes the SQL feature engineering logic against Microsoft SQL Server.
It creates:
  1. vw_establishment_risk_mart (View with lag analysis, chronic offender flags)
  2. analytics_establishment_risk_mart (Materialized physical table for fast dashboard reporting)
  3. vw_overdue_inspections (View showing establishments due or overdue for inspection)
  4. vw_geospatial_hotspot_scores (View ranking Chicago zip codes by composite risk score)

Usage:
  python scripts/run_feature_engineering.py
"""

import sys
import re
from pathlib import Path

# Add project root to Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

import database.connection as db
import config

def execute_sql_file(sql_file_path: Path):
    """
    Reads a SQL file and executes it in Microsoft SQL Server.
    SQL Server scripts often use 'GO' commands to separate batches of statements.
    This function splits the file by 'GO' and runs each batch one by one.
    """
    print(f"[*] Reading SQL script from: {sql_file_path.name}")
    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split SQL script into separate batches wherever 'GO' appears on its own line
    # Regex explanation:
    #   ^\s*GO\s*$ matches lines that only contain the word GO (ignoring leading/trailing spaces)
    batches = re.split(r'^\s*GO\s*$', sql_content, flags=re.MULTILINE | re.IGNORECASE)

    conn = db.get_connection(database=config.DB_NAME)
    conn.autocommit = True
    cursor = conn.cursor()

    executed_count = 0
    for batch in batches:
        clean_batch = batch.strip()
        # Skip empty lines or purely comment batches
        if clean_batch and not clean_batch.startswith("USE"):
            try:
                cursor.execute(clean_batch)
                executed_count += 1
            except Exception as e:
                # Some DDLs might throw warnings or benign errors; print clearly
                print(f"[!] Warning executing statement: {e}")

    print(f"[+] Successfully executed {executed_count} SQL batches.")
    conn.close()

def display_risk_mart_insights():
    """
    Runs quick verification queries on the newly created risk tables
    and prints clear, beginner-friendly results.
    """
    conn = db.get_connection(database=config.DB_NAME)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("STEP 3: FEATURE ENGINEERING & RISK MART SUMMARY")
    print("=" * 80)

    # 1. Total records in analytics_establishment_risk_mart
    cursor.execute("SELECT COUNT(*), SUM(CAST(is_chronic_offender AS INT)) FROM analytics_establishment_risk_mart")
    total_inspections, chronic_records = cursor.fetchone()
    print(f"\n[1] Materialized Risk Mart Table:")
    print(f"    - Total Analyzed Inspections: {total_inspections:,}")
    print(f"    - Inspections Flagged as Chronic Offender Incidents: {chronic_records:,}")

    # 2. Top 5 Chronic Repeat Offenders
    print("\n[2] Top 5 Chronic Repeat Offenders (Establishments with Repeated Failures):")
    print("-" * 80)
    sql_chronic = """
        SELECT TOP 5 
            license_number,
            dba_name,
            risk_level,
            cumulative_prior_failures,
            rolling_3_prior_failure_rate
        FROM analytics_establishment_risk_mart
        WHERE is_chronic_offender = 1
        ORDER BY cumulative_prior_failures DESC, rolling_3_prior_failure_rate DESC
    """
    cursor.execute(sql_chronic)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            lic, dba, risk, prior_fails, roll_rate = r
            print(f"    - License #{lic} | {dba:<32} | {risk:<16} | Prior Fails: {prior_fails} | Rolling Fail Rate: {int(roll_rate*100)}%")
    else:
        print("    (No chronic offenders found in current sample)")

    # 3. Overdue Inspections Breakdown
    print("\n[3] Overdue Inspections Summary (Establishments Exceeding CDPH Mandates):")
    print("-" * 80)
    sql_overdue = """
        SELECT overdue_status, COUNT(*) AS total_establishments
        FROM vw_overdue_inspections
        GROUP BY overdue_status
        ORDER BY total_establishments DESC
    """
    cursor.execute(sql_overdue)
    for status, count in cursor.fetchall():
        print(f"    - {status:<22} : {count:,} establishments")

    # 4. Top 5 Hotspot Zip Codes
    print("\n[4] Top 5 High-Risk Geographic Hotspot Zip Codes:")
    print("-" * 80)
    sql_hotspots = """
        SELECT TOP 5 
            zip_code, 
            total_active_establishments, 
            failure_rate_pct, 
            priority_violations_per_inspection, 
            composite_hotspot_score,
            hotspot_tier
        FROM vw_geospatial_hotspot_scores
        ORDER BY composite_hotspot_score DESC
    """
    cursor.execute(sql_hotspots)
    for zip_c, est_cnt, fail_pct, pri_viol, score, tier in cursor.fetchall():
        print(f"    - Zip Code {zip_c} | Score: {score:>4.1f}/100 [{tier}] | Fail Rate: {fail_pct:>5.1f}% | Priority Viol/Insp: {pri_viol}")

    print("\n" + "=" * 80)
    print("[SUCCESS] Feature Engineering & Risk Marts are live in Microsoft SQL Server!")
    print("=" * 80)
    conn.close()

def main():
    sql_path = PROJECT_ROOT / "database" / "feature_engineering.sql"
    if not sql_path.exists():
        print(f"[ERROR] SQL file not found at: {sql_path}")
        return

    execute_sql_file(sql_path)
    display_risk_mart_insights()

if __name__ == "__main__":
    main()
