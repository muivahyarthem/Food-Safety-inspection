
-- Food Inspection Analytics System (FIAS) - Database Schema
-- 1. Create Dimension Tables

-- Date Dimension
IF OBJECT_ID('dim_date', 'U') IS NULL
BEGIN
    CREATE TABLE dim_date (
        date_key INT PRIMARY KEY,             
        full_date DATE NOT NULL,
        year INT NOT NULL,
        quarter INT NOT NULL,
        month INT NOT NULL,
        month_name VARCHAR(20) NOT NULL,
        day_of_week INT NOT NULL,
        day_name VARCHAR(20) NOT NULL,
        is_weekend BIT NOT NULL
    );
END
GO

-- Facility Type Dimension
IF OBJECT_ID('dim_facility_type', 'U') IS NULL
BEGIN
    CREATE TABLE dim_facility_type (
        facility_type_key INT IDENTITY(1,1) PRIMARY KEY,
        raw_name VARCHAR(150) NOT NULL,
        standardized_category VARCHAR(100) NOT NULL,
        CONSTRAINT uq_facility_type UNIQUE (raw_name)
    );
END
GO

-- Geography Dimension
IF OBJECT_ID('dim_geography', 'U') IS NULL
BEGIN
    CREATE TABLE dim_geography (
        geography_key INT IDENTITY(1,1) PRIMARY KEY,
        street_address VARCHAR(255) NOT NULL,
        city VARCHAR(50) DEFAULT 'CHICAGO',
        state VARCHAR(10) DEFAULT 'IL',
        zip_code VARCHAR(10),
        latitude DECIMAL(9,6),
        longitude DECIMAL(9,6),
        CONSTRAINT uq_geography UNIQUE (street_address, zip_code)
    );
END
GO

-- Establishment Dimension
IF OBJECT_ID('dim_establishment', 'U') IS NULL
BEGIN
    CREATE TABLE dim_establishment (
        establishment_key INT IDENTITY(1,1) PRIMARY KEY,
        license_number INT NOT NULL,
        dba_name VARCHAR(255) NOT NULL,
        aka_name VARCHAR(255),
        risk_level VARCHAR(50),
        first_inspection_date DATE,
        last_inspection_date DATE,
        CONSTRAINT uq_establishment UNIQUE (license_number, dba_name)
    );
END
GO

-- 2. Create Fact Tables

-- Main Inspections Fact Table
IF OBJECT_ID('fact_inspections', 'U') IS NULL
BEGIN
    CREATE TABLE fact_inspections (
        inspection_id BIGINT PRIMARY KEY,
        date_key INT FOREIGN KEY REFERENCES dim_date(date_key),
        establishment_key INT FOREIGN KEY REFERENCES dim_establishment(establishment_key),
        geography_key INT FOREIGN KEY REFERENCES dim_geography(geography_key),
        facility_type_key INT FOREIGN KEY REFERENCES dim_facility_type(facility_type_key),
        inspection_type VARCHAR(100) NOT NULL,
        results VARCHAR(50) NOT NULL,
        is_failure BIT NOT NULL,
        priority_violations_count INT DEFAULT 0,
        serious_violations_count INT DEFAULT 0,
        core_violations_count INT DEFAULT 0,
        total_violations_count INT DEFAULT 0,
        days_since_last_inspection INT NULL,
        prior_failures_cumulative INT DEFAULT 0
    );
END
GO

-- Granular Violations Fact Table (Child of fact_inspections)
IF OBJECT_ID('fact_violations', 'U') IS NULL
BEGIN
    CREATE TABLE fact_violations (
        violation_id BIGINT IDENTITY(1,1) PRIMARY KEY,
        inspection_id BIGINT FOREIGN KEY REFERENCES fact_inspections(inspection_id) ON DELETE CASCADE,
        violation_code INT NOT NULL,
        violation_description VARCHAR(255) NOT NULL,
        severity_tier VARCHAR(50) NOT NULL,
        severity_weight INT NOT NULL,
        inspector_comment NVARCHAR(MAX)
    );
END
GO

-- 3. Create Performance Indexes
IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_inspections_estab')
    CREATE INDEX idx_fact_inspections_estab ON fact_inspections(establishment_key);
GO

IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_inspections_date')
    CREATE INDEX idx_fact_inspections_date ON fact_inspections(date_key);
GO

IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_inspections_geo')
    CREATE INDEX idx_fact_inspections_geo ON fact_inspections(geography_key);
GO

IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_inspections_results')
    CREATE INDEX idx_fact_inspections_results ON fact_inspections(results);
GO

IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_violations_code')
    CREATE INDEX idx_fact_violations_code ON fact_violations(violation_code);
GO

IF NOT EXISTS (SELECT name FROM sys.indexes WHERE name = 'idx_fact_violations_inspection')
    CREATE INDEX idx_fact_violations_inspection ON fact_violations(inspection_id);
GO

-- 4. Analytical Views for Reporting & Dashboards
-- View 1: Establishment Risk Mart & Recidivism
IF OBJECT_ID('vw_establishment_risk_mart', 'V') IS NOT NULL
    DROP VIEW vw_establishment_risk_mart;
GO
CREATE VIEW vw_establishment_risk_mart AS
WITH historical_lags AS (
    SELECT 
        i.inspection_id,
        i.establishment_key,
        i.date_key,
        d.full_date,
        i.is_failure,
        i.priority_violations_count,
        i.total_violations_count,
        LAG(d.full_date) OVER (
            PARTITION BY i.establishment_key 
            ORDER BY d.full_date ASC, i.inspection_id ASC
        ) AS previous_inspection_date,
        LAG(i.is_failure) OVER (
            PARTITION BY i.establishment_key 
            ORDER BY d.full_date ASC, i.inspection_id ASC
        ) AS previous_was_failure
    FROM fact_inspections i
    JOIN dim_date d ON i.date_key = d.date_key
)
SELECT 
    hl.inspection_id,
    hl.establishment_key,
    hl.full_date AS inspection_date,
    hl.is_failure,
    COALESCE(DATEDIFF(day, hl.previous_inspection_date, hl.full_date), 0) AS days_since_prior_inspection,
    CASE WHEN hl.is_failure = 1 AND hl.previous_was_failure = 1 THEN 1 ELSE 0 END AS is_consecutive_failure,
    COUNT(CASE WHEN hl.is_failure = 1 THEN 1 END) OVER (
        PARTITION BY hl.establishment_key 
        ORDER BY hl.full_date, hl.inspection_id 
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS cumulative_prior_failures,
    ROUND(AVG(CASE WHEN hl.is_failure = 1 THEN 1.0 ELSE 0.0 END) OVER (
        PARTITION BY hl.establishment_key 
        ORDER BY hl.full_date, hl.inspection_id 
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    ), 2) AS rolling_3_prior_failure_rate
FROM historical_lags hl;
GO

-- View 2: Geographic Hotspot Summary by Zip Code
IF OBJECT_ID('vw_zip_code_risk_summary', 'V') IS NOT NULL
    DROP VIEW vw_zip_code_risk_summary;
GO
CREATE VIEW vw_zip_code_risk_summary AS
SELECT 
    g.zip_code,
    COUNT(DISTINCT e.license_number) AS active_establishments,
    COUNT(i.inspection_id) AS total_inspections,
    ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
    SUM(i.priority_violations_count) AS total_priority_violations,
    ROUND(CAST(SUM(i.priority_violations_count) AS FLOAT) / NULLIF(COUNT(i.inspection_id), 0), 2) AS priority_violations_per_inspection
FROM fact_inspections i
JOIN dim_geography g ON i.geography_key = g.geography_key
JOIN dim_establishment e ON i.establishment_key = e.establishment_key
WHERE g.zip_code IS NOT NULL AND g.zip_code != '00000'
GROUP BY g.zip_code;
GO

-- View 3: Top Violations Pareto Distribution
IF OBJECT_ID('vw_top_violations_pareto', 'V') IS NOT NULL
    DROP VIEW vw_top_violations_pareto;
GO
CREATE VIEW vw_top_violations_pareto AS
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
SELECT 
    violation_code,
    violation_description,
    severity_tier,
    citation_frequency,
    ROUND(100.0 * citation_frequency / NULLIF(grand_total_citations, 0), 2) AS pct_of_all_citations,
    ROUND(100.0 * running_cumulative_citations / NULLIF(grand_total_citations, 0), 2) AS cumulative_share_pct
FROM ranked_violations;
GO

-- View 4: Monthly Seasonality & Moving Failure Rate
IF OBJECT_ID('vw_monthly_seasonality', 'V') IS NOT NULL
    DROP VIEW vw_monthly_seasonality;
GO
CREATE VIEW vw_monthly_seasonality AS
WITH monthly_metrics AS (
    SELECT 
        d.year,
        d.month,
        d.month_name,
        COUNT(i.inspection_id) AS total_inspections,
        SUM(CAST(i.is_failure AS INT)) AS failed_inspections,
        ROUND(100.0 * SUM(CAST(i.is_failure AS FLOAT)) / NULLIF(COUNT(i.inspection_id), 0), 2) AS monthly_fail_rate
    FROM fact_inspections i
    JOIN dim_date d ON i.date_key = d.date_key
    GROUP BY d.year, d.month, d.month_name
)
SELECT 
    year,
    month,
    month_name,
    total_inspections,
    failed_inspections,
    monthly_fail_rate,
    ROUND(AVG(monthly_fail_rate) OVER (
        ORDER BY year, month 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 2) AS moving_avg_fail_rate_3mo
FROM monthly_metrics;
GO

-- View 5: Inspection Type Efficacy Comparison
IF OBJECT_ID('vw_inspection_type_comparison', 'V') IS NOT NULL
    DROP VIEW vw_inspection_type_comparison;
GO
CREATE VIEW vw_inspection_type_comparison AS
SELECT 
    i.inspection_type,
    COUNT(i.inspection_id) AS total_inspections,
    SUM(CAST(i.is_failure AS INT)) AS total_failures,
    ROUND(100.0 * AVG(CAST(i.is_failure AS FLOAT)), 2) AS failure_rate_pct,
    ROUND(AVG(CAST(i.priority_violations_count AS FLOAT)), 2) AS avg_priority_violations
FROM fact_inspections i
GROUP BY i.inspection_type;
GO
