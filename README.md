# Food Safety Inspection Analytics System (FIAS)

This project connects directly to the **City of Chicago Food Inspections API** (from `API.txt`), fetches food inspection and violation records, and stores them directly into your local **Microsoft SQL Server Management Studio (SSMS)**.

---

## 🚀 Quick Start: Running Step 1

To fetch data from the API and save it into your Microsoft SQL Server, open your terminal / command prompt in this directory and run:

```bash
python scripts/step1_api_to_sqlserver.py
```

### What This Script Does:
1. **Reads API URL**: Automatically loads the API endpoint from `API.txt` (`https://data.cityofchicago.org/api/v3/views/4ijn-s7e5/query.json`).
2. **Connects to SQL Server**: Connects to your local SQL Server instance (`localhost\SQLEXPRESS`) using Windows Authentication.
3. **Creates the Database**: Automatically creates the database `FoodInspectionDB` if it doesn't already exist.
4. **Creates Tables**: Sets up `raw_inspections` and `raw_violations`.
5. **Fetches Data**: Uses pagination to download the inspection data in clean batches.
6. **Inserts into SQL Server**: Uses fast batch inserting to store records in SQL Server.

---

## 🖥️ Viewing the Data in Microsoft SQL Server Management Studio (SSMS)

Follow these simple steps to view your data in SSMS:

### 1. Open SSMS and Connect
- **Server type:** `Database Engine`
- **Server name:** `localhost\SQLEXPRESS` (or `.\SQLEXPRESS`)
- **Authentication:** `Windows Authentication`
- Click **Connect**.

### 2. Locate Your Database
In the left sidebar (**Object Explorer**):
1. Expand **Databases**.
2. Look for **`FoodInspectionDB`**.
3. Expand **Tables**:
   - `dbo.raw_inspections`
   - `dbo.raw_violations`
   - *(If running the full star schema, you will also see `dim_date`, `dim_establishment`, `dim_facility_type`, `dim_geography`, `fact_inspections`, and `fact_violations`)*.

### 3. Run Verification Queries
Click the **New Query** button at the top toolbar, paste any of the following queries, and press **F5** (or click **Execute**):

#### Check Inspection Count & Preview Rows:
```sql
USE FoodInspectionDB;
GO

-- View total row count
SELECT COUNT(*) AS total_inspections FROM raw_inspections;

-- Preview the latest 10 inspections
SELECT TOP 10 
    inspection_id, 
    dba_name, 
    facility_type, 
    risk_level, 
    address, 
    inspection_date, 
    results 
FROM raw_inspections
ORDER BY inspection_date DESC;
```

#### Check Violations Preview:
```sql
USE FoodInspectionDB;
GO

-- Preview the first 10 violations cited
SELECT TOP 10 
    violation_id, 
    inspection_id, 
    violation_code, 
    violation_description, 
    severity_tier, 
    inspector_comment
FROM raw_violations;
```

#### Quick Business Insight: Top 10 Facilities with Highest Violations:
```sql
USE FoodInspectionDB;
GO

SELECT TOP 10 
    i.dba_name,
    i.facility_type,
    COUNT(v.violation_id) AS total_violations_cited
FROM raw_inspections i
JOIN raw_violations v ON i.inspection_id = v.inspection_id
GROUP BY i.dba_name, i.facility_type
ORDER BY total_violations_cited DESC;
```

---

## 📁 Project File Structure

| File / Folder | Purpose |
| :--- | :--- |
| **`scripts/step1_api_to_sqlserver.py`** | **Step 1 standalone script:** Connects to the API in `API.txt` and inserts data directly into SQL Server. Beginner-friendly and well-commented. |
| **`notebooks/Step2_Data_Cleaning_and_Star_Schema.ipynb`** | **Step 2 Python Notebook:** Interactive Jupyter Notebook for cleaning, normalizing, and transforming data into the Star Schema in SQL Server. |
| **`docs/`** | Handover specifications and comprehensive engineering report documents. |
| **`API.txt`** | Contains the exact City of Chicago API endpoint URL. |
| **`config.py`** | Easy settings file to configure database name, server, and download limits. |
| **`main.py`** | Runs the full pipeline end-to-end (ETL, dimensional modeling, and analytics). |
| **`database/`** | Contains SQL Server connection handling (`connection.py`) and full Star Schema DDL (`schema.sql`). |
| **`pipeline/`** | Modular ETL scripts (`extractor.py`, `transformer.py`, `loader.py`). |
| **`analytics/`** | Contains pre-written SQL queries (`queries.sql`) and a Python runner (`run_analytics.py`) answering the core business questions. |
| **`requirements.txt`** | Python dependencies (includes `pyodbc`, `requests`, `pandas`, `SQLAlchemy`, `ipykernel`). |

---

## 📓 Running Step 2 (Python Notebook)

You can open and run **`notebooks/Step2_Data_Cleaning_and_Star_Schema.ipynb`** in VS Code or Jupyter:

1. Open VS Code in this folder.
2. Open `notebooks/Step2_Data_Cleaning_and_Star_Schema.ipynb`.
3. In the top right corner, select the Python kernel (`.venv`).
4. Click **Run All** (or run cells step-by-step).
5. Watch each cell clean the data, validate coordinates, standardize facility types, and populate the Star Schema tables in Microsoft SQL Server!

---

## 🔬 Step 3: Feature Engineering & Risk Marts

To compute inspection recency gaps, recidivism, chronic repeat offenders, and neighborhood hotspot scores, run:

```bash
python scripts/run_feature_engineering.py
```

### What This Adds to SQL Server:
1. **`analytics_establishment_risk_mart`**: Materialized table computing:
   - `days_since_prior_inspection`: Days elapsed between consecutive audits (via `LAG()`).
   - `is_consecutive_failure`: Flags instances where an establishment failed two inspections in a row.
   - `cumulative_prior_failures`: Historical failures tally for each business.
   - `rolling_3_prior_failure_rate`: Moving average failure rate over the 3 prior inspections.
   - `is_chronic_offender`: Flags establishments with repeat failures.
2. **`vw_overdue_inspections`**: Live view of establishments exceeding CDPH inspection timeframes (Risk 1 > 365 days, Risk 2 > 730 days).
3. **`vw_geospatial_hotspot_scores`**: Composite 0-100 Hotspot Risk Index for all Chicago zip codes.

### Sample SSMS Queries for Step 3:

```sql
USE FoodInspectionDB;
GO

-- 1. View Top Chronic Repeat Offenders
SELECT TOP 10 
    license_number, 
    dba_name, 
    risk_level, 
    cumulative_prior_failures, 
    rolling_3_prior_failure_rate 
FROM analytics_establishment_risk_mart 
WHERE is_chronic_offender = 1 
ORDER BY cumulative_prior_failures DESC;

-- 2. View Top 10 High-Risk Hotspot Zip Codes
SELECT TOP 10 
    zip_code, 
    composite_hotspot_score, 
    hotspot_tier, 
    failure_rate_pct, 
    priority_violations_per_inspection 
FROM vw_geospatial_hotspot_scores 
ORDER BY composite_hotspot_score DESC;

-- 3. Check Overdue Facilities
SELECT TOP 10 
    license_number, 
    dba_name, 
    risk_level, 
    days_since_last_inspection, 
    inspection_mandate_days, 
    overdue_status 
FROM vw_overdue_inspections 
ORDER BY days_since_last_inspection DESC;
```

---

## ⚙️ Configuration & Customization
If you want to adjust the number of records downloaded or change the server name:
- Open [config.py](file:///D:/Christ/Proj/6.%20Food%20Safty%20Inspection/config.py) or [step1_api_to_sqlserver.py](file:///D:/Christ/Proj/6.%20Food%20Safty%20Inspection/step1_api_to_sqlserver.py)
- Change `TOTAL_RECORDS_TO_FETCH = 5000` to any number (or set `RECORD_LIMIT = None` in `config.py` to fetch all 300k+ records).

