"""
Data Transformer Module
========================
Cleans, normalizes, and prepares raw Chicago food inspection records
into structured Star Schema datasets (Dimensions and Fact tables).
"""

import re
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd

# Regular expression to extract structured violation codes, descriptions, and comments
VIOLATION_REGEX = re.compile(
    r"(?P<code>\d+)\.\s*(?P<desc>[^-]+?)\s*-\s*Comments:\s*(?P<comment>.*?)(?=(\s*\|\s*\d+\.|$))",
    re.DOTALL
)

# Fallback regex for violations that do not include the standard '- Comments:' separator
VIOLATION_FALLBACK_REGEX = re.compile(
    r"(?P<code>\d+)\.\s*(?P<desc>[^|]+)",
    re.DOTALL
)

def clean_text(text: Optional[str]) -> str:
    """Trim whitespace, collapse multiple spaces, and convert to uppercase."""
    if not text or pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text).strip()).upper()

def standardize_facility_type(raw_type: Optional[str]) -> str:
    """Classifies raw facility types into standardized analytical buckets."""
    if not raw_type or pd.isna(raw_type):
        return "Other / General Food Service"
    
    val = clean_text(raw_type)
    if "RESTAURANT" in val:
        return "Restaurant"
    elif "GROCERY" in val or "SUPERMARKET" in val:
        return "Grocery Store"
    elif any(k in val for k in ["SCHOOL", "DAYCARE", "CHILD", "HEAD START"]):
        return "School / Daycare"
    elif "BAKERY" in val:
        return "Bakery"
    elif "MOBILE" in val or "FOOD TRUCK" in val or "CART" in val:
        return "Mobile Food Vendor"
    elif any(k in val for k in ["LIQUOR", "TAVERN", "BAR", "LOUNGE", "PUB", "BREW"]):
        return "Bar / Tavern"
    elif "WHOLESALE" in val or "DISTRIBUTOR" in val or "COMMISSARY" in val:
        return "Wholesale / Distribution"
    elif any(k in val for k in ["HOSPITAL", "NURSING", "HEALTH", "LONG TERM"]):
        return "Healthcare Facility"
    elif "SPECIAL EVENT" in val or "POPUP" in val or "POPUPS" in val:
        return "Pop-up / Special Event"
    else:
        return "Other / General Food Service"

def standardize_inspection_type(raw_type: Optional[str]) -> str:
    """Standardizes noisy inspection type strings into 7 clean categories."""
    if not raw_type or pd.isna(raw_type):
        return "Other Administrative"
    
    val = clean_text(raw_type)
    if "CANVASS" in val and "RE-INSPECTION" in val:
        return "Canvass Re-Inspection"
    elif "CANVASS" in val:
        return "Routine Canvass"
    elif "COMPLAINT" in val and "RE-INSPECTION" in val:
        return "Complaint Re-Inspection"
    elif "COMPLAINT" in val:
        return "Complaint"
    elif "LICENSE" in val:
        return "License Initial / Renewal"
    elif "FOOD POISONING" in val or "SUSPECT" in val:
        return "Suspected Food Poisoning"
    else:
        return "Other Administrative"

def standardize_risk(raw_risk: Optional[str]) -> str:
    """Standardizes risk string into High, Medium, Low, or Unassigned."""
    if not raw_risk or pd.isna(raw_risk):
        return "Unassigned"
    val = str(raw_risk).strip().upper()
    if "1" in val or "HIGH" in val:
        return "High"
    elif "2" in val or "MEDIUM" in val:
        return "Medium"
    elif "3" in val or "LOW" in val:
        return "Low"
    return "Unassigned"

def standardize_results(raw_result: Optional[str]) -> str:
    """Standardizes the final inspection result."""
    if not raw_result or pd.isna(raw_result):
        return "Unknown"
    val = str(raw_result).strip().title()
    if "Pass W/ Conditions" in val:
        return "Pass w/ Conditions"
    elif "Pass" in val:
        return "Pass"
    elif "Fail" in val:
        return "Fail"
    elif "Out Of Business" in val:
        return "Out of Business"
    elif "Business Not Located" in val:
        return "Business Not Located"
    elif "No Entry" in val:
        return "No Entry"
    return val

def parse_violations(inspection_id: int, violations_text: Optional[str]) -> List[Dict[str, Any]]:
    """
    Parses the multi-line violations string into individual structured records.
    Assigns CDPH severity tiers:
        Codes 1-14: Priority (Critical) - Weight 3
        Codes 15-29: Priority Foundation (Serious) - Weight 2
        Codes 30+: Core (Minor) - Weight 1
    """
    if not violations_text or pd.isna(violations_text):
        return []

    parsed_violations = []
    matches = list(VIOLATION_REGEX.finditer(violations_text))

    if matches:
        for m in matches:
            code_num = int(m.group("code").strip())
            desc = m.group("desc").strip().title()
            comment = m.group("comment").strip()

            if 1 <= code_num <= 14:
                tier = "Priority (Critical)"
                weight = 3
            elif 15 <= code_num <= 29:
                tier = "Priority Foundation (Serious)"
                weight = 2
            else:
                tier = "Core (Minor)"
                weight = 1

            parsed_violations.append({
                "inspection_id": inspection_id,
                "violation_code": code_num,
                "violation_description": desc[:255],
                "severity_tier": tier,
                "severity_weight": weight,
                "inspector_comment": comment
            })
    else:
        # Fallback: simple delimiter split if comment tags are missing
        for m in VIOLATION_FALLBACK_REGEX.finditer(violations_text):
            try:
                code_num = int(m.group("code").strip())
                desc = m.group("desc").strip().title()
                if 1 <= code_num <= 14:
                    tier = "Priority (Critical)"
                    weight = 3
                elif 15 <= code_num <= 29:
                    tier = "Priority Foundation (Serious)"
                    weight = 2
                else:
                    tier = "Core (Minor)"
                    weight = 1

                parsed_violations.append({
                    "inspection_id": inspection_id,
                    "violation_code": code_num,
                    "violation_description": desc[:255],
                    "severity_tier": tier,
                    "severity_weight": weight,
                    "inspector_comment": ""
                })
            except Exception:
                continue

    return parsed_violations

def clean_zip_code(zip_raw: Any) -> Optional[str]:
    """Extracts valid 5-digit zip code."""
    if not zip_raw or pd.isna(zip_raw):
        return None
    match = re.search(r"\b(\d{5})\b", str(zip_raw))
    return match.group(1) if match else None

def validate_coordinates(lat_val: Any, lon_val: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Validates latitude and longitude within the City of Chicago bounding box:
        Latitude:  41.60 to 42.10
        Longitude: -87.95 to -87.50
    Returns (None, None) if coordinates are invalid or outside Chicago.
    """
    try:
        lat = float(lat_val)
        lon = float(lon_val)
        if 41.60 <= lat <= 42.10 and -87.95 <= lon <= -87.50:
            return round(lat, 6), round(lon, 6)
    except (ValueError, TypeError):
        pass
    return None, None

def transform_raw_records(raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Main transformation pipeline. Transforms list of raw API records into
    structured dictionaries ready for Star Schema loading.
    
    Returns a dictionary with keys:
        - 'dates': List of unique dim_date rows
        - 'facility_types': List of unique dim_facility_type rows
        - 'geographies': List of unique dim_geography rows
        - 'establishments': List of unique dim_establishment rows
        - 'inspections': List of fact_inspections rows
        - 'violations': List of fact_violations rows
    """
    print(f"[*] Transforming {len(raw_records)} raw records...")

    dim_dates = {}
    dim_facility_types = {}
    dim_geographies = {}
    dim_establishments = {}
    fact_inspections = []
    fact_violations = []

    for r in raw_records:
        # 1. Inspection ID
        raw_id = r.get("inspection_id")
        if not raw_id:
            continue
        try:
            inspection_id = int(raw_id)
        except ValueError:
            continue

        # 2. Date Dimension
        raw_date = r.get("inspection_date")
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.strptime(raw_date[:10], "%Y-%m-%d")
        else:
            dt = datetime(2000, 1, 1)

        date_key = int(dt.strftime("%Y%m%d"))
        full_date = dt.date()
        if date_key not in dim_dates:
            dim_dates[date_key] = {
                "date_key": date_key,
                "full_date": full_date,
                "year": dt.year,
                "quarter": (dt.month - 1) // 3 + 1,
                "month": dt.month,
                "month_name": dt.strftime("%B"),
                "day_of_week": dt.isoweekday(),
                "day_name": dt.strftime("%A"),
                "is_weekend": 1 if dt.isoweekday() in [6, 7] else 0
            }

        # 3. Facility Type Dimension
        raw_fac = clean_text(r.get("facility_type")) or "UNKNOWN"
        if raw_fac not in dim_facility_types:
            dim_facility_types[raw_fac] = {
                "raw_name": raw_fac[:150],
                "standardized_category": standardize_facility_type(raw_fac)
            }

        # 4. Geography Dimension
        address = clean_text(r.get("address")) or "UNKNOWN ADDRESS"
        zip_code = clean_zip_code(r.get("zip"))
        lat, lon = validate_coordinates(r.get("latitude"), r.get("longitude"))
        geo_key = (address, zip_code)
        if geo_key not in dim_geographies:
            dim_geographies[geo_key] = {
                "street_address": address[:255],
                "city": "CHICAGO",
                "state": "IL",
                "zip_code": zip_code,
                "latitude": lat,
                "longitude": lon
            }

        # 5. Establishment Dimension
        dba_name = clean_text(r.get("dba_name")) or "UNKNOWN"
        aka_name = clean_text(r.get("aka_name")) or dba_name
        try:
            license_num = int(r.get("license_") or 0)
        except (ValueError, TypeError):
            license_num = 0
        risk_level = standardize_risk(r.get("risk"))

        estab_key = (license_num, dba_name)
        if estab_key not in dim_establishments:
            dim_establishments[estab_key] = {
                "license_number": license_num,
                "dba_name": dba_name[:255],
                "aka_name": aka_name[:255],
                "risk_level": risk_level,
                "first_inspection_date": full_date,
                "last_inspection_date": full_date
            }
        else:
            # Update date range
            if full_date < dim_establishments[estab_key]["first_inspection_date"]:
                dim_establishments[estab_key]["first_inspection_date"] = full_date
            if full_date > dim_establishments[estab_key]["last_inspection_date"]:
                dim_establishments[estab_key]["last_inspection_date"] = full_date

        # 6. Violations Parsing
        raw_violations_text = r.get("violations")
        parsed_v = parse_violations(inspection_id, raw_violations_text)
        fact_violations.extend(parsed_v)

        # Count violations by tier
        priority_cnt = sum(1 for v in parsed_v if v["severity_tier"] == "Priority (Critical)")
        serious_cnt = sum(1 for v in parsed_v if v["severity_tier"] == "Priority Foundation (Serious)")
        core_cnt = sum(1 for v in parsed_v if v["severity_tier"] == "Core (Minor)")
        total_cnt = len(parsed_v)

        # 7. Inspection Outcomes & Attributes
        results = standardize_results(r.get("results"))
        is_failure = 1 if results == "Fail" else 0
        inspection_type = standardize_inspection_type(r.get("inspection_type"))

        fact_inspections.append({
            "inspection_id": inspection_id,
            "date_key": date_key,
            "license_number": license_num,
            "dba_name": dba_name,
            "street_address": address,
            "zip_code": zip_code,
            "raw_facility_name": raw_fac,
            "inspection_type": inspection_type,
            "results": results,
            "is_failure": is_failure,
            "priority_violations_count": priority_cnt,
            "serious_violations_count": serious_cnt,
            "core_violations_count": core_cnt,
            "total_violations_count": total_cnt
        })

    print(f"[+] Transformation finished:")
    print(f"    - Unique Dates: {len(dim_dates)}")
    print(f"    - Unique Facility Types: {len(dim_facility_types)}")
    print(f"    - Unique Geographies: {len(dim_geographies)}")
    print(f"    - Unique Establishments: {len(dim_establishments)}")
    print(f"    - Inspections: {len(fact_inspections)}")
    print(f"    - Parsed Violations: {len(fact_violations)}")

    return {
        "dates": list(dim_dates.values()),
        "facility_types": list(dim_facility_types.values()),
        "geographies": list(dim_geographies.values()),
        "establishments": list(dim_establishments.values()),
        "inspections": fact_inspections,
        "violations": fact_violations
    }
