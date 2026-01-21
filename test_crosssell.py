"""Test cross-sell gap injection specifically."""
import sys
sys.path.insert(0, ".")

from data.database import get_connection, init_database
from data.generator import FMCGDataGenerator  
from data.seed_data import AnomalyInjector

# Setup
conn = get_connection()
init_database(conn)

# Generate minimal data
gen = FMCGDataGenerator(conn)
gen.generate_all()

# Check what categories retailers are buying
print("\n=== RETAILER CATEGORY ANALYSIS ===")
result = conn.execute("""
    SELECT r.retailer_id, p.category, COUNT(*) as cnt
    FROM retailers r
    JOIN transactions t ON r.retailer_id = t.retailer_id
    JOIN products p ON t.sku_id = p.sku_id
    WHERE r.lifecycle_status = 'ACTIVE'
    GROUP BY r.retailer_id, p.category
    ORDER BY r.retailer_id, cnt DESC
    LIMIT 20
""").fetchall()

for row in result:
    print(f"  {row[0]}: {row[1]} ({row[2]} txns)")

# Check specific affinity pair
print("\n=== CARBONATED BEVERAGES + SALTY SNACKS ===")
result = conn.execute("""
    WITH retailer_cats AS (
        SELECT DISTINCT r.retailer_id, p.category
        FROM retailers r
        JOIN transactions t ON r.retailer_id = t.retailer_id
        JOIN products p ON t.sku_id = p.sku_id
        WHERE r.lifecycle_status = 'ACTIVE'
    )
    SELECT 
        COUNT(DISTINCT CASE WHEN category = 'Carbonated Beverages' THEN retailer_id END) as has_beverages,
        COUNT(DISTINCT CASE WHEN category = 'Salty Snacks' THEN retailer_id END) as has_snacks,
        (SELECT COUNT(DISTINCT a.retailer_id) 
         FROM retailer_cats a 
         JOIN retailer_cats b ON a.retailer_id = b.retailer_id
         WHERE a.category = 'Carbonated Beverages' 
           AND b.category = 'Salty Snacks') as has_both
    FROM retailer_cats
""").fetchone()

print(f"  Retailers with Carbonated Beverages: {result[0]}")
print(f"  Retailers with Salty Snacks: {result[1]}")
print(f"  Retailers with BOTH: {result[2]}")

# Now inject anomalies
print("\n=== INJECTING ANOMALIES ===")
inj = AnomalyInjector(conn)
gt = inj.inject_all()

print(f"\nCross-sell gaps created: {len(gt['cross_sell_gaps'])}")
for gap in gt['cross_sell_gaps'][:5]:
    print(f"  {gap['retailer_id']}: {gap['buys_category']} -> missing {gap['missing_category']}")

conn.close()
print("\nDone!")
