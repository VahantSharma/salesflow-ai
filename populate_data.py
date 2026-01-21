"""
Master Data Population Script

This is the ONE script to run for complete Phase 1 data setup:
1. Initialize database schema
2. Generate baseline data (retailers, products, transactions, visits)
3. Inject anomalies (churn, cross-sell gaps, stock-out)
4. Run validation queries
5. Print summary statistics
================================================================================
PHASE 1 DATA CONTRACT - DO NOT MODIFY WITHOUT REASON
================================================================================
After successful validation, this data is FROZEN for Phase 2 development.
Changes here affect ALL downstream AI agent behavior.

Semantic Rules:
- Agents MUST consume SQL views (v_churn_candidates, etc.) as truth
- Agents MUST NOT re-derive churn/cross-sell logic in Python
- All analytics are relative to execution date (CURRENT_DATE in views)
- txn_id represents order-line (not order) - line frequency = engagement proxy

Ground Truth:
- Churn retailers: Known via ground_truth table (anomaly_type='churn')
- Cross-sell gaps: Known via ground_truth table (anomaly_type='cross_sell_gap')
- Stock-outs: Known via ground_truth table (anomaly_type='stock_out')
================================================================================
Usage:
    python populate_data.py

After running, you should be able to answer these questions with SQL:
1. "Show me a retailer slowly disengaging"
2. "Show me a cross-sell gap opportunity"
3. "Why is Bronze tier churn deprioritized?"
4. "What's the stock-out situation?"
5. "Who are the ground truth anomalies?"
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.database import get_connection, init_database, get_table_counts, verify_schema
from data.generator import FMCGDataGenerator
from data.seed_data import AnomalyInjector, get_ground_truth
from config.settings import settings


def run_validation_queries(conn):
    """Run validation queries to verify data quality."""
    print("\n" + "=" * 60)
    print("VALIDATION QUERIES")
    print("=" * 60)
    
    # 1. Tier Distribution
    print("\n[1] Retailer Tier Distribution:")
    result = conn.execute("""
        SELECT tier, lifecycle_status, COUNT(*) as count
        FROM retailers
        GROUP BY tier, lifecycle_status
        ORDER BY tier, lifecycle_status
    """).fetchdf()
    print(result.to_string(index=False))
    
    # 2. Category Transaction Distribution
    print("\n[2] Top Categories by Transaction Count:")
    result = conn.execute("""
        SELECT p.category, COUNT(*) as txn_count, 
               SUM(t.total_value) as total_revenue
        FROM transactions t
        JOIN products p ON t.sku_id = p.sku_id
        GROUP BY p.category
        ORDER BY txn_count DESC
        LIMIT 5
    """).fetchdf()
    print(result.to_string(index=False))
    
    # 3. Churn Candidates (from our view)
    print("\n[3] Churn Candidates (Gold+Silver with recent decline):")
    result = conn.execute("""
        SELECT retailer_id, tier, orders_last_14d, orders_prior_14d,
               days_since_order, last_order_date
        FROM v_churn_candidates
        ORDER BY days_since_order DESC
        LIMIT 10
    """).fetchdf()
    print(result.to_string(index=False))
    
    # 4. Ground Truth Summary
    print("\n[4] Ground Truth Anomalies:")
    result = conn.execute("""
        SELECT anomaly_type, COUNT(*) as count
        FROM ground_truth
        GROUP BY anomaly_type
    """).fetchdf()
    print(result.to_string(index=False))
    
    # 5. Cross-sell Gap Verification
    print("\n[5] Sample Cross-Sell Gaps (from ground truth):")
    result = conn.execute("""
        SELECT details
        FROM ground_truth
        WHERE anomaly_type = 'cross_sell_gap'
        LIMIT 3
    """).fetchall()
    for row in result:
        import json
        details = json.loads(row[0])
        print(f"  - Retailer {details['retailer_id']}: Buys {details['buys_category']}, Missing {details['missing_category']}")
    
    # 6. Weekly Transaction Trend (to see if weekend dips exist)
    print("\n[6] Transactions by Day of Week:")
    result = conn.execute("""
        SELECT 
            CASE EXTRACT(DOW FROM transaction_date)
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                WHEN 6 THEN 'Saturday'
            END as day_name,
            COUNT(*) as txn_count
        FROM transactions
        GROUP BY EXTRACT(DOW FROM transaction_date)
        ORDER BY EXTRACT(DOW FROM transaction_date)
    """).fetchdf()
    print(result.to_string(index=False))
    
    # 7. Stock-out Verification
    print("\n[7] Stock-Out Events:")
    result = conn.execute("""
        SELECT details
        FROM ground_truth
        WHERE anomaly_type = 'stock_out'
    """).fetchall()
    for row in result:
        import json
        details = json.loads(row[0])
        print(f"  - SKU: {details['sku_name']}")
        print(f"    Beat: {details['beat_id']}")
        print(f"    Period: {details['start_date']} to {details['end_date']}")
        print(f"    Transactions removed: {details['transactions_removed']}")


def main():
    """Main entry point for data population."""
    print("=" * 60)
    print("SALESFLOW AI - DATA POPULATION")
    print(f"Random Seed: {settings.RANDOM_SEED}")
    print(f"Retailers: {settings.NUM_RETAILERS}")
    print(f"Days of History: {settings.DAYS_OF_HISTORY}")
    print("=" * 60)
    
    # Step 1: Get connection and initialize schema
    print("\n[STEP 1] Initializing database...")
    conn = get_connection()
    init_database(conn)
    
    # Verify schema
    if not verify_schema(conn):
        print("ERROR: Schema verification failed!")
        sys.exit(1)
    
    # Step 2: Generate baseline data
    print("\n[STEP 2] Generating baseline data...")
    generator = FMCGDataGenerator(conn)
    counts = generator.generate_all()
    
    # Step 3: Inject anomalies
    print("\n[STEP 3] Injecting anomalies...")
    injector = AnomalyInjector(conn)
    ground_truth = injector.inject_all()
    
    # Step 4: Final table counts
    print("\n[STEP 4] Final Table Counts:")
    final_counts = get_table_counts(conn)
    for table, count in final_counts.items():
        print(f"  {table}: {count:,}")
    
    # Step 5: Run validation queries
    run_validation_queries(conn)
    
    # Final Summary
    print("\n" + "=" * 60)
    print("PHASE 1 DATA POPULATION COMPLETE")
    print("=" * 60)
    print("\nGround Truth Summary:")
    print(f"  - Churn retailers: {len(ground_truth['churn_retailers'])}")
    print(f"  - Cross-sell gaps: {len(ground_truth['cross_sell_gaps'])}")
    print(f"  - Stock-out events: {len(ground_truth['stock_out_events'])}")
    
    print("\n✓ Data is ready for AI agent development (Phase 2)")
    print("✓ Run validation queries anytime to verify data integrity")
    print("✓ Ground truth stored in 'ground_truth' table for accuracy checks")
    
    conn.close()


if __name__ == "__main__":
    main()
