-- =============================================================================
-- SalesFlow AI - DuckDB Schema Definition
-- =============================================================================
-- This schema models an FMCG distribution network with:
-- - Retailers (stores/outlets)
-- - Products (SKUs in catalog)
-- - Transactions (sales records)
-- - Visits (sales rep activity)
-- - Category Affinities (cross-sell rules)
-- =============================================================================

-- Drop existing tables (for clean recreation)
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS visits;
DROP TABLE IF EXISTS category_affinities;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS retailers;

-- =============================================================================
-- RETAILERS - Store/outlet master data
-- =============================================================================
-- Business Context:
-- Retailers are the stores/kirana shops that buy from distributors.
-- Lifecycle status is BUSINESS STATE (manually set), not computed from behavior.
-- A shop can be CLOSED even with recent orders (final clearance).
-- =============================================================================
CREATE TABLE retailers (
    retailer_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    owner_name VARCHAR,
    
    -- Customer segmentation (determines service level and credit)
    tier VARCHAR NOT NULL CHECK (tier IN ('Gold', 'Silver', 'Bronze')),
    
    -- Lifecycle state (BUSINESS decision, not computed)
    -- ACTIVE: Normal operations
    -- DORMANT: Temporarily inactive (renovation, owner travel)
    -- CLOSED: Permanently shut down (do not flag as churn)
    lifecycle_status VARCHAR NOT NULL DEFAULT 'ACTIVE' 
        CHECK (lifecycle_status IN ('ACTIVE', 'DORMANT', 'CLOSED')),
    
    -- Geographic assignment
    beat_id VARCHAR NOT NULL,
    city VARCHAR,
    latitude DECIMAL(9, 6),
    longitude DECIMAL(9, 6),
    
    -- Financial parameters
    credit_limit DECIMAL(12, 2) NOT NULL DEFAULT 10000,
    outstanding_balance DECIMAL(12, 2) NOT NULL DEFAULT 0,
    
    -- Status tracking (is_active is for soft delete, lifecycle_status is business state)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    onboarded_date DATE NOT NULL,
    
    -- Retailer preferences (2-3 preferred categories, JSON array)
    -- Used to make purchase patterns realistic
    preferred_categories VARCHAR,  -- JSON: ["Carbonated Beverages", "Salty Snacks"]
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- PRODUCTS - SKU catalog
-- =============================================================================
CREATE TABLE products (
    sku_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    brand VARCHAR NOT NULL,
    
    -- Category hierarchy (for cross-sell analysis)
    category VARCHAR NOT NULL,
    sub_category VARCHAR,
    
    -- Pricing
    price_to_retailer DECIMAL(10, 2) NOT NULL,
    mrp DECIMAL(10, 2) NOT NULL,
    margin_percent DECIMAL(5, 2) NOT NULL,
    
    -- Packaging
    case_size INTEGER NOT NULL DEFAULT 12,
    
    -- Flags
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_must_sell BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- TRANSACTIONS - Sales fact table (the core analytical table)
-- =============================================================================
-- PRICING CONTRACT (enforced in data generation):
--   unit_price: EFFECTIVE price per unit AFTER any discounts
--   total_value: quantity * unit_price (always consistent)
--   promo_discount_percent: For audit trail only, already applied to unit_price
-- 
-- Example: SKU priced ₹100, 10% promo, qty 5
--   unit_price = 90.00 (post-discount)
--   total_value = 450.00 (5 * 90)
--   promo_discount_percent = 10.00
-- =============================================================================
CREATE TABLE transactions (
    txn_id VARCHAR PRIMARY KEY,
    
    -- Foreign keys
    retailer_id VARCHAR NOT NULL REFERENCES retailers(retailer_id),
    sku_id VARCHAR NOT NULL REFERENCES products(sku_id),
    
    -- Transaction details (see pricing contract above)
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL,  -- Post-discount effective price
    total_value DECIMAL(12, 2) NOT NULL, -- = quantity * unit_price
    
    -- Time dimensions (pre-calculated for query efficiency)
    transaction_date DATE NOT NULL,
    transaction_week INTEGER NOT NULL,
    transaction_month INTEGER NOT NULL,
    
    -- Context
    sales_rep_id VARCHAR,
    
    -- Promotion tracking (for audit, discount already in unit_price)
    promo_applied BOOLEAN NOT NULL DEFAULT FALSE,
    promo_discount_percent DECIMAL(5, 2) DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- VISITS - Sales rep activity tracking
-- =============================================================================
CREATE TABLE visits (
    visit_id VARCHAR PRIMARY KEY,
    
    -- Foreign key
    retailer_id VARCHAR NOT NULL REFERENCES retailers(retailer_id),
    
    -- Visit details
    sales_rep_id VARCHAR NOT NULL,
    visit_date DATE NOT NULL,
    
    -- Outcome
    is_productive BOOLEAN NOT NULL,  -- Did they place an order?
    
    -- Efficiency metrics
    duration_minutes INTEGER,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- CATEGORY_AFFINITIES - Cross-sell correlation rules
-- =============================================================================
-- This table defines which product categories are commonly bought together.
-- Used by the Strategist agent to identify cross-sell opportunities.
-- =============================================================================
CREATE TABLE category_affinities (
    category_a VARCHAR NOT NULL,
    category_b VARCHAR NOT NULL,
    
    -- Probability that a retailer buying A also buys B
    -- P(B|A) - conditional probability
    affinity_score DECIMAL(5, 3) NOT NULL CHECK (affinity_score BETWEEN 0 AND 1),
    
    -- Description for explainability
    description VARCHAR,
    
    PRIMARY KEY (category_a, category_b)
);

-- =============================================================================
-- INDEXES - For query performance
-- =============================================================================
CREATE INDEX idx_txn_retailer_date ON transactions(retailer_id, transaction_date);
CREATE INDEX idx_txn_date ON transactions(transaction_date);
CREATE INDEX idx_txn_week ON transactions(transaction_week);
CREATE INDEX idx_txn_sku ON transactions(sku_id);
CREATE INDEX idx_visits_retailer_date ON visits(retailer_id, visit_date);
CREATE INDEX idx_retailers_tier ON retailers(tier);
CREATE INDEX idx_retailers_beat ON retailers(beat_id);
CREATE INDEX idx_retailers_active ON retailers(is_active);
CREATE INDEX idx_retailers_lifecycle ON retailers(lifecycle_status);
CREATE INDEX idx_products_category ON products(category);

-- =============================================================================
-- SEED DATA - Category Affinities (Cross-sell rules)
-- =============================================================================
-- These represent real-world purchase correlations in FMCG
INSERT INTO category_affinities (category_a, category_b, affinity_score, description) VALUES
    ('Carbonated Beverages', 'Salty Snacks', 0.72, 'Classic combo - cola and chips'),
    ('Salty Snacks', 'Carbonated Beverages', 0.68, 'Snack buyers often want drinks'),
    ('Dairy', 'Bakery', 0.65, 'Milk and bread combo'),
    ('Bakery', 'Dairy', 0.62, 'Bread buyers often buy milk'),
    ('Personal Care', 'Home Care', 0.58, 'Household shopping pattern'),
    ('Home Care', 'Personal Care', 0.55, 'Cleaning supplies and toiletries'),
    ('Juice', 'Health Snacks', 0.48, 'Health-conscious consumers'),
    ('Health Snacks', 'Juice', 0.45, 'Healthy lifestyle bundle'),
    ('Confectionery', 'Carbonated Beverages', 0.42, 'Treat yourself combo'),
    ('Carbonated Beverages', 'Confectionery', 0.38, 'Drinks and sweets combo');

-- =============================================================================
-- VIEWS - Pre-built analytical queries
-- =============================================================================
-- IMPORTANT DESIGN DECISIONS:
-- 1. All views exclude CLOSED retailers to avoid false churn flags
--    CLOSED is a business state, not behavioral decay
-- 2. All views use CURRENT_DATE for time-relative calculations
--    This means analytics change daily - this is intentional
--    For debugging, run queries on same day as data generation
-- 3. These views are the SOURCE OF TRUTH for AI agents
--    Agents MUST consume these views, NOT re-derive logic
-- =============================================================================

-- Retailer performance summary (last 30 days vs prior 30 days)
-- Excludes CLOSED retailers - they are not churn candidates
CREATE OR REPLACE VIEW v_retailer_performance AS
SELECT 
    r.retailer_id,
    r.name,
    r.tier,
    r.beat_id,
    r.lifecycle_status,
    COUNT(DISTINCT CASE WHEN t.transaction_date >= CURRENT_DATE - 30 THEN t.txn_id END) as orders_last_30d,
    COUNT(DISTINCT CASE WHEN t.transaction_date >= CURRENT_DATE - 60 
                        AND t.transaction_date < CURRENT_DATE - 30 THEN t.txn_id END) as orders_prior_30d,
    SUM(CASE WHEN t.transaction_date >= CURRENT_DATE - 30 THEN t.total_value ELSE 0 END) as value_last_30d,
    SUM(CASE WHEN t.transaction_date >= CURRENT_DATE - 60 
             AND t.transaction_date < CURRENT_DATE - 30 THEN t.total_value ELSE 0 END) as value_prior_30d,
    MAX(t.transaction_date) as last_order_date,
    CURRENT_DATE - MAX(t.transaction_date) as days_since_order
FROM retailers r
LEFT JOIN transactions t ON r.retailer_id = t.retailer_id
WHERE r.is_active = TRUE
  AND r.lifecycle_status != 'CLOSED'  -- Exclude permanently closed shops
GROUP BY r.retailer_id, r.name, r.tier, r.beat_id, r.lifecycle_status;

-- Category purchase matrix per retailer
-- For cross-sell gap analysis
CREATE OR REPLACE VIEW v_retailer_categories AS
SELECT 
    t.retailer_id,
    r.name as retailer_name,
    r.tier,
    r.lifecycle_status,
    p.category,
    COUNT(*) as purchase_count,
    SUM(t.total_value) as category_value
FROM transactions t
JOIN retailers r ON t.retailer_id = r.retailer_id
JOIN products p ON t.sku_id = p.sku_id
WHERE t.transaction_date >= CURRENT_DATE - 90
  AND r.is_active = TRUE
  AND r.lifecycle_status = 'ACTIVE'  -- Only active retailers for cross-sell
GROUP BY t.retailer_id, r.name, r.tier, r.lifecycle_status, p.category;

-- Churn candidates view (for AI agent use)
-- Retailers with declining order frequency who are NOT closed
CREATE OR REPLACE VIEW v_churn_candidates AS
SELECT 
    r.retailer_id,
    r.name,
    r.tier,
    r.beat_id,
    r.lifecycle_status,
    COUNT(DISTINCT CASE WHEN t.transaction_date >= CURRENT_DATE - 14 THEN t.txn_id END) as orders_last_14d,
    COUNT(DISTINCT CASE WHEN t.transaction_date >= CURRENT_DATE - 28 
                        AND t.transaction_date < CURRENT_DATE - 14 THEN t.txn_id END) as orders_prior_14d,
    MAX(t.transaction_date) as last_order_date,
    CURRENT_DATE - MAX(t.transaction_date) as days_since_order
FROM retailers r
LEFT JOIN transactions t ON r.retailer_id = t.retailer_id
WHERE r.is_active = TRUE
  AND r.lifecycle_status = 'ACTIVE'  -- Only ACTIVE can be churn
  AND r.tier IN ('Gold', 'Silver')   -- Focus on high-value tiers
GROUP BY r.retailer_id, r.name, r.tier, r.beat_id, r.lifecycle_status
HAVING COUNT(DISTINCT CASE WHEN t.transaction_date >= CURRENT_DATE - 28 
                           AND t.transaction_date < CURRENT_DATE - 14 THEN t.txn_id END) >= 2  -- Had activity before


-- =============================================================================
-- PHASE 5: APPROVALS TABLE - Human-in-the-Loop Governance
-- =============================================================================
-- Design Philosophy (CTO Approved):
-- ═════════════════════════════════════════════════════════════════════════════
-- 
-- 1. APPEND-ONLY: Records cannot be updated or deleted after creation.
--    Status changes create NEW records (audit trail pattern).
-- 
-- 2. POST-WORKFLOW: Approvals happen OUTSIDE the AI workflow.
--    Workflow terminates → Findings persisted → Human acts → Approval recorded
-- 
-- 3. FINDING_ID IS PRIMARY KEY: Stable identity across re-runs.
--    Do NOT use trace_id + retailer_id compound key.
-- 
-- 4. REJECTION IS OBSERVATIONAL: manager_context is for offline analytics.
--    It is NEVER fed back into the AI decision system.
-- 
-- 5. EXPIRY IS DERIVED: SUPERSEDED status when new decision replaces old.
--    No time-based expiry timers or background jobs.
-- 
-- ═════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS approvals (
    -- === Identity ===
    finding_id VARCHAR PRIMARY KEY,       -- UUID from Strategist
    trace_id VARCHAR NOT NULL,            -- Links to DecisionTrace
    decision_id VARCHAR,                  -- Groups findings from same workflow run
    
    -- === Retailer Context ===
    retailer_id VARCHAR NOT NULL,
    retailer_name VARCHAR NOT NULL,
    tier VARCHAR DEFAULT 'Bronze' CHECK (tier IN ('Gold', 'Silver', 'Bronze')),
    
    -- === Recommendation Details ===
    issue_type VARCHAR NOT NULL,          -- CHURN_RISK, CROSS_SELL_GAP, VALUE_DECLINE
    severity VARCHAR NOT NULL CHECK (severity IN ('HIGH', 'MEDIUM', 'LOW')),
    confidence_level VARCHAR DEFAULT 'MEDIUM' CHECK (confidence_level IN ('HIGH', 'MEDIUM', 'LOW')),
    recommended_action TEXT NOT NULL,
    action_type VARCHAR NOT NULL CHECK (action_type IN ('VISIT', 'CALL', 'MESSAGE')),
    suggested_discount INTEGER CHECK (suggested_discount >= 0 AND suggested_discount <= 15),
    
    -- === Timing ===
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deadline_description VARCHAR,         -- "Within 48 hours", "Next visit cycle"
    
    -- === Approval Status ===
    -- PENDING: Awaiting human decision
    -- APPROVED: Manager accepted the recommendation
    -- REJECTED: Manager declined with context
    -- SUPERSEDED: Replaced by newer decision (not time-based expiry)
    status VARCHAR DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    decided_at TIMESTAMP,
    decided_by VARCHAR DEFAULT 'manager', -- Future: actual user ID from auth
    
    -- === Manager Context (For OFFLINE ANALYTICS ONLY) ===
    -- This data is collected for operational analysis.
    -- It is NOT consumed by the AI decision system.
    rejection_category VARCHAR CHECK (
        rejection_category IS NULL OR 
        rejection_category IN ('incorrect_data', 'already_handled', 'wrong_priority', 'wrong_action', 'not_applicable', 'other')
    ),
    manager_context TEXT,                 -- Free-form notes
    
    -- === Supersession Tracking ===
    superseded_by VARCHAR,                -- finding_id of replacement
    superseded_at TIMESTAMP
);

-- Indexes for approvals table
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_retailer ON approvals(retailer_id);
CREATE INDEX IF NOT EXISTS idx_approvals_trace ON approvals(trace_id);
CREATE INDEX IF NOT EXISTS idx_approvals_created ON approvals(created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_decided ON approvals(decided_at);