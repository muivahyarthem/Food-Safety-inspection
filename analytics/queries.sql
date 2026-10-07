-- ============================================================================
-- Food Inspection Analytics System (FIAS)
-- Core Analytical SQL Queries (T-SQL / Microsoft SQL Server)
-- ============================================================================
-- You can run these queries directly in SQL Server Management Studio (SSMS)
-- Make sure you are using the database:
USE FoodInspectionDB;
GO

-- ============================================================================
-- BUSINESS QUESTION 1: RESOURCE ALLOCATION
-- Which zip codes exhibit high failure rates and recurrent high-risk violations?
-- ============================================================================
SELECT TOP 15
    g.zip_code,
    COUNT(DISTINCT e.license_number) AS active_establishments,
    COUNT(i.inspection_id) AS total_inspections,
    SUM(CAST(i.is_failure AS INT)) AS total_failed_inspections,
    ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
    SUM(i.priority_violations_count) AS total_priority_violations,
    ROUND(CAST(SUM(i.priority_violations_count) AS FLOAT) / NULLIF(COUNT(i.inspection_id), 0), 2) AS priority_violations_per_inspection
FROM fact_inspections i
JOIN dim_geography g ON i.geography_key = g.geography_key
JOIN dim_establishment e ON i.establishment_key = e.establishment_key
WHERE g.zip_code IS NOT NULL AND g.zip_code != '00000'
GROUP BY g.zip_code
HAVING COUNT(i.inspection_id) >= 20
ORDER BY failure_rate_pct DESC, total_priority_violations DESC;
GO


-- ============================================================================
-- BUSINESS QUESTION 2: ESTABLISHMENT RISK PROFILING
-- Which establishments have a chronic history of failing inspections (Chronic Offenders)?
-- ============================================================================
SELECT TOP 25
    e.license_number,
    e.dba_name,
    e.risk_level,
    COUNT(i.inspection_id) AS total_inspections,
    SUM(CAST(i.is_failure AS INT)) AS total_failures,
    ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_probability_pct,
    SUM(i.priority_violations_count) AS total_priority_violations,
    MAX(d.full_date) AS most_recent_inspection_date,
    DATEDIFF(day, MAX(d.full_date), GETDATE()) AS days_since_last_inspection
FROM fact_inspections i
JOIN dim_establishment e ON i.establishment_key = e.establishment_key
JOIN dim_date d ON i.date_key = d.date_key
GROUP BY e.license_number, e.dba_name, e.risk_level
HAVING SUM(CAST(i.is_failure AS INT)) >= 2
ORDER BY total_failures DESC, failure_probability_pct DESC;
GO


-- ============================================================================
-- BUSINESS QUESTION 3: VIOLATION DIAGNOSTICS
-- What are the most common critical violations leading to failure or hazard?
-- (Ranked by Pareto frequency & severity)
-- ============================================================================
WITH violation_counts AS (
    SELECT 
        v.violation_code,
        v.violation_description,
        v.severity_tier,
        COUNT(*) AS citation_frequency
    FROM fact_violations v
    GROUP BY v.violation_code, v.violation_description, v.severity_tier
),
ranked_violations AS (
    SELECT 
        violation_code,
        violation_description,
        severity_tier,
        citation_frequency,
        SUM(citation_frequency) OVER (ORDER BY citation_frequency DESC) AS running_cumulative_citations,
        SUM(citation_frequency) OVER () AS grand_total_citations
    FROM violation_counts
)
SELECT TOP 15
    violation_code,
    violation_description,
    severity_tier,
    citation_frequency,
    ROUND(100.0 * citation_frequency / NULLIF(grand_total_citations, 0), 2) AS pct_of_all_citations,
    ROUND(100.0 * running_cumulative_citations / NULLIF(grand_total_citations, 0), 2) AS cumulative_share_pct
FROM ranked_violations
ORDER BY citation_frequency DESC;
GO


-- ============================================================================
-- BUSINESS QUESTION 4: TEMPORAL & SEASONALITY PATTERNS
-- Are there seasonal spikes in violations (Summer vs Winter) and monthly failure drift?
-- ============================================================================
SELECT 
    d.month,
    d.month_name,
    COUNT(i.inspection_id) AS total_inspections,
    SUM(CAST(i.is_failure AS INT)) AS failed_inspections,
    ROUND(100.0 * SUM(CAST(i.is_failure AS FLOAT)) / NULLIF(COUNT(i.inspection_id), 0), 2) AS failure_rate_pct,
    SUM(i.priority_violations_count) AS total_priority_violations
FROM fact_inspections i
JOIN dim_date d ON i.date_key = d.date_key
GROUP BY d.month, d.month_name
ORDER BY d.month ASC;
GO


-- ============================================================================
-- BONUS: BASELINE METRICS BY FACILITY TYPE
-- (Restaurants vs Grocery Stores vs Schools vs Bakeries)
-- ============================================================================
SELECT 
    f.standardized_category,
    COUNT(i.inspection_id) AS total_inspections,
    ROUND(100.0 * AVG(CASE WHEN i.results = 'Pass' THEN 1.0 ELSE 0.0 END), 2) AS pct_pass,
    ROUND(100.0 * AVG(CASE WHEN i.results = 'Pass w/ Conditions' THEN 1.0 ELSE 0.0 END), 2) AS pct_conditional,
    ROUND(100.0 * AVG(CASE WHEN i.results = 'Fail' THEN 1.0 ELSE 0.0 END), 2) AS pct_fail,
    ROUND(AVG(CAST(i.total_violations_count AS FLOAT)), 2) AS avg_violations_per_inspection
FROM fact_inspections i
JOIN dim_facility_type f ON i.facility_type_key = f.facility_type_key
GROUP BY f.standardized_category
ORDER BY total_inspections DESC;
GO
