"""
Database Connection Manager
Handles connecting to Microsoft SQL Server using pyodbc.
Includes automatic ODBC driver detection and database initialization.
"""

import pyodbc
from pathlib import Path
import config

def get_installed_driver() -> str:
    """Find the best available SQL Server ODBC driver installed on this machine."""
    available = pyodbc.drivers()
    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server"
    ]
    for drv in preferred_drivers:
        if drv in available:
            return drv
    # Default fallback
    return "ODBC Driver 18 for SQL Server"

def get_connection_string(database: str = None) -> str:
    """Constructs the ODBC connection string for Microsoft SQL Server."""
    driver = get_installed_driver()
    db = database or config.DB_NAME
    
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={config.DB_SERVER}",
        f"DATABASE={db}"
    ]
    
    if config.DB_USER and config.DB_PASSWORD:
        parts.append(f"UID={config.DB_USER}")
        parts.append(f"PWD={config.DB_PASSWORD}")
    else:
        parts.append(f"Trusted_Connection={config.DB_TRUSTED_CONNECTION}")
    
    # Driver 18 requires TrustServerCertificate for self-signed certificates
    if "18" in driver:
        parts.append(f"TrustServerCertificate={config.DB_TRUST_SERVER_CERTIFICATE}")
        
    return ";".join(parts) + ";"

def get_connection(database: str = None):
    """Returns an active pyodbc connection to SQL Server."""
    conn_str = get_connection_string(database)
    return pyodbc.connect(conn_str)

def initialize_database():
    """
    Ensures that the target database (e.g., FoodInspectionDB) exists in SQL Server,
    then executes schema.sql to create all tables, indexes, and views.
    """
    print(f"[*] Checking SQL Server connection on '{config.DB_SERVER}'...")
    
    # 1. Connect to 'master' database with autocommit to verify or create our database
    master_conn = pyodbc.connect(get_connection_string(database="master"), autocommit=True)
    cursor = master_conn.cursor()
    
    cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{config.DB_NAME}'")
    exists = cursor.fetchone()
    if not exists:
        print(f"[*] Creating database '{config.DB_NAME}' in SQL Server...")
        cursor.execute(f"CREATE DATABASE [{config.DB_NAME}];")
        print(f"[+] Database '{config.DB_NAME}' created successfully.")
    else:
        print(f"[+] Database '{config.DB_NAME}' already exists.")
    master_conn.close()

    # 2. Connect to the project database and execute schema.sql
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    if schema_path.exists():
        print("[*] Applying schema (tables, views, indexes)...")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        
        # Split script by 'GO' commands (standard T-SQL batch separator)
        batches = [b.strip() for b in sql_script.split("\nGO") if b.strip()]
        
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        for batch in batches:
            if batch:
                cur.execute(batch)
        conn.close()
        print("[+] Schema successfully applied!")
    else:
        print("[!] schema.sql not found; skipping schema creation.")
