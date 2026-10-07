"""
Data Loader Module
==================
Loads cleaned and transformed Star Schema records into Microsoft SQL Server.
Handles surrogate key lookups, deduplication, and fast batch loading.
"""

from typing import Dict, Any, List
import database.connection as db

def load_dates(cursor, dates: List[Dict[str, Any]]):
    """Inserts unique dates into dim_date if they do not already exist."""
    print(f"[*] Loading {len(dates)} dates into dim_date...")
    sql_check = "SELECT date_key FROM dim_date"
    cursor.execute(sql_check)
    existing_keys = {row[0] for row in cursor.fetchall()}

    to_insert = [
        (
            d["date_key"],
            d["full_date"],
            d["year"],
            d["quarter"],
            d["month"],
            d["month_name"],
            d["day_of_week"],
            d["day_name"],
            d["is_weekend"]
        )
        for d in dates if d["date_key"] not in existing_keys
    ]

    if to_insert:
        insert_sql = """
            INSERT INTO dim_date (date_key, full_date, year, quarter, month, month_name, day_of_week, day_name, is_weekend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.fast_executemany = True
        cursor.executemany(insert_sql, to_insert)
        print(f"[+] Inserted {len(to_insert)} new rows into dim_date.")
    else:
        print("[+] All dates already present in dim_date.")

def load_facility_types(cursor, facility_types: List[Dict[str, Any]]) -> Dict[str, int]:
    """Inserts unique facility types into dim_facility_type and returns a lookup dictionary."""
    print(f"[*] Loading {len(facility_types)} facility types into dim_facility_type...")
    cursor.execute("SELECT raw_name, facility_type_key FROM dim_facility_type")
    lookup = {row[0]: row[1] for row in cursor.fetchall()}

    to_insert = [
        (f["raw_name"], f["standardized_category"])
        for f in facility_types if f["raw_name"] not in lookup
    ]

    if to_insert:
        insert_sql = "INSERT INTO dim_facility_type (raw_name, standardized_category) VALUES (?, ?)"
        cursor.fast_executemany = True
        cursor.executemany(insert_sql, to_insert)
        print(f"[+] Inserted {len(to_insert)} new facility types.")

        # Refresh lookup
        cursor.execute("SELECT raw_name, facility_type_key FROM dim_facility_type")
        lookup = {row[0]: row[1] for row in cursor.fetchall()}
    else:
        print("[+] All facility types already present.")

    return lookup

def load_geographies(cursor, geographies: List[Dict[str, Any]]) -> Dict[tuple, int]:
    """Inserts unique geographies into dim_geography and returns a lookup dictionary."""
    print(f"[*] Loading {len(geographies)} geographies into dim_geography...")
    cursor.execute("SELECT street_address, COALESCE(zip_code, ''), geography_key FROM dim_geography")
    lookup = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    to_insert = []
    for g in geographies:
        key = (g["street_address"], g["zip_code"] or "")
        if key not in lookup:
            to_insert.append((
                g["street_address"],
                g["city"],
                g["state"],
                g["zip_code"],
                g["latitude"],
                g["longitude"]
            ))

    if to_insert:
        insert_sql = """
            INSERT INTO dim_geography (street_address, city, state, zip_code, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor.fast_executemany = True
        cursor.executemany(insert_sql, to_insert)
        print(f"[+] Inserted {len(to_insert)} new geography records.")

        cursor.execute("SELECT street_address, COALESCE(zip_code, ''), geography_key FROM dim_geography")
        lookup = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
    else:
        print("[+] All geography records already present.")

    return lookup

def load_establishments(cursor, establishments: List[Dict[str, Any]]) -> Dict[tuple, int]:
    """Inserts unique establishments into dim_establishment and returns a lookup dictionary."""
    print(f"[*] Loading {len(establishments)} establishments into dim_establishment...")
    cursor.execute("SELECT license_number, dba_name, establishment_key FROM dim_establishment")
    lookup = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    to_insert = []
    for e in establishments:
        key = (e["license_number"], e["dba_name"])
        if key not in lookup:
            to_insert.append((
                e["license_number"],
                e["dba_name"],
                e["aka_name"],
                e["risk_level"],
                e["first_inspection_date"],
                e["last_inspection_date"]
            ))

    if to_insert:
        insert_sql = """
            INSERT INTO dim_establishment (license_number, dba_name, aka_name, risk_level, first_inspection_date, last_inspection_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor.fast_executemany = True
        cursor.executemany(insert_sql, to_insert)
        print(f"[+] Inserted {len(to_insert)} new establishments.")

        cursor.execute("SELECT license_number, dba_name, establishment_key FROM dim_establishment")
        lookup = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
    else:
        print("[+] All establishments already present.")

    return lookup

def load_inspections(
    cursor,
    inspections: List[Dict[str, Any]],
    facility_lookup: Dict[str, int],
    geo_lookup: Dict[tuple, int],
    estab_lookup: Dict[tuple, int]
) -> List[int]:
    """Loads inspection records into fact_inspections using mapped surrogate keys."""
    print(f"[*] Loading {len(inspections)} inspections into fact_inspections...")
    cursor.execute("SELECT inspection_id FROM fact_inspections")
    existing_ids = {row[0] for row in cursor.fetchall()}

    to_insert = []
    inserted_ids = []

    for insp in inspections:
        insp_id = insp["inspection_id"]
        if insp_id in existing_ids:
            continue

        estab_key = estab_lookup.get((insp["license_number"], insp["dba_name"]))
        geo_key = geo_lookup.get((insp["street_address"], insp["zip_code"] or ""))
        fac_key = facility_lookup.get(insp["raw_facility_name"])

        to_insert.append((
            insp_id,
            insp["date_key"],
            estab_key,
            geo_key,
            fac_key,
            insp["inspection_type"],
            insp["results"],
            insp["is_failure"],
            insp["priority_violations_count"],
            insp["serious_violations_count"],
            insp["core_violations_count"],
            insp["total_violations_count"],
            None,  # days_since_last_inspection (can be updated or computed via view)
            0      # prior_failures_cumulative
        ))
        inserted_ids.append(insp_id)

    if to_insert:
        insert_sql = """
            INSERT INTO fact_inspections (
                inspection_id, date_key, establishment_key, geography_key, facility_type_key,
                inspection_type, results, is_failure,
                priority_violations_count, serious_violations_count, core_violations_count, total_violations_count,
                days_since_last_inspection, prior_failures_cumulative
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.fast_executemany = True
        cursor.executemany(insert_sql, to_insert)
        print(f"[+] Inserted {len(to_insert)} new inspections into fact_inspections.")
    else:
        print("[+] All inspections are already loaded.")

    return inserted_ids

def load_violations(cursor, violations: List[Dict[str, Any]]):
    """Loads parsed violations into fact_violations."""
    print(f"[*] Loading {len(violations)} violations into fact_violations...")
    if not violations:
        print("[+] No violations to load.")
        return

    # Check existing inspection IDs in fact_inspections to ensure referential integrity
    cursor.execute("SELECT inspection_id FROM fact_inspections")
    valid_inspections = {row[0] for row in cursor.fetchall()}

    # Check which violations have already been inserted to avoid duplicates
    cursor.execute("SELECT DISTINCT inspection_id FROM fact_violations")
    existing_inspections_with_violations = {row[0] for row in cursor.fetchall()}

    to_insert = [
        (
            v["inspection_id"],
            v["violation_code"],
            v["violation_description"],
            v["severity_tier"],
            v["severity_weight"],
            v["inspector_comment"]
        )
        for v in violations
        if v["inspection_id"] in valid_inspections
        and v["inspection_id"] not in existing_inspections_with_violations
    ]

    if to_insert:
        insert_sql = """
            INSERT INTO fact_violations (
                inspection_id, violation_code, violation_description, severity_tier, severity_weight, inspector_comment
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """
        # Batch insert in chunks of 5000 for efficiency
        cursor.fast_executemany = True
        chunk_size = 5000
        for i in range(0, len(to_insert), chunk_size):
            chunk = to_insert[i:i + chunk_size]
            cursor.executemany(insert_sql, chunk)
        print(f"[+] Inserted {len(to_insert)} violations into fact_violations.")
    else:
        print("[+] All violations already loaded or no new inspection records.")

def load_all(transformed_data: Dict[str, Any]):
    """
    Orchestrates the complete data loading sequence into Microsoft SQL Server.
    Ensures dimension dependencies and foreign keys are satisfied.
    """
    print("\n" + "=" * 60)
    print("STARTING DATABASE LOAD TO MICROSOFT SQL SERVER")
    print("=" * 60)

    conn = db.get_connection()
    try:
        cursor = conn.cursor()

        # Step 1: Load Dimensions
        load_dates(cursor, transformed_data["dates"])
        conn.commit()

        facility_lookup = load_facility_types(cursor, transformed_data["facility_types"])
        conn.commit()

        geo_lookup = load_geographies(cursor, transformed_data["geographies"])
        conn.commit()

        estab_lookup = load_establishments(cursor, transformed_data["establishments"])
        conn.commit()

        # Step 2: Load Fact Tables
        load_inspections(cursor, transformed_data["inspections"], facility_lookup, geo_lookup, estab_lookup)
        conn.commit()

        load_violations(cursor, transformed_data["violations"])
        conn.commit()

        print("[+] Database loading successfully completed!")

    except Exception as e:
        conn.rollback()
        print(f"[!] Error during database load: {e}")
        raise e
    finally:
        conn.close()
