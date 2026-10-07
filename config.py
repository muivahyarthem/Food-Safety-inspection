"""
Project Configuration File
This file contains the configuration settings for the Food Safety Inspection pipeline.
Can adjust th database connection details and API download limits.
"""

import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

# 1. API Configuration
# Reads endpoint from API.txt or defaults to Chicago Open Data API
API_TXT_PATH = BASE_DIR / "API.txt"
if API_TXT_PATH.exists():
    with open(API_TXT_PATH, "r", encoding="utf-8") as f:
        API_URL = f.read().strip()
else:
    API_URL = "https://data.cityofchicago.org/api/v3/views/4ijn-s7e5/query.json"

# Ingestion settings:
# BATCH_SIZE: Number of rows fetched per API request
BATCH_SIZE = 2500

# RECORD_LIMIT: Maximum records to download for initial loading and testing.
# Set to 10000 by default for quick and reliable execution.
# To download ALL records (300k+), set RECORD_LIMIT = None.
RECORD_LIMIT = 10000


# 2. Microsoft SQL Server Database Configuration
# These settings connect to your local Microsoft SQL Server instance (used in SSMS).
DB_SERVER = r"localhost\SQLEXPRESS"   # Common default instance; change to 'localhost' or '.\SQLEXPRESS' if needed
DB_NAME = "FoodInspectionDB"          # The database name where tables will be created
DB_TRUSTED_CONNECTION = "yes"         # "yes" uses Windows Authentication (SSMS standard)
DB_TRUST_SERVER_CERTIFICATE = "yes"   # Required for newer ODBC drivers (Driver 18)

# Optional: If using SQL Server Authentication (username/password) instead of Windows Auth:
DB_USER = None       # e.g., "sa"
DB_PASSWORD = None   # e.g., "YourStrongPassword!"
