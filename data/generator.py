"""
FMCG Data Generator

Responsibility:
- Generate realistic synthetic data for retailers, products, transactions, visits
- Create believable patterns that mimic real FMCG distribution
- Provide baseline "normal" behavior BEFORE anomaly injection
- All generation is deterministic (seeded) for reproducibility

Key Design Decisions:
1. Deterministic: Same seed = same data (debugging friendly)
2. Settings-driven: All parameters from config.settings
3. Realistic patterns:
   - Retailers have 2-3 preferred categories (70% of purchases)
   - Tier affects order frequency and value
   - Weekend dips in ordering (realistic)
   - Max 1 order per retailer per day (deduplication via set)
4. NO anomalies here - that's seed_data.py's job

Business Reality Modeled:
- Gold retailers: High frequency (8-12 orders/month), high value
- Silver retailers: Medium frequency (4-8 orders/month), medium value  
- Bronze retailers: Low frequency (2-4 orders/month), lower value
- Each retailer has category preferences (mimics real store specialization)

SEMANTIC NOTE (Important for Phase 2):
- txn_id = Order-line (each SKU in an order is a separate transaction)
- This means COUNT(txn_id) measures LINE FREQUENCY, not ORDER FREQUENCY
- This is an acceptable proxy for "engagement" in churn detection
- If asked: "We use line-item frequency as engagement signal"

Usage:
    from data.generator import FMCGDataGenerator
    from data.database import get_connection, init_database
    
    conn = get_connection()
    init_database(conn)
    
    generator = FMCGDataGenerator(conn)
    generator.generate_all()
"""

import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import numpy as np
from faker import Faker
import duckdb

from config.settings import settings


class FMCGDataGenerator:
    """
    Generates realistic FMCG distribution data.
    
    All randomness is seeded for reproducibility.
    """
    
    # Product categories and their sub-categories
    CATEGORIES = {
        "Carbonated Beverages": ["Cola", "Lemon-Lime", "Orange", "Energy"],
        "Salty Snacks": ["Chips", "Namkeen", "Nuts", "Crackers"],
        "Dairy": ["Milk", "Curd", "Paneer", "Cheese"],
        "Bakery": ["Bread", "Biscuits", "Cakes", "Rusks"],
        "Personal Care": ["Soap", "Shampoo", "Toothpaste", "Deodorant"],
        "Home Care": ["Detergent", "Dishwash", "Floor Cleaner", "Toilet Cleaner"],
        "Confectionery": ["Chocolates", "Candies", "Gum", "Mints"],
        "Juice": ["Mango", "Apple", "Mixed Fruit", "Orange"],
        "Health Snacks": ["Protein Bars", "Granola", "Dried Fruits", "Seeds"],
    }
    
    # Brands per category (2-3 competing brands)
    BRANDS = {
        "Carbonated Beverages": ["CocaCola", "PepsiCo", "Thums Up"],
        "Salty Snacks": ["Lays", "Kurkure", "Haldirams"],
        "Dairy": ["Amul", "Mother Dairy", "Nestle"],
        "Bakery": ["Britannia", "Parle", "ITC"],
        "Personal Care": ["HUL", "P&G", "Dabur"],
        "Home Care": ["HUL", "P&G", "Godrej"],
        "Confectionery": ["Cadbury", "Nestle", "Parle"],
        "Juice": ["Tropicana", "Real", "Paper Boat"],
        "Health Snacks": ["Yoga Bar", "RiteBite", "True Elements"],
    }
    
    # Indian city names for realism
    CITIES = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", 
              "Pune", "Ahmedabad", "Kolkata", "Jaipur", "Lucknow"]
    
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        """
        Initialize generator with database connection.
        
        Args:
            conn: DuckDB connection (schema should be initialized)
        """
        self.conn = conn
        self.fake = Faker("en_IN")  # Indian locale for names
        
        # Set seeds for reproducibility
        self._set_seeds()
        
        # Will be populated during generation
        self.retailers: List[Dict] = []
        self.products: List[Dict] = []
        self.transactions: List[Dict] = []
        self.visits: List[Dict] = []
        
        # Reference date (today for the simulation)
        self.reference_date = datetime.now().date()
        
    def _set_seeds(self):
        """Set all random seeds for reproducibility."""
        seed = settings.RANDOM_SEED
        random.seed(seed)
        np.random.seed(seed)
        Faker.seed(seed)
        print(f"✓ Random seeds set to {seed}")
    
    def generate_all(self) -> Dict[str, int]:
        """
        Generate all data: retailers, products, transactions, visits.
        
        Returns:
            Dict with counts of generated records
        """
        print("\n" + "=" * 60)
        print("GENERATING FMCG DATA")
        print("=" * 60)
        
        # Order matters: retailers and products first
        self._generate_products()
        self._generate_retailers()
        self._generate_transactions()
        self._generate_visits()
        
        # Insert into database
        self._insert_all()
        
        counts = {
            "retailers": len(self.retailers),
            "products": len(self.products),
            "transactions": len(self.transactions),
            "visits": len(self.visits),
        }
        
        print("\n" + "=" * 60)
        print("GENERATION COMPLETE")
        for table, count in counts.items():
            print(f"  {table}: {count:,} records")
        print("=" * 60)
        
        return counts
    
    def _generate_products(self):
        """Generate product catalog."""
        print("\n[1/4] Generating products...")
        
        sku_counter = 1
        
        for category, sub_categories in self.CATEGORIES.items():
            brands = self.BRANDS.get(category, ["Generic"])
            
            for sub_cat in sub_categories:
                # 2-3 SKUs per sub-category per brand
                for brand in brands:
                    num_skus = random.randint(2, 3)
                    for _ in range(num_skus):
                        # Price varies by category
                        base_price = self._get_base_price(category)
                        margin = random.uniform(0.15, 0.30)
                        
                        product = {
                            "sku_id": f"SKU-{sku_counter:04d}",
                            "name": f"{brand} {sub_cat} {random.choice(['500ml', '1L', '200g', '500g', '100g'])}",
                            "brand": brand,
                            "category": category,
                            "sub_category": sub_cat,
                            "price_to_retailer": round(base_price * (1 - margin), 2),
                            "mrp": round(base_price, 2),
                            "margin_percent": round(margin * 100, 2),
                            "case_size": random.choice([6, 12, 24]),
                            "is_active": True,
                            "is_must_sell": random.random() < 0.1,  # 10% are must-sell
                        }
                        self.products.append(product)
                        sku_counter += 1
        
        print(f"  ✓ Generated {len(self.products)} products across {len(self.CATEGORIES)} categories")
    
    def _get_base_price(self, category: str) -> float:
        """Get realistic base price for a category."""
        price_ranges = {
            "Carbonated Beverages": (20, 80),
            "Salty Snacks": (10, 100),
            "Dairy": (25, 200),
            "Bakery": (20, 150),
            "Personal Care": (30, 300),
            "Home Care": (50, 400),
            "Confectionery": (10, 200),
            "Juice": (30, 150),
            "Health Snacks": (50, 300),
        }
        low, high = price_ranges.get(category, (20, 100))
        return round(random.uniform(low, high), 2)
    
    def _generate_retailers(self):
        """Generate retailer master data with category preferences."""
        print("\n[2/4] Generating retailers...")
        
        num_retailers = settings.NUM_RETAILERS
        tier_dist = settings.TIER_DISTRIBUTION
        
        # Calculate counts per tier
        num_gold = int(num_retailers * tier_dist["Gold"])
        num_silver = int(num_retailers * tier_dist["Silver"])
        num_bronze = num_retailers - num_gold - num_silver
        
        # Generate beats (geographic routes)
        num_beats = settings.NUM_BEATS
        beats = [f"BEAT-{i:02d}" for i in range(1, num_beats + 1)]
        
        all_categories = list(self.CATEGORIES.keys())
        
        for i in range(num_retailers):
            # Determine tier
            if i < num_gold:
                tier = "Gold"
                credit_limit = random.uniform(50000, 100000)
                num_preferred = 3  # Gold stores are more diverse
            elif i < num_gold + num_silver:
                tier = "Silver"
                credit_limit = random.uniform(25000, 50000)
                num_preferred = 2
            else:
                tier = "Bronze"
                credit_limit = random.uniform(10000, 25000)
                num_preferred = 2
            
            # Assign preferred categories (this drives purchase behavior)
            preferred = random.sample(all_categories, num_preferred)
            
            # Small percentage are CLOSED or DORMANT (for realism)
            if random.random() < 0.02:  # 2% closed
                lifecycle = "CLOSED"
            elif random.random() < 0.03:  # 3% dormant
                lifecycle = "DORMANT"
            else:
                lifecycle = "ACTIVE"
            
            city = random.choice(self.CITIES)
            
            retailer = {
                "retailer_id": f"R-{i+1:04d}",
                "name": f"{self.fake.first_name()}'s {random.choice(['Store', 'Shop', 'Mart', 'Kirana'])}",
                "owner_name": self.fake.name(),
                "tier": tier,
                "lifecycle_status": lifecycle,
                "beat_id": random.choice(beats),
                "city": city,
                "latitude": round(random.uniform(18.5, 28.5), 6),  # India lat range
                "longitude": round(random.uniform(72.5, 88.5), 6),  # India lon range
                "credit_limit": round(credit_limit, 2),
                "outstanding_balance": round(random.uniform(0, credit_limit * 0.3), 2),
                "is_active": lifecycle != "CLOSED",
                "onboarded_date": self.reference_date - timedelta(days=random.randint(90, 365*2)),
                "preferred_categories": json.dumps(preferred),
            }
            self.retailers.append(retailer)
        
        print(f"  ✓ Generated {len(self.retailers)} retailers")
        print(f"    Gold: {num_gold}, Silver: {num_silver}, Bronze: {num_bronze}")
        print(f"    ACTIVE: {sum(1 for r in self.retailers if r['lifecycle_status'] == 'ACTIVE')}")
        print(f"    DORMANT: {sum(1 for r in self.retailers if r['lifecycle_status'] == 'DORMANT')}")
        print(f"    CLOSED: {sum(1 for r in self.retailers if r['lifecycle_status'] == 'CLOSED')}")
    
    def _generate_transactions(self):
        """
        Generate transaction history with realistic patterns.
        
        Key patterns:
        - Tier affects frequency and value
        - Preferred categories get 70% of purchases
        - Weekend dips (Saturday/Sunday lower)
        - Some random noise
        """
        print("\n[3/4] Generating transactions...")
        
        days_history = settings.DAYS_OF_HISTORY
        start_date = self.reference_date - timedelta(days=days_history)
        
        # Products by category for quick lookup
        products_by_category = {}
        for p in self.products:
            cat = p["category"]
            if cat not in products_by_category:
                products_by_category[cat] = []
            products_by_category[cat].append(p)
        
        all_categories = list(products_by_category.keys())
        txn_counter = 1
        
        for retailer in self.retailers:
            # Skip CLOSED retailers entirely (no recent transactions)
            if retailer["lifecycle_status"] == "CLOSED":
                continue
            
            # DORMANT retailers have sparse recent transactions
            if retailer["lifecycle_status"] == "DORMANT":
                days_active = days_history // 3  # Only active for first third
            else:
                days_active = days_history
            
            tier = retailer["tier"]
            preferred_cats = json.loads(retailer["preferred_categories"])
            
            # Base orders per month by tier
            if tier == "Gold":
                orders_per_month = random.uniform(8, 12)
                avg_items_per_order = random.uniform(5, 10)
                avg_qty_per_item = random.uniform(3, 8)
            elif tier == "Silver":
                orders_per_month = random.uniform(4, 8)
                avg_items_per_order = random.uniform(3, 6)
                avg_qty_per_item = random.uniform(2, 5)
            else:  # Bronze
                orders_per_month = random.uniform(2, 4)
                avg_items_per_order = random.uniform(2, 4)
                avg_qty_per_item = random.uniform(1, 3)
            
            # Calculate order dates (max 1 order per day - realistic FMCG pattern)
            num_orders = int((days_active / 30) * orders_per_month)
            order_dates = set()  # Use set to prevent duplicate dates
            
            # Try to fill unique order dates (with reasonable attempt limit)
            attempts = 0
            max_attempts = num_orders * 3  # Prevent infinite loop
            
            while len(order_dates) < num_orders and attempts < max_attempts:
                attempts += 1
                
                # Random date within active period
                days_ago = random.randint(0, days_active - 1)
                order_date = self.reference_date - timedelta(days=days_ago)
                
                # Weekend dip: 50% less likely on Sat/Sun
                if order_date.weekday() >= 5:  # Saturday or Sunday
                    if random.random() < 0.5:
                        continue
                
                order_dates.add(order_date)  # Set automatically deduplicates
            
            order_dates = list(order_dates)  # Convert back to list for iteration
            
            # Generate transactions for each order
            for order_date in order_dates:
                num_items = max(1, int(np.random.normal(avg_items_per_order, 1)))
                
                # Select categories: 70% from preferred, 30% from others
                order_categories = []
                for _ in range(num_items):
                    if random.random() < 0.7 and preferred_cats:
                        order_categories.append(random.choice(preferred_cats))
                    else:
                        order_categories.append(random.choice(all_categories))
                
                for category in order_categories:
                    # Pick a product from this category
                    product = random.choice(products_by_category[category])
                    
                    # Quantity with some noise
                    quantity = max(1, int(np.random.normal(avg_qty_per_item, 1)))
                    
                    # Promo: 15% chance
                    promo_applied = random.random() < 0.15
                    if promo_applied:
                        discount = random.uniform(5, settings.MAX_DISCOUNT_PERCENT)
                    else:
                        discount = 0
                    
                    # Calculate prices (following our pricing contract)
                    base_price = product["price_to_retailer"]
                    unit_price = round(base_price * (1 - discount/100), 2)
                    total_value = round(unit_price * quantity, 2)
                    
                    transaction = {
                        "txn_id": f"TXN-{txn_counter:08d}",
                        "retailer_id": retailer["retailer_id"],
                        "sku_id": product["sku_id"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_value": total_value,
                        "transaction_date": order_date,
                        "transaction_week": order_date.isocalendar()[1],
                        "transaction_month": order_date.month,
                        "sales_rep_id": f"SR-{random.randint(1, 20):02d}",
                        "promo_applied": promo_applied,
                        "promo_discount_percent": round(discount, 2) if promo_applied else 0,
                    }
                    self.transactions.append(transaction)
                    txn_counter += 1
        
        print(f"  ✓ Generated {len(self.transactions):,} transactions")
    
    def _generate_visits(self):
        """
        Generate visit records from transactions + non-productive visits.
        
        Rules:
        - Every transaction date = productive visit
        - Add 15-20% non-productive visits
        """
        print("\n[4/4] Generating visits...")
        
        # Group transactions by retailer and date
        retailer_dates = {}
        for txn in self.transactions:
            key = (txn["retailer_id"], txn["transaction_date"])
            if key not in retailer_dates:
                retailer_dates[key] = txn["sales_rep_id"]
        
        visit_counter = 1
        
        # Create productive visits from transactions
        for (retailer_id, visit_date), sales_rep_id in retailer_dates.items():
            visit = {
                "visit_id": f"V-{visit_counter:08d}",
                "retailer_id": retailer_id,
                "sales_rep_id": sales_rep_id,
                "visit_date": visit_date,
                "is_productive": True,
                "duration_minutes": random.randint(10, 45),
            }
            self.visits.append(visit)
            visit_counter += 1
        
        num_productive = len(self.visits)
        
        # Add non-productive visits (15-20% of productive)
        num_non_productive = int(num_productive * random.uniform(0.15, 0.20))
        
        active_retailers = [r for r in self.retailers if r["lifecycle_status"] == "ACTIVE"]
        
        for _ in range(num_non_productive):
            retailer = random.choice(active_retailers)
            days_ago = random.randint(0, settings.DAYS_OF_HISTORY - 1)
            visit_date = self.reference_date - timedelta(days=days_ago)
            
            visit = {
                "visit_id": f"V-{visit_counter:08d}",
                "retailer_id": retailer["retailer_id"],
                "sales_rep_id": f"SR-{random.randint(1, 20):02d}",
                "visit_date": visit_date,
                "is_productive": False,
                "duration_minutes": random.randint(5, 15),  # Shorter for non-productive
            }
            self.visits.append(visit)
            visit_counter += 1
        
        print(f"  ✓ Generated {len(self.visits):,} visits")
        print(f"    Productive: {num_productive:,}")
        print(f"    Non-productive: {num_non_productive:,}")
    
    def _insert_all(self):
        """Insert all generated data into database using batch operations."""
        print("\n[INSERT] Writing to database...")
        
        # Insert products (small, OK to do individually)
        for p in self.products:
            self.conn.execute("""
                INSERT INTO products (sku_id, name, brand, category, sub_category,
                    price_to_retailer, mrp, margin_percent, case_size, is_active, is_must_sell)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [p["sku_id"], p["name"], p["brand"], p["category"], p["sub_category"],
                  p["price_to_retailer"], p["mrp"], p["margin_percent"], p["case_size"],
                  p["is_active"], p["is_must_sell"]])
        print(f"  ✓ Inserted {len(self.products)} products")
        
        # Insert retailers (small, OK to do individually)
        for r in self.retailers:
            self.conn.execute("""
                INSERT INTO retailers (retailer_id, name, owner_name, tier, lifecycle_status,
                    beat_id, city, latitude, longitude, credit_limit, outstanding_balance,
                    is_active, onboarded_date, preferred_categories)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [r["retailer_id"], r["name"], r["owner_name"], r["tier"], r["lifecycle_status"],
                  r["beat_id"], r["city"], r["latitude"], r["longitude"], r["credit_limit"],
                  r["outstanding_balance"], r["is_active"], r["onboarded_date"], r["preferred_categories"]])
        print(f"  ✓ Inserted {len(self.retailers)} retailers")
        
        # Insert transactions BATCH (20k+ rows - need batch for performance)
        txn_data = [
            (t["txn_id"], t["retailer_id"], t["sku_id"], t["quantity"], t["unit_price"],
             t["total_value"], t["transaction_date"], t["transaction_week"], t["transaction_month"],
             t["sales_rep_id"], t["promo_applied"], t["promo_discount_percent"])
            for t in self.transactions
        ]
        self.conn.executemany("""
            INSERT INTO transactions (txn_id, retailer_id, sku_id, quantity, unit_price,
                total_value, transaction_date, transaction_week, transaction_month,
                sales_rep_id, promo_applied, promo_discount_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, txn_data)
        print(f"  ✓ Inserted {len(self.transactions):,} transactions")
        
        # Insert visits BATCH (6k+ rows)
        visit_data = [
            (v["visit_id"], v["retailer_id"], v["sales_rep_id"], v["visit_date"],
             v["is_productive"], v["duration_minutes"])
            for v in self.visits
        ]
        self.conn.executemany("""
            INSERT INTO visits (visit_id, retailer_id, sales_rep_id, visit_date,
                is_productive, duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, visit_data)
        print(f"  ✓ Inserted {len(self.visits):,} visits")


if __name__ == "__main__":
    # Quick test
    from data.database import get_connection, init_database
    
    print("Testing data generator...")
    conn = get_connection()
    init_database(conn)
    
    generator = FMCGDataGenerator(conn)
    counts = generator.generate_all()
    
    print("\nVerification queries:")
    
    # Check tier distribution
    result = conn.execute("""
        SELECT tier, COUNT(*) as count, 
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
        FROM retailers 
        GROUP BY tier 
        ORDER BY tier
    """).fetchdf()
    print("\nTier Distribution:")
    print(result.to_string(index=False))
    
    # Check category distribution
    result = conn.execute("""
        SELECT p.category, COUNT(*) as txn_count
        FROM transactions t
        JOIN products p ON t.sku_id = p.sku_id
        GROUP BY p.category
        ORDER BY txn_count DESC
        LIMIT 5
    """).fetchdf()
    print("\nTop Categories by Transactions:")
    print(result.to_string(index=False))
    
    conn.close()
