"""
Analytics Runner Module
=======================
Executes the analytical queries directly on Microsoft SQL Server
and prints clean summary tables answering the 4 core business questions.
"""

import database.connection as db
import pandas as pd

def run_query(sql: str, description: str):
    """Executes a SQL query and returns a pandas DataFrame."""
    print("\n" + "=" * 80)
    print(description)
    print("=" * 80)
    conn = db.get_connection()
    try:
        df = pd.read_sql(sql, conn)
        return df
    finally:
        conn.close()

def display_business_insights():
    """Runs all 4 business question queries and prints formatted tables."""
    print("\n" + "#" * 80)
    print("FOOD SAFETY INSPECTION - ANALYTICAL INSIGHTS & KPI REPORT")
    print("#" * 80)

    # 1. Overall Summary
    q_summary = """
    SELECT 
        COUNT(i.inspection_id) AS total_inspections,
        COUNT(DISTINCT i.establishment_key) AS unique_establishments,
        ROUND(100.0 * AVG(CASE WHEN i.results = 'Pass' THEN 1.0 ELSE 0.0 END), 2) AS overall_pass_rate_pct,
        ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS overall_fail_rate_pct,
        SUM(i.priority_violations_count) AS total_priority_violations,
        SUM(i.total_violations_count) AS total_violations_cited
    FROM fact_inspections i;
    """
    df_sum = run_query(q_summary, "OVERALL SYSTEM SUMMARY")
    print(df_sum.to_string(index=False))

    # 2. Resource Allocation (Zip Code Hotspots)
    q1 = """
    SELECT TOP 10
        g.zip_code,
        COUNT(i.inspection_id) AS total_inspections,
        SUM(CAST(i.is_failure AS INT)) AS failed_inspections,
        ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
        SUM(i.priority_violations_count) AS priority_violations
    FROM fact_inspections i
    JOIN dim_geography g ON i.geography_key = g.geography_key
    WHERE g.zip_code IS NOT NULL AND g.zip_code != '00000'
    GROUP BY g.zip_code
    HAVING COUNT(i.inspection_id) >= 10
    ORDER BY failure_rate_pct DESC, priority_violations DESC;
    """
    df1 = run_query(q1, "QUESTION 1: TOP HIGH-RISK ZIP CODES (RESOURCE ALLOCATION)")
    print(df1.to_string(index=False))

    # 3. Chronic Repeat Offenders
    q2 = """
    SELECT TOP 10
        e.license_number,
        e.dba_name,
        e.risk_level,
        COUNT(i.inspection_id) AS inspections_count,
        SUM(CAST(i.is_failure AS INT)) AS failures_count,
        ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
        SUM(i.priority_violations_count) AS priority_violations
    FROM fact_inspections i
    JOIN dim_establishment e ON i.establishment_key = e.establishment_key
    GROUP BY e.license_number, e.dba_name, e.risk_level
    HAVING SUM(CAST(i.is_failure AS INT)) >= 2
    ORDER BY failures_count DESC, failure_rate_pct DESC;
    """
    df2 = run_query(q2, "QUESTION 2: CHRONIC REPEAT OFFENDERS (ESTABLISHMENT RISK PROFILING)")
    print(df2.to_string(index=False))

    # 4. Top Critical Violations (Pareto)
    q3 = """
    SELECT TOP 10
        violation_code,
        LEFT(violation_description, 45) AS violation_description,
        severity_tier,
        citation_frequency,
        pct_of_all_citations,
        cumulative_share_pct
    FROM vw_top_violations_pareto
    ORDER BY citation_frequency DESC;
    """
    df3 = run_query(q3, "QUESTION 3: TOP VIOLATIONS DIAGNOSTICS (PARETO ANALYSIS)")
    print(df3.to_string(index=False))

    # 5. Monthly Seasonality
    q4 = """
    SELECT 
        year,
        month,
        month_name,
        total_inspections,
        failed_inspections,
        monthly_fail_rate,
        moving_avg_fail_rate_3mo
    FROM vw_monthly_seasonality
    ORDER BY year DESC, month DESC;
    """
    df4 = run_query(q4, "QUESTION 4: MONTHLY TEMPORAL TRENDS & SEASONALITY")
    print(df4.head(12).to_string(index=False))

    print("\n" + "=" * 80)
    print("[+] All analytical queries executed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    display_business_insights()
