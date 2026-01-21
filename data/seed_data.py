"""
Anomaly Injection Module

Responsibility:
- Inject KNOWN anomalies into the baseline data
- Create churn patterns (decaying purchase frequency)
- Create cross-sell gaps (missing category pairs)
- Create stock-out patterns (localized product absence)
- Maintain ground truth registry for validation

Design Philosophy:
1. Anomalies must be DETECTABLE but not OBVIOUS
2. Patterns should match what AI agents will look for
3. Ground truth enables validation: we KNOW which retailers are anomalies
4. Realistic noise: not every signal is clean

Anomaly Types:
1. CHURN: Gold/Silver retailers with exponentially decaying purchases
   - Target: 12% of Gold+Silver ACTIVE retailers
   - Pattern: Last 30-60 days show clear decline
   
2. CROSS-SELL GAP: Retailers buying Category A but not Category B
   - Focus: High-affinity pairs (Beverages↔Snacks, Dairy↔Bakery)
   - Target: ~10% of active retailers
   
3. STOCK-OUT: Single SKU missing from single beat for 1-2 weeks
   - Simpler pattern, clear temporal boundary
   - Target: 1 SKU, 1 beat (keep it simple)

IMPORTANT SIDE EFFECT:
- Churn injection DELETES transactions but keeps visits intact
- This creates "visits without orders" which is REALISTIC
- Interpretation: "Sales rep visited but customer didn't buy" (churn signal)
- If asked: "We deliberately preserve visits to reflect sales attempts"

Usage:
    from data.seed_data import AnomalyInjector
    from data.database import get_connection
    
    conn = get_connection()
    injector = AnomalyInjector(conn)
    ground_truth = injector.inject_all()
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Set
import numpy as np
import duckdb

from config.settings import settings


class AnomalyInjector:
    """
    Injects known anomalies into the data for AI to detect.
    
    Maintains ground truth so we can validate AI accuracy.
    """
    
    # High-affinity category pairs (retailers buying A often also want B)
    AFFINITY_PAIRS = [
        ("Carbonated Beverages", "Salty Snacks"),  # Classic combo
        ("Dairy", "Bakery"),                        # Breakfast combo
        ("Confectionery", "Juice"),                 # Kids' favorites
        ("Personal Care", "Home Care"),             # Daily essentials
    ]
    
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        """
        Initialize injector with database connection.
        
        Args:
            conn: DuckDB connection with populated data
        """
        self.conn = conn
        self.reference_date = datetime.now().date()
        
        # Ground truth storage
        self.ground_truth = {
            "churn_retailers": [],
            "cross_sell_gaps": [],
            "stock_out_events": [],
        }
        
        # Set seed for reproducibility
        random.seed(settings.RANDOM_SEED + 1)  # Different seed than generator
        np.random.seed(settings.RANDOM_SEED + 1)
    
    def inject_all(self) -> Dict:
        """
        Inject all anomaly types.
        
        Returns:
            Ground truth dictionary for validation
        """
        print("\n" + "=" * 60)
        print("INJECTING ANOMALIES")
        print("=" * 60)
        
        self._inject_churn_patterns()
        self._inject_cross_sell_gaps()
        self._inject_stock_out()
        
        # Save ground truth to database
        self._save_ground_truth()
        
        print("\n" + "=" * 60)
        print("ANOMALY INJECTION COMPLETE")
        print(f"  Churn retailers: {len(self.ground_truth['churn_retailers'])}")
        print(f"  Cross-sell gaps: {len(self.ground_truth['cross_sell_gaps'])}")
        print(f"  Stock-out events: {len(self.ground_truth['stock_out_events'])}")
        print("=" * 60)
        
        return self.ground_truth
    
    def _inject_churn_patterns(self):
        """
        Create churn patterns for Gold+Silver ACTIVE retailers.
        
        Pattern: Exponentially decaying purchase frequency
        - Week 4+ ago: Normal activity
        - Week 3: 70% of normal
        - Week 2: 40% of normal  
        - Week 1: 10% of normal (almost stopped)
        """
        print("\n[CHURN] Injecting churn patterns...")
        
        # Get Gold+Silver ACTIVE retailers
        eligible = self.conn.execute("""
            SELECT retailer_id, tier
            FROM retailers
            WHERE tier IN ('Gold', 'Silver')
              AND lifecycle_status = 'ACTIVE'
        """).fetchall()
        
        # Select 12% for churn
        num_churn = max(1, int(len(eligible) * 0.12))
        churn_retailers = random.sample(eligible, num_churn)
        
        print(f"  Selected {num_churn} retailers for churn injection")
        
        for retailer_id, tier in churn_retailers:
            # Get their recent transactions
            recent_txns = self.conn.execute("""
                SELECT txn_id, transaction_date
                FROM transactions
                WHERE retailer_id = ?
                  AND transaction_date >= ?
                ORDER BY transaction_date
            """, [retailer_id, self.reference_date - timedelta(days=30)]).fetchall()
            
            if len(recent_txns) < 3:
                continue  # Not enough transactions to create decay pattern
            
            # Delete transactions based on decay pattern
            deleted_count = 0
            for txn_id, txn_date in recent_txns:
                # Handle both date and datetime from DuckDB
                if hasattr(txn_date, 'date'):
                    txn_date = txn_date.date()
                days_ago = (self.reference_date - txn_date).days
                
                # Calculate survival probability based on recency
                if days_ago <= 7:
                    keep_prob = 0.1  # 10% survive in last week
                elif days_ago <= 14:
                    keep_prob = 0.4  # 40% survive in week 2
                elif days_ago <= 21:
                    keep_prob = 0.7  # 70% survive in week 3
                else:
                    keep_prob = 1.0  # Keep older transactions
                
                if random.random() > keep_prob:
                    self.conn.execute("DELETE FROM transactions WHERE txn_id = ?", [txn_id])
                    deleted_count += 1
            
            # Record in ground truth
            self.ground_truth["churn_retailers"].append({
                "retailer_id": retailer_id,
                "tier": tier,
                "pattern": "exponential_decay",
                "transactions_removed": deleted_count,
            })
        
        print(f"  ✓ Created churn pattern for {len(self.ground_truth['churn_retailers'])} retailers")
    
    def _inject_cross_sell_gaps(self):
        """
        Create cross-sell gaps: retailers buying A but not B.
        
        Pattern: 
        - Find retailers buying from one category in a high-affinity pair
        - Remove their purchases from the paired category
        - Creates opportunity AI can identify
        """
        print("\n[CROSS-SELL] Injecting cross-sell gaps...")
        
        # Get ACTIVE retailers with their purchase history
        retailers_with_purchases = self.conn.execute("""
            SELECT DISTINCT r.retailer_id, p.category
            FROM retailers r
            JOIN transactions t ON r.retailer_id = t.retailer_id
            JOIN products p ON t.sku_id = p.sku_id
            WHERE r.lifecycle_status = 'ACTIVE'
        """).fetchall()
        
        # Build retailer -> categories map
        retailer_categories: Dict[str, Set[str]] = {}
        for retailer_id, category in retailers_with_purchases:
            if retailer_id not in retailer_categories:
                retailer_categories[retailer_id] = set()
            retailer_categories[retailer_id].add(category)
        
        # For each affinity pair, find retailers buying both
        gaps_created = 0
        target_gaps = max(5, int(len(retailer_categories) * 0.10))  # 10%
        
        print(f"  Target gaps: {target_gaps}, Total retailers with purchases: {len(retailer_categories)}")
        
        for cat_a, cat_b in self.AFFINITY_PAIRS:
            if gaps_created >= target_gaps:
                break
            
            # Find retailers buying both categories
            both_buyers = [
                rid for rid, cats in retailer_categories.items()
                if cat_a in cats and cat_b in cats
            ]
            
            print(f"    {cat_a} + {cat_b}: {len(both_buyers)} retailers buying both")
            
            if not both_buyers:
                continue
            
            # Select some to create gaps (remove cat_b purchases)
            # Use max(1, ...) to ensure we always select at least 1
            num_to_modify = max(1, min(len(both_buyers) // 3, target_gaps - gaps_created))
            gap_retailers = random.sample(both_buyers, min(num_to_modify, len(both_buyers)))
            
            for retailer_id in gap_retailers:
                # Count transactions to delete first (DuckDB rowcount doesn't work for DELETE)
                count_result = self.conn.execute("""
                    SELECT COUNT(*) FROM transactions
                    WHERE retailer_id = ?
                      AND sku_id IN (SELECT sku_id FROM products WHERE category = ?)
                """, [retailer_id, cat_b]).fetchone()[0]
                
                if count_result > 0:
                    # Delete transactions for cat_b
                    self.conn.execute("""
                        DELETE FROM transactions
                        WHERE retailer_id = ?
                          AND sku_id IN (SELECT sku_id FROM products WHERE category = ?)
                    """, [retailer_id, cat_b])
                    
                    self.ground_truth["cross_sell_gaps"].append({
                        "retailer_id": retailer_id,
                        "buys_category": cat_a,
                        "missing_category": cat_b,
                        "affinity_pair": f"{cat_a} ↔ {cat_b}",
                        "transactions_removed": count_result,
                    })
                    gaps_created += 1
        
        print(f"  ✓ Created {gaps_created} cross-sell gaps")
    
    def _inject_stock_out(self):
        """
        Create stock-out pattern: single SKU missing from single beat.
        
        Pattern:
        - Pick 1 popular SKU
        - Pick 1 beat
        - Remove all transactions for that SKU in that beat for last 2 weeks
        - Simulates supply chain issue
        """
        print("\n[STOCK-OUT] Injecting stock-out pattern...")
        
        # Find a popular SKU (high transaction count)
        popular_sku = self.conn.execute("""
            SELECT sku_id, COUNT(*) as txn_count
            FROM transactions
            GROUP BY sku_id
            ORDER BY txn_count DESC
            LIMIT 10
        """).fetchall()
        
        if not popular_sku:
            print("  ⚠ No transactions found, skipping stock-out injection")
            return
        
        # Pick one from top 10 randomly
        target_sku = random.choice(popular_sku)[0]
        
        # Pick a beat with this SKU
        beats_with_sku = self.conn.execute("""
            SELECT DISTINCT r.beat_id
            FROM transactions t
            JOIN retailers r ON t.retailer_id = r.retailer_id
            WHERE t.sku_id = ?
        """, [target_sku]).fetchall()
        
        if not beats_with_sku:
            print("  ⚠ No beats found with target SKU, skipping")
            return
        
        target_beat = random.choice(beats_with_sku)[0]
        
        # Define stock-out period (last 14 days)
        stock_out_start = self.reference_date - timedelta(days=14)
        
        # Count transactions to delete first (DuckDB rowcount doesn't work for DELETE)
        deleted = self.conn.execute("""
            SELECT COUNT(*) FROM transactions
            WHERE sku_id = ?
              AND retailer_id IN (SELECT retailer_id FROM retailers WHERE beat_id = ?)
              AND transaction_date >= ?
        """, [target_sku, target_beat, stock_out_start]).fetchone()[0]
        
        # Delete transactions
        self.conn.execute("""
            DELETE FROM transactions
            WHERE sku_id = ?
              AND retailer_id IN (SELECT retailer_id FROM retailers WHERE beat_id = ?)
              AND transaction_date >= ?
        """, [target_sku, target_beat, stock_out_start])
        
        # Get SKU name for readability
        sku_name = self.conn.execute(
            "SELECT name FROM products WHERE sku_id = ?", [target_sku]
        ).fetchone()[0]
        
        self.ground_truth["stock_out_events"].append({
            "sku_id": target_sku,
            "sku_name": sku_name,
            "beat_id": target_beat,
            "start_date": str(stock_out_start),
            "end_date": str(self.reference_date),
            "transactions_removed": deleted,
        })
        
        print(f"  ✓ Created stock-out: {sku_name} in {target_beat}")
        print(f"    Removed {deleted} transactions from last 14 days")
    
    def _save_ground_truth(self):
        """Save ground truth to a JSON table for later validation."""
        # Create ground truth table if not exists
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ground_truth (
                anomaly_type VARCHAR,
                details JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Clear existing
        self.conn.execute("DELETE FROM ground_truth")
        
        # Insert all ground truth records
        for churn in self.ground_truth["churn_retailers"]:
            self.conn.execute(
                "INSERT INTO ground_truth (anomaly_type, details) VALUES (?, ?)",
                ["churn", json.dumps(churn)]
            )
        
        for gap in self.ground_truth["cross_sell_gaps"]:
            self.conn.execute(
                "INSERT INTO ground_truth (anomaly_type, details) VALUES (?, ?)",
                ["cross_sell_gap", json.dumps(gap)]
            )
        
        for stockout in self.ground_truth["stock_out_events"]:
            self.conn.execute(
                "INSERT INTO ground_truth (anomaly_type, details) VALUES (?, ?)",
                ["stock_out", json.dumps(stockout)]
            )
        
        print("\n  ✓ Ground truth saved to database")


def get_ground_truth(conn: duckdb.DuckDBPyConnection) -> Dict:
    """
    Retrieve ground truth from database.
    
    Returns:
        Dict with anomaly lists
    """
    result = {
        "churn_retailers": [],
        "cross_sell_gaps": [],
        "stock_out_events": [],
    }
    
    rows = conn.execute(
        "SELECT anomaly_type, details FROM ground_truth"
    ).fetchall()
    
    for anomaly_type, details in rows:
        details_dict = json.loads(details)
        if anomaly_type == "churn":
            result["churn_retailers"].append(details_dict)
        elif anomaly_type == "cross_sell_gap":
            result["cross_sell_gaps"].append(details_dict)
        elif anomaly_type == "stock_out":
            result["stock_out_events"].append(details_dict)
    
    return result


if __name__ == "__main__":
    # Test anomaly injection
    from data.database import get_connection, init_database
    from data.generator import FMCGDataGenerator
    
    print("Testing anomaly injection...")
    
    # Setup
    conn = get_connection()
    init_database(conn)
    
    # Generate baseline data
    generator = FMCGDataGenerator(conn)
    generator.generate_all()
    
    # Inject anomalies
    injector = AnomalyInjector(conn)
    ground_truth = injector.inject_all()
    
    # Verify ground truth retrieval
    print("\n" + "=" * 60)
    print("VERIFICATION: Retrieving ground truth from DB")
    print("=" * 60)
    
    retrieved = get_ground_truth(conn)
    print(f"\nRetrieved ground truth:")
    print(f"  Churn retailers: {len(retrieved['churn_retailers'])}")
    print(f"  Cross-sell gaps: {len(retrieved['cross_sell_gaps'])}")
    print(f"  Stock-out events: {len(retrieved['stock_out_events'])}")
    
    # Show sample churn retailer
    if retrieved["churn_retailers"]:
        sample = retrieved["churn_retailers"][0]
        print(f"\nSample churn retailer:")
        print(f"  ID: {sample['retailer_id']}")
        print(f"  Tier: {sample['tier']}")
        print(f"  Pattern: {sample['pattern']}")
    
    conn.close()
    print("\n✓ Anomaly injection test complete")
