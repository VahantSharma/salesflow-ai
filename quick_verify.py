"""Quick verification that Phase 1 data is correctly populated."""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.database import get_connection, init_database, get_table_counts
from data.generator import FMCGDataGenerator
from data.seed_data import AnomalyInjector, get_ground_truth

# Setup
print("Setting up...")
conn = get_connection()
init_database(conn)

# Generate
print("Generating data...")
gen = FMCGDataGenerator(conn)
gen.generate_all()

# Anomalies
print("\nInjecting anomalies...")
inj = AnomalyInjector(conn)
gt = inj.inject_all()

# Counts
print("\n=== FINAL COUNTS ===")
counts = get_table_counts(conn)
for t, c in counts.items():
    print(f"  {t}: {c:,}")

# Ground truth
print("\n=== GROUND TRUTH ===")
print(f"  Churn retailers: {len(gt['churn_retailers'])}")
print(f"  Cross-sell gaps: {len(gt['cross_sell_gaps'])}")
print(f"  Stock-out events: {len(gt['stock_out_events'])}")

# Quick queries
print("\n=== VALIDATION ===")

# 1. Churn check
print("\n1. Sample churn retailer:")
if gt['churn_retailers']:
    rid = gt['churn_retailers'][0]['retailer_id']
    result = conn.execute(f"""
        SELECT transaction_date, COUNT(*) as txn_count
        FROM transactions
        WHERE retailer_id = '{rid}'
        GROUP BY transaction_date
        ORDER BY transaction_date DESC
        LIMIT 5
    """).fetchall()
    for row in result:
        print(f"   {row[0]}: {row[1]} transactions")

# 2. Category distribution  
print("\n2. Category transaction counts:")
result = conn.execute("""
    SELECT p.category, COUNT(*) as cnt
    FROM transactions t JOIN products p ON t.sku_id = p.sku_id
    GROUP BY p.category ORDER BY cnt DESC LIMIT 3
""").fetchall()
for row in result:
    print(f"   {row[0]}: {row[1]}")

# 3. View test
print("\n3. Churn candidates view:")
result = conn.execute("""
    SELECT COUNT(*) FROM v_churn_candidates
""").fetchone()
print(f"   {result[0]} retailers in churn candidates view")

conn.close()
print("\n✓ Phase 1 verification complete!")
