
-- Feature Engineering & Analytical Risk Marts
-- 
-- 1. Create 'vw_establishment_risk_mart': Computes inspection gaps, recidivism,
--    and chronic offender indicators using SQL window functions (LAG, OVER).
-- 2. Materializes 'analytics_establishment_risk_mart': Creates a fast, indexed
--    physical table for high-speed dashboard reporting.
-- 3. Create 'vw_overdue_inspections': Flags food businesses that have exceeded
--    the official inspection timeframe (High risk > 365 days, Medium > 730 days).
-- 4. Create 'vw_geospatial_hotspot_scores': Calculates a composite 0-100 Hotspot
--    Risk Score for each Chicago zip code to prioritize inspector assignments.


USE FoodInspectionDB;
GO

-- 1. ESTABLISHMENT RISK MART VIEW (vw_establishment_risk_mart)


IF OBJECT_ID('dbo.vw_establishment_risk_mart', 'V') IS NOT NULL
    DROP VIEW dbo.vw_establishment_risk_mart;
GO

CREATE VIEW dbo.vw_establishment_risk_mart AS
WITH inspection_history AS (
    -- Step A: Get all inspections in chronological order for each establishment
    SELECT 
        i.inspection_id,
        i.establishment_key,
        e.license_number,
        e.dba_name,
        e.aka_name,
        e.risk_level,
        f.standardized_category AS facility_category,
        g.zip_code,
        g.street_address,
        g.latitude,
        g.longitude,
        d.full_date AS inspection_date,
        d.year AS inspection_year,
        i.inspection_type,
        i.results,
        i.is_failure,
        i.priority_violations_count,
        i.serious_violations_count,
        i.core_violations_count,
        i.total_violations_count,

        -- 1. Date of the previous inspection for this same restaurant
        LAG(d.full_date) OVER (
            PARTITION BY i.establishment_key 
            ORDER BY d.full_date ASC, i.inspection_id ASC
        ) AS prev_inspection_date,

        -- 2. Did the previous inspection fail? (1 = Yes, 0 = No, NULL = First visit)
        LAG(CAST(i.is_failure AS INT)) OVER (
            PARTITION BY i.establishment_key 
            ORDER BY d.full_date ASC, i.inspection_id ASC
        ) AS prev_was_failure,

        -- 3. Result of the previous inspection
        LAG(i.results) OVER (
            PARTITION BY i.establishment_key 
            ORDER BY d.full_date ASC, i.inspection_id ASC
        ) AS prev_result

    FROM dbo.fact_inspections i
    INNER JOIN dbo.dim_establishment e ON i.establishment_key = e.establishment_key
    INNER JOIN dbo.dim_date d ON i.date_key = d.date_key
    LEFT JOIN dbo.dim_facility_type f ON i.facility_type_key = f.facility_type_key
    LEFT JOIN dbo.dim_geography g ON i.geography_key = g.geography_key
),
calculated_features AS (
    -- Step B: Compute recency gaps, consecutive failure flags, and rolling averages
    SELECT 
        ih.*,

        -- Feature 1: Days elapsed since the restaurant was last inspected
        -- (Defaults to 0 for the very first inspection on record)
        COALESCE(DATEDIFF(day, ih.prev_inspection_date, ih.inspection_date), 0) AS days_since_prior_inspection,

        -- Feature 2: Consecutive Failure Flag (1 if current inspection failed AND previous inspection also failed)
        CASE 
            WHEN ih.is_failure = 1 AND ih.prev_was_failure = 1 THEN 1 
            ELSE 0 
        END AS is_consecutive_failure,

        -- Feature 3: Cumulative prior failures before this inspection date
        -- Counts all historical failures up to (but not including) the current row
        COUNT(CASE WHEN ih.is_failure = 1 THEN 1 END) OVER (
            PARTITION BY ih.establishment_key 
            ORDER BY ih.inspection_date, ih.inspection_id 
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS cumulative_prior_failures,

        -- Feature 4: Rolling failure rate over the last 3 prior inspections (0.00 to 1.00)
        ROUND(AVG(CASE WHEN ih.is_failure = 1 THEN 1.0 ELSE 0.0 END) OVER (
            PARTITION BY ih.establishment_key 
            ORDER BY ih.inspection_date, ih.inspection_id 
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ), 2) AS rolling_3_prior_failure_rate,

        -- Feature 5: Total inspections conducted on this establishment up to this point
        COUNT(*) OVER (
            PARTITION BY ih.establishment_key 
            ORDER BY ih.inspection_date, ih.inspection_id 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS inspection_visit_number

    FROM inspection_history ih
)
SELECT 
    cf.*,
    -- Feature 6: Chronic Offender Indicator
    -- A business is flagged as a Chronic Offender if:
    -- (a) It has consecutive failures, OR
    -- (b) It has accumulated 2 or more historical failures
    CASE 
        WHEN cf.is_consecutive_failure = 1 OR cf.cumulative_prior_failures >= 2 THEN 1 
        ELSE 0 
    END AS is_chronic_offender
FROM calculated_features cf;
GO



-- 2. MATERIALIZED PHYSICAL TABLE (analytics_establishment_risk_mart)

IF OBJECT_ID('dbo.analytics_establishment_risk_mart', 'U') IS NOT NULL
    DROP TABLE dbo.analytics_establishment_risk_mart;
GO

SELECT *
INTO dbo.analytics_establishment_risk_mart
FROM dbo.vw_establishment_risk_mart;
GO

-- Add primary key & performance indexes
ALTER TABLE dbo.analytics_establishment_risk_mart 
    ADD CONSTRAINT pk_analytics_risk_mart PRIMARY KEY (inspection_id);
GO

CREATE INDEX idx_risk_mart_license ON dbo.analytics_establishment_risk_mart(license_number);
CREATE INDEX idx_risk_mart_chronic ON dbo.analytics_establishment_risk_mart(is_chronic_offender);
CREATE INDEX idx_risk_mart_zip ON dbo.analytics_establishment_risk_mart(zip_code);
CREATE INDEX idx_risk_mart_risk_level ON dbo.analytics_establishment_risk_mart(risk_level);
GO



-- 3. OVERDUE INSPECTIONS VIEW (vw_overdue_inspections)
IF OBJECT_ID('dbo.vw_overdue_inspections', 'V') IS NOT NULL
    DROP VIEW dbo.vw_overdue_inspections;
GO

CREATE VIEW dbo.vw_overdue_inspections AS
WITH latest_visits AS (
    SELECT 
        e.establishment_key,
        e.license_number,
        e.dba_name,
        e.aka_name,
        e.risk_level,
        MAX(d.full_date) AS most_recent_inspection_date,
        -- Find the outcome of the most recent inspection
        (
            SELECT TOP 1 fi.results 
            FROM dbo.fact_inspections fi 
            JOIN dbo.dim_date dd ON fi.date_key = dd.date_key
            WHERE fi.establishment_key = e.establishment_key
            ORDER BY dd.full_date DESC, fi.inspection_id DESC
        ) AS most_recent_result,
        -- Get the location info
        MAX(g.street_address) AS street_address,
        MAX(g.zip_code) AS zip_code,
        MAX(g.latitude) AS latitude,
        MAX(g.longitude) AS longitude
    FROM dbo.dim_establishment e
    INNER JOIN dbo.fact_inspections i ON e.establishment_key = i.establishment_key
    INNER JOIN dbo.dim_date d ON i.date_key = d.date_key
    LEFT JOIN dbo.dim_geography g ON i.geography_key = g.geography_key
    GROUP BY e.establishment_key, e.license_number, e.dba_name, e.aka_name, e.risk_level
)
SELECT 
    lv.license_number,
    lv.dba_name,
    lv.aka_name,
    lv.risk_level,
    lv.street_address,
    lv.zip_code,
    lv.latitude,
    lv.longitude,
    lv.most_recent_inspection_date,
    lv.most_recent_result,
    DATEDIFF(day, lv.most_recent_inspection_date, GETDATE()) AS days_since_last_inspection,

    -- Official threshold based on City of Chicago risk category
    CASE 
        WHEN lv.risk_level LIKE '%Risk 1%' THEN 365
        WHEN lv.risk_level LIKE '%Risk 2%' THEN 730
        WHEN lv.risk_level LIKE '%Risk 3%' THEN 1095
        ELSE 365
    END AS inspection_mandate_days,

    -- Overdue status indicator
    CASE 
        WHEN lv.most_recent_result IN ('Out of Business', 'Business Not Located') THEN 'Closed / Inactive'
        WHEN (lv.risk_level LIKE '%Risk 1%' AND DATEDIFF(day, lv.most_recent_inspection_date, GETDATE()) > 365) THEN 'CRITICAL OVERDUE'
        WHEN (lv.risk_level LIKE '%Risk 2%' AND DATEDIFF(day, lv.most_recent_inspection_date, GETDATE()) > 730) THEN 'MODERATE OVERDUE'
        WHEN (lv.risk_level LIKE '%Risk 3%' AND DATEDIFF(day, lv.most_recent_inspection_date, GETDATE()) > 1095) THEN 'LOW OVERDUE'
        ELSE 'Up to Date'
    END AS overdue_status

FROM latest_visits lv
WHERE lv.most_recent_result NOT IN ('Out of Business', 'Business Not Located');
GO

-- 4. GEOSPATIAL HOTSPOT RISK VIEW (vw_geospatial_hotspot_scores)

IF OBJECT_ID('dbo.vw_geospatial_hotspot_scores', 'V') IS NOT NULL
    DROP VIEW dbo.vw_geospatial_hotspot_scores;
GO

CREATE VIEW dbo.vw_geospatial_hotspot_scores AS
WITH zip_aggregates AS (
    SELECT 
        g.zip_code,
        COUNT(DISTINCT e.license_number) AS total_active_establishments,
        COUNT(i.inspection_id) AS total_inspections,
        SUM(CAST(i.is_failure AS INT)) AS total_failed_inspections,
        ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
        SUM(i.priority_violations_count) AS total_priority_violations,
        ROUND(CAST(SUM(i.priority_violations_count) AS FLOAT) / NULLIF(COUNT(i.inspection_id), 0), 2) AS priority_violations_per_inspection,
        ROUND(AVG(g.latitude), 6) AS centroid_latitude,
        ROUND(AVG(g.longitude), 6) AS centroid_longitude
    FROM dbo.fact_inspections i
    INNER JOIN dbo.dim_geography g ON i.geography_key = g.geography_key
    INNER JOIN dbo.dim_establishment e ON i.establishment_key = e.establishment_key
    WHERE g.zip_code IS NOT NULL AND g.zip_code != '00000' AND LEN(g.zip_code) = 5
    GROUP BY g.zip_code
    HAVING COUNT(i.inspection_id) >= 10
)
SELECT 
    za.*,
    -- Composite 0 - 100 Hotspot Risk Index
    -- (Failure rate capped at 60 points + priority violations per inspection scaled up to 40 points)
    ROUND(
        LEAST(100.0, 
            (za.failure_rate_pct * 0.6) + 
            (LEAST(za.priority_violations_per_inspection * 15.0, 40.0))
        ), 1
    ) AS composite_hotspot_score,

    -- Risk Category
    CASE 
        WHEN (za.failure_rate_pct * 0.6) + (za.priority_violations_per_inspection * 15.0) >= 40 THEN 'HIGH HOTSPOT'
        WHEN (za.failure_rate_pct * 0.6) + (za.priority_violations_per_inspection * 15.0) >= 25 THEN 'MODERATE HOTSPOT'
        ELSE 'LOW HOTSPOT'
    END AS hotspot_tier

FROM zip_aggregates za;
GO
