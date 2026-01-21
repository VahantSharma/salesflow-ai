"""Minimal test of data pipeline with unbuffered output."""
import sys
sys.stdout.reconfigure(line_buffering=True)  # Force unbuffered output

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data.database import get_connection, init_database, get_table_counts
from data.generator import FMCGDataGenerator
from data.seed_data import AnomalyInjector

print("1. Setting up database...")
conn = get_connection()
init_database(conn)

print("2. Generating data...")
gen = FMCGDataGenerator(conn)
gen.generate_all()

print("\n3. Counts after generation:")
for t, c in get_table_counts(conn).items():
    print(f"   {t}: {c}")

print("\n4. Injecting anomalies...")
inj = AnomalyInjector(conn)
gt = inj.inject_all()

print("\n5. Final Results:")
print(f"   Churn retailers: {len(gt['churn_retailers'])}")
print(f"   Cross-sell gaps: {len(gt['cross_sell_gaps'])}")
print(f"   Stock-out events: {len(gt['stock_out_events'])}")

print("\n6. Sample ground truth:")
if gt['cross_sell_gaps']:
    gap = gt['cross_sell_gaps'][0]
    print(f"   Cross-sell gap: {gap['retailer_id']} buys {gap['buys_category']}, missing {gap['missing_category']}")
else:
    print("   No cross-sell gaps created")

print("\n7. Final counts:")
for t, c in get_table_counts(conn).items():
    print(f"   {t}: {c}")

conn.close()
print("\n✓ Test complete!")
