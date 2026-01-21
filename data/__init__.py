"""
Data Package

This package contains all data-related modules for SalesFlow AI.

Modules:
- generator: Synthetic data generation for retailers, products, transactions
- seed_data: Anomaly injection (churn patterns, cross-sell gaps)
- schema.sql: DuckDB schema definition

The data layer is responsible for:
- Creating realistic FMCG distribution data
- Injecting detectable anomalies for AI to discover
- Providing database connectivity

Usage:
    from data.generator import FMCGDataGenerator
    from data.seed_data import inject_anomalies
"""

__all__ = ["generator", "seed_data"]
