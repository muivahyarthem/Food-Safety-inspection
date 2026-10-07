"""
Data Extractor Module
=====================
Extracts food inspection records from the City of Chicago API
specified in API.txt (using pagination and error handling).
"""

import time
import requests
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import config

def fetch_inspections(
    total_records: Optional[int] = config.RECORD_LIMIT,
    batch_size: int = config.BATCH_SIZE,
    save_raw_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetches food inspection records from the Chicago API in batches.
    
    Parameters:
        total_records: Total number of records to retrieve (None for all).
        batch_size: Number of records to request per API call.
        save_raw_cache: Whether to save a copy in data/raw for debugging/backup.
        
    Returns:
        List of raw inspection record dictionaries.
    """
    print(f"[*] Starting API Extraction from: {config.API_URL}")
    if total_records:
        print(f"[*] Target record limit: {total_records} (batch size: {batch_size})")
    else:
        print(f"[*] Target record limit: All available records (batch size: {batch_size})")

    all_records: List[Dict[str, Any]] = []
    offset = 0

    while True:
        # Determine how many records to fetch in this batch
        current_limit = batch_size
        if total_records is not None:
            remaining = total_records - len(all_records)
            if remaining <= 0:
                break
            current_limit = min(batch_size, remaining)

        query = f"SELECT * ORDER BY inspection_date DESC, inspection_id DESC LIMIT {current_limit} OFFSET {offset}"
        params = {"query": query}

        print(f"    --> Requesting rows {offset + 1} to {offset + current_limit}...", end=" ", flush=True)

        try:
            response = requests.get(config.API_URL, params=params, timeout=30)
            if response.status_code != 200:
                print(f"\n[!] API Error (Status {response.status_code}): {response.text[:200]}")
                break

            data = response.json()
            if not isinstance(data, list) or len(data) == 0:
                print("No more records returned from API.")
                break

            all_records.extend(data)
            print(f"Received {len(data)} rows. (Total so far: {len(all_records)})")

            if len(data) < current_limit:
                # Less than requested means we reached the end of the dataset
                break

            offset += len(data)
            # Brief pause to respect API rate limits
            time.sleep(0.5)

        except Exception as e:
            print(f"\n[!] Network or extraction error: {e}")
            break

    print(f"[+] Extraction complete! Successfully retrieved {len(all_records)} raw records.")

    # Save raw cache if requested
    if save_raw_cache and len(all_records) > 0:
        raw_dir = config.BASE_DIR / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        cache_file = raw_dir / "inspections_raw.json"
        print(f"[*] Caching raw data to '{cache_file}'...")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(all_records, f)
        print("[+] Raw data cached.")

    return all_records

if __name__ == "__main__":
    records = fetch_inspections(total_records=100)
    print(f"Sample test: fetched {len(records)} records.")
