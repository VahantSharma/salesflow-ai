"""
Database Connection and Initialization

Responsibility:
- Provide DuckDB connection management
- Initialize schema from schema.sql
- Handle connection lifecycle
- Support both file-based and in-memory databases

Design Decisions:
- Use DuckDB for zero-setup OLAP capability
- In-memory for development/testing, file for persistence
- Schema is idempotent (DROP IF EXISTS + CREATE)

Usage:
    from data.database import get_connection, init_database
    
    conn = get_connection()  # In-memory by default
    init_database(conn)       # Creates all tables
"""

import duckdb
from pathlib import Path
from typing import Optional
import os


# Path to schema file
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """
    Get a DuckDB connection.
    
    Args:
        db_path: Path to database file. If None, uses in-memory database.
                 Use ":memory:" explicitly for in-memory.
                 
    Returns:
        DuckDB connection object
        
    Example:
        conn = get_connection()  # In-memory
        conn = get_connection("salesflow.duckdb")  # File-based
    """
    if db_path is None:
        db_path = ":memory:"
    
    conn = duckdb.connect(db_path)
    return conn


def init_database(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Initialize database schema from schema.sql.
    
    This is idempotent - safe to call multiple times.
    Drops existing tables and recreates them.
    
    Args:
        conn: DuckDB connection
        
    Raises:
        FileNotFoundError: If schema.sql doesn't exist
        duckdb.Error: If SQL execution fails
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
    
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    
    # Execute the entire schema file
    # DuckDB handles multiple statements
    conn.execute(schema_sql)
    
    print(f"✓ Database initialized from {SCHEMA_PATH.name}")


def get_table_counts(conn: duckdb.DuckDBPyConnection) -> dict:
    """
    Get row counts for all tables.
    
    Useful for validation after data generation.
    
    Args:
        conn: DuckDB connection
        
    Returns:
        Dict mapping table name to row count
    """
    tables = ["retailers", "products", "transactions", "visits", "category_affinities"]
    counts = {}
    
    for table in tables:
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = result[0] if result else 0
        except duckdb.CatalogException:
            counts[table] = None  # Table doesn't exist
    
    return counts


def verify_schema(conn: duckdb.DuckDBPyConnection) -> bool:
    """
    Verify all expected tables and views exist.
    
    Args:
        conn: DuckDB connection
        
    Returns:
        True if schema is complete, False otherwise
    """
    expected_tables = ["retailers", "products", "transactions", "visits", "category_affinities"]
    expected_views = ["v_retailer_performance", "v_retailer_categories", "v_churn_candidates"]
    
    # Check tables
    for table in expected_tables:
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except duckdb.CatalogException:
            print(f"✗ Missing table: {table}")
            return False
    
    # Check views
    for view in expected_views:
        try:
            conn.execute(f"SELECT 1 FROM {view} LIMIT 1")
        except duckdb.CatalogException:
            print(f"✗ Missing view: {view}")
            return False
    
    return True


def execute_query(conn: duckdb.DuckDBPyConnection, sql: str):
    """
    Execute a query and return results as pandas DataFrame.
    
    Args:
        conn: DuckDB connection
        sql: SQL query string
        
    Returns:
        pandas DataFrame with results
    """
    return conn.execute(sql).fetchdf()


# Convenience function for quick testing
def create_test_database() -> duckdb.DuckDBPyConnection:
    """
    Create an in-memory database with schema initialized.
    
    Useful for testing and development.
    
    Returns:
        Initialized DuckDB connection
    """
    conn = get_connection()
    init_database(conn)
    return conn


if __name__ == "__main__":
    # Quick test
    print("Testing database module...")
    conn = create_test_database()
    
    counts = get_table_counts(conn)
    print(f"Table counts: {counts}")
    
    if verify_schema(conn):
        print("✓ Schema verification passed")
    else:
        print("✗ Schema verification failed")
    
    conn.close()
