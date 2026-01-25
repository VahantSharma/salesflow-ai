"""
Strategist Agent

Responsibility:
- Analyze data patterns and identify business opportunities
- Prioritize insights using DETERMINISTIC rules (not LLM)
- Generate ONE specific recommendation (not menus)
- Map insights to concrete sales actions

Explicitly NOT responsible for:
- SQL generation (Analyst's job)
- Message crafting (Copywriter's job)
- Data retrieval (Analyst's job)

Personality:
- "Strategy Consultant" - thinks in frameworks, prioritizes ruthlessly
- Speaks in business outcomes, not technical metrics
- Always explains "why this matters NOW"
- References Salescode.ai's value proposition

Priority Hierarchy (DETERMINISTIC - enforced in code):
1. CHURN_RISK (retention beats everything)
2. CROSS_SELL_GAP (growth, but suppressed if churn risk HIGH)
3. VALUE_DECLINE (efficiency)

Business Rule: Cross-sell is SUPPRESSED if churn risk = HIGH
  - You never upsell a retailer who is about to churn
  - This logic is in code, not in prompts

Action Mapping (DETERMINISTIC):
- CHURN_RISK + HIGH severity → VISIT (high friction, high impact)
- CHURN_RISK + MEDIUM severity → CALL (medium friction)
- CHURN_RISK + LOW severity → MESSAGE (low friction)
- CROSS_SELL_GAP + HIGH → VISIT with trial pack
- CROSS_SELL_GAP + MEDIUM → MESSAGE with catalog

Confidence Levels (passed to Copywriter):
- HIGH: Strong evidence, >70% match with pattern → assertive tone
- MEDIUM: Moderate evidence → suggestive tone
- LOW: Weak evidence → exploratory tone

Input Contract (from Analyst):
{
    "query": str,           # Original user question
    "sql": str,             # Generated SQL
    "view_used": str,       # Which view was queried
    "results": DataFrame,   # Query results
    "result_metadata": {
        "row_count": int,
        "execution_time_ms": float,
        "is_empty": bool
    }
}

Output Format:
{
    "insight_type": "CHURN_RISK",
    "priority": "P1_CRITICAL",
    "findings": [...],
    "recommended_action": "Immediate sales rep visit",
    "action_type": "VISIT",
    "confidence_level": "HIGH",
    "business_impact": "₹47,000 monthly revenue at risk",
    "evidence": ["14 days since last order", "3 consecutive volume declines"]
}

Usage:
    from agents.strategist import StrategistAgent
    strategist = StrategistAgent(llm=llm)
    insight = strategist.analyze(analyst_output)
"""

import json
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
import pandas as pd

from config.prompts import STRATEGIST_SYSTEM_PROMPT


def generate_finding_id() -> str:
    """
    Generate a stable finding_id (UUID).
    
    This is the PRIMARY IDENTITY for approval tracking.
    Called when creating findings to ensure each has unique identity.
    
    Using UUID ensures:
    - Uniqueness across runs
    - No collision with re-analysis of same retailer
    - Stable identity for approval tracking
    
    Phase 5 (Human-in-the-Loop):
    ----------------------------
    finding_id is used by ApprovalManager as the primary key.
    Do NOT use trace_id + retailer_id as compound key - that fails
    when same retailer has multiple findings or re-runs.
    """
    return str(uuid.uuid4())


class StrategistAgent:
    """
    Strategic analysis and recommendation agent.
    
    The Strategist is the "brain" of the system - it interprets
    data and decides what to do about it.
    
    Key Features:
    - Rich input contract (preserves query intent)
    - Deterministic priority hierarchy
    - Business rule: Cross-sell suppressed if churn risk HIGH
    - Confidence scoring for downstream tone adjustment
    
    ==========================================================================
    CONFIDENCE CALCULATION PHILOSOPHY
    ==========================================================================
    Confidence level determines downstream message tone (via Copywriter).
    
    Confidence is based on:
    1. Number of affected retailers (more = higher confidence)
    2. Severity consistency across findings (consistent = higher)
    3. Data completeness (NULLs reduce confidence)
    4. Result size (not too small, not too large)
    
    Thresholds:
    - HIGH: ≥5 findings AND ≥10 rows → strong pattern detected
    - MEDIUM: ≥2 findings AND ≥3 rows → moderate signal
    - LOW: <2 findings OR <3 rows → weak/uncertain signal
    
    This transforms "confidence" from LLM fluff into auditable system signal.
    ==========================================================================
    """
    
    # =========================================================================
    # SEVERITY THRESHOLDS (SINGLE SOURCE OF TRUTH)
    # =========================================================================
    # These thresholds are used BOTH in code logic AND referenced in prompts.
    # If you change these, update STRATEGIST_SYSTEM_PROMPT in config/prompts.py
    # =========================================================================
    SEVERITY_THRESHOLDS = {
        'CHURN_RISK': {
            'HIGH': {'days_since_order': 14, 'decline_percent': 30},
            'MEDIUM': {'days_since_order': 7, 'decline_percent': 15},
        },
        'CROSS_SELL_GAP': {
            'HIGH': {'affinity_score': 0.6, 'purchase_count': 10},
            'MEDIUM': {'affinity_score': 0.5, 'purchase_count': 5},
        },
        'VALUE_DECLINE': {
            'HIGH': {'decline_percent': 25},
            'MEDIUM': {'decline_percent': 10},
        }
    }
    
    # =========================================================================
    # COLUMN MAPPING (FIX #2 - ROBUST COLUMN RESOLUTION)
    # =========================================================================
    # Maps insight types to possible DataFrame column names from views.
    # This decouples Strategist from exact view schema naming.
    # 
    # Views defined in data/schema.sql:
    #   v_churn_candidates: orders_last_14d, orders_prior_14d, days_since_order
    #   v_retailer_performance: orders_last_30d, orders_prior_30d, value_last_30d, value_prior_30d
    #   v_retailer_categories: category, purchase_count
    # =========================================================================
    COLUMN_MAP = {
        'CHURN_RISK': {
            'current': ['orders_last_14d', 'orders_last_30d'],
            'baseline': ['orders_prior_14d', 'orders_prior_30d'],
            'days_since_order': ['days_since_order'],
        },
        'VALUE_DECLINE': {
            'current': ['value_last_30d', 'value_last_14d'],
            'baseline': ['value_prior_30d', 'value_prior_14d'],
        },
        'CROSS_SELL_GAP': {
            'affinity_score': ['affinity_score'],
            'purchase_count': ['purchase_count'],
            'has_category': ['category', 'category_a'],
            'missing_category': ['category_b', 'missing_category'],
        }
    }
    
    # Priority hierarchy (lower = higher priority)
    PRIORITY_ORDER = {
        'CHURN_RISK': 1,
        'CROSS_SELL_GAP': 2,
        'VALUE_DECLINE': 3,
        'RECOGNITION': 4
    }
    
    # Severity to action mapping
    ACTION_MAPPING = {
        ('CHURN_RISK', 'HIGH'): 'VISIT',
        ('CHURN_RISK', 'MEDIUM'): 'CALL',
        ('CHURN_RISK', 'LOW'): 'MESSAGE',
        ('CROSS_SELL_GAP', 'HIGH'): 'VISIT',
        ('CROSS_SELL_GAP', 'MEDIUM'): 'MESSAGE',
        ('CROSS_SELL_GAP', 'LOW'): 'MESSAGE',
        ('VALUE_DECLINE', 'HIGH'): 'CALL',
        ('VALUE_DECLINE', 'MEDIUM'): 'MESSAGE',
        ('VALUE_DECLINE', 'LOW'): 'MESSAGE',
    }
    
    # Discount caps by severity
    DISCOUNT_CAPS = {
        'HIGH': 15,
        'MEDIUM': 10,
        'LOW': 5
    }
    
    # Tier priority (higher value = higher priority)
    # NOTE: Keys are title-case to match database. Normalize incoming tiers.
    TIER_PRIORITY = {
        'Gold': 3,
        'Silver': 2,
        'Bronze': 1
    }
    
    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Strategist Agent.
        
        Args:
            llm: LangChain chat model (GPT-4-turbo recommended)
        """
        self.llm = llm
    
    @staticmethod
    def _get_first_existing(row_data: dict, candidates: List[str], default=None):
        """
        Get the first existing column value from a list of candidates.
        
        This allows flexible column resolution across different view schemas.
        
        Args:
            row_data: Dictionary of column values from DataFrame row
            candidates: List of column names to try, in order of preference
            default: Default value if no candidate exists
            
        Returns:
            Value from first matching column, or default
        """
        for col in candidates:
            if col in row_data and row_data[col] is not None:
                return row_data[col]
        return default
    
    @staticmethod
    def _normalize_tier(tier: str) -> str:
        """
        Normalize tier to title case for consistency.
        
        Database uses 'Gold', 'Silver', 'Bronze' (title case).
        LLM might return 'GOLD', 'gold', etc.
        
        Args:
            tier: Tier string in any case
            
        Returns:
            Title-cased tier string
        """
        if not tier:
            return 'Bronze'  # Default tier
        return tier.strip().title()
    
    def analyze(self, analyst_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze data and generate strategic insight.
        
        Input Contract:
        - query: Original user question
        - sql: Generated SQL
        - view_used: Which view was queried
        - results: DataFrame with query results
        - result_metadata: {row_count, execution_time_ms, is_empty}
        
        Args:
            analyst_output: Output from AnalystAgent with full context
            
        Returns:
            Dict with insight_type, priority, findings, recommended_action,
            action_type, confidence_level, business_impact, evidence
        """
        # Extract inputs with validation
        query = analyst_output.get('query', '')
        sql = analyst_output.get('sql', '')
        view_used = analyst_output.get('view_used')
        results = analyst_output.get('results')
        result_metadata = analyst_output.get('result_metadata', {})
        
        # Handle empty results
        if result_metadata.get('is_empty', True) or results is None or len(results) == 0:
            return self._create_empty_insight(query, view_used)
        
        # Detect insight type from view used
        insight_type = self._detect_insight_type(view_used, query, results)
        
        # Generate findings using LLM (constrained to pattern recognition)
        findings = self._generate_findings(
            insight_type=insight_type,
            results=results,
            query=query,
            sql=sql
        )
        
        # CRITICAL: Inject insight_type into each finding
        # LLM findings do NOT include insight_type - we add it here
        for finding in findings:
            finding['insight_type'] = insight_type
        
        # Compute severity deterministically in Python (not LLM)
        # This ensures consistent, auditable severity assignments
        findings = self._compute_deterministic_severity(findings, insight_type, results)
        
        # Apply deterministic prioritization
        prioritized = self._prioritize(findings, insight_type)
        
        # Apply business rules
        prioritized = self._apply_business_rules(prioritized)
        
        # Calculate confidence
        confidence_level = self._calculate_confidence(prioritized, result_metadata)
        
        # Build final insight
        if not prioritized['findings']:
            return self._create_empty_insight(query, view_used)
        
        # Get top finding for summary
        top_finding = prioritized['findings'][0] if prioritized['findings'] else None
        
        # Calculate suggested discount (single source of truth - Copywriter uses this)
        top_severity = top_finding.get('severity', 'LOW') if top_finding else 'LOW'
        suggested_discount = self.DISCOUNT_CAPS.get(top_severity, 5)
        
        # =======================================================================
        # INJECT METRICS INTO FINDINGS (DETERMINISTIC - FROM DATAFRAME)
        # =======================================================================
        # Metrics MUST come from the DataFrame, NOT from LLM parsing.
        # LLM can explain, but code extracts the numbers.
        # This ensures charts have reliable, deterministic data.
        # =======================================================================
        prioritized['findings'] = self._inject_metrics_from_dataframe(
            prioritized['findings'], 
            results, 
            insight_type
        )
        
        # Update top_finding with metrics
        top_finding = prioritized['findings'][0] if prioritized['findings'] else None
        
        # =======================================================================
        # COMPUTE SUMMARY (POST-BUSINESS-RULES)
        # =======================================================================
        # Summary MUST reflect what user sees, not raw findings.
        # Cross-sell suppression has already happened at this point.
        # UI displays these counts directly - no recomputation allowed.
        # =======================================================================
        summary = self._compute_summary(prioritized['findings'])
        
        return {
            'success': True,
            'insight_type': insight_type,
            'priority': prioritized['priority'],
            'findings': prioritized['findings'],
            'top_finding': top_finding,
            'recommended_action': prioritized.get('recommended_action', 'Review data'),
            'action_type': prioritized.get('action_type', 'MESSAGE'),
            'confidence_level': confidence_level,
            'business_impact': self._calculate_business_impact(prioritized['findings']),
            'evidence': self._extract_evidence(prioritized['findings']),
            'suppressed_crosssell': prioritized.get('suppressed_crosssell', False),
            'suggested_discount': suggested_discount,  # Single source of truth for discounts
            'summary': summary  # Pre-computed counts for UI (UI must NOT recompute)
        }
    
    def _detect_insight_type(
        self, 
        view_used: Optional[str], 
        query: str,
        results: pd.DataFrame
    ) -> str:
        """
        Detect the type of insight based on view and query.
        
        Priority:
        1. View used (most reliable)
        2. Query keywords
        3. Column names in results
        """
        # Detection by view
        if view_used:
            view_mapping = {
                'v_churn_candidates': 'CHURN_RISK',
                'v_retailer_performance': 'VALUE_DECLINE',
                'v_retailer_categories': 'CROSS_SELL_GAP'
            }
            if view_used in view_mapping:
                return view_mapping[view_used]
        
        # Detection by query keywords
        query_lower = query.lower()
        if any(kw in query_lower for kw in ['churn', 'risk', 'at-risk', 'declining', 'drop']):
            return 'CHURN_RISK'
        if any(kw in query_lower for kw in ['cross-sell', 'opportunity', 'gap', 'missing']):
            return 'CROSS_SELL_GAP'
        if any(kw in query_lower for kw in ['value', 'revenue', 'decline', 'trend']):
            return 'VALUE_DECLINE'
        
        # Detection by columns
        columns = set(results.columns)
        if 'orders_last_14d' in columns or 'days_since_order' in columns:
            return 'CHURN_RISK'
        if 'missing_category' in columns or 'affinity_score' in columns:
            return 'CROSS_SELL_GAP'
        
        # Default
        return 'VALUE_DECLINE'
    
    def _generate_findings(
        self,
        insight_type: str,
        results: pd.DataFrame,
        query: str,
        sql: str
    ) -> List[Dict[str, Any]]:
        """
        Generate structured findings from data.
        
        Uses LLM for pattern recognition, but structure is deterministic.
        LLM is constrained to NOT invent numbers - only interpret what's there.
        """
        # Cap results to prevent token overflow
        df_subset = results.head(20)
        
        # Convert to string for LLM
        data_str = df_subset.to_string(index=False)
        
        # Build prompt
        # =================================================================
        # LLM PROMPT DESIGN (FIX: CLARIFIED - NO NUMBER COMPUTATION)
        # =================================================================
        # LLM's job: DESCRIBE patterns, IDENTIFY retailers, EXPLAIN why
        # LLM must NOT: Compute percentages, determine severity, assign priority
        # 
        # Numbers in output are REFERENCE ONLY - code re-extracts from DataFrame
        # This prevents hallucination from creeping into metrics
        # =================================================================
        prompt = f"""Analyze this {insight_type} data and identify specific findings.

USER QUESTION: {query}

DATA (first {len(df_subset)} rows):
{data_str}

RULES:
1. IDENTIFY retailers that show concerning patterns in the data
2. REFERENCE the column values you see (e.g., days_since_order, orders_last_14d)
3. EXPLAIN in business terms WHY each retailer matters
4. Do NOT compute percentages or changes - just cite the raw numbers you see
5. Do NOT determine severity or priority - that is computed by code
6. Each finding must have: retailer_id, retailer_name, tier, explanation

Return a JSON array of findings. Example format:
[
  {{
    "retailer_id": "R-0001",
    "retailer_name": "Kumar Stores",
    "tier": "Gold",
    "explanation": "Has not ordered in 14 days, down from 5 orders in prior period"
  }}
]

Return ONLY the JSON array, no other text.
"""
        
        try:
            messages = [
                SystemMessage(content=STRATEGIST_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = self.llm.invoke(messages)
            
            # Parse JSON response
            findings = self._parse_findings_json(response.content)
            
            # Validate findings against actual data
            validated = self._validate_findings(findings, results)
            
            return validated
            
        except Exception as e:
            # Fallback: Generate basic findings from data
            return self._generate_basic_findings(insight_type, results)
    
    def _parse_findings_json(self, content: str) -> List[Dict[str, Any]]:
        """Parse LLM response as JSON array."""
        content = content.strip()
        
        # Handle markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        try:
            findings = json.loads(content)
            if isinstance(findings, list):
                return findings
            return []
        except json.JSONDecodeError:
            return []
    
    def _validate_findings(
        self, 
        findings: List[Dict[str, Any]], 
        results: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Validate that findings reference actual data.
        
        Removes hallucinated findings that don't match the data.
        """
        if 'retailer_id' not in results.columns:
            return findings
        
        valid_ids = set(results['retailer_id'].astype(str).tolist())
        validated = []
        
        for finding in findings:
            rid = finding.get('retailer_id', '')
            if rid in valid_ids:
                validated.append(finding)
        
        return validated
    
    def _generate_basic_findings(
        self, 
        insight_type: str, 
        results: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Fallback: Generate basic findings without LLM.
        
        Used when LLM fails or returns invalid JSON.
        """
        findings = []
        
        for _, row in results.head(10).iterrows():
            finding = {
                'retailer_id': row.get('retailer_id', 'Unknown'),
                'retailer_name': row.get('name', row.get('retailer_name', 'Unknown')),
                'tier': row.get('tier', 'Unknown'),
                'severity': 'MEDIUM',  # Will be recomputed by _compute_deterministic_severity
                'insight_type': insight_type
            }
            
            # Add specific metrics based on insight type (severity computed later)
            if insight_type == 'CHURN_RISK':
                if 'days_since_order' in row:
                    days = row['days_since_order']
                    finding['metric'] = 'days_since_order'
                    finding['current_value'] = int(days) if pd.notna(days) else 0
                    finding['explanation'] = f"{days} days since last order"
                elif 'orders_last_14d' in row and 'orders_prior_14d' in row:
                    current = row['orders_last_14d']
                    prior = row['orders_prior_14d']
                    if prior > 0:
                        change = ((current - prior) / prior) * 100
                        finding['metric'] = 'order_frequency'
                        finding['current_value'] = int(current)
                        finding['baseline_value'] = int(prior)
                        finding['change_percent'] = round(change, 1)
                        finding['explanation'] = f"Order frequency changed {change:.1f}%"
            
            elif insight_type == 'CROSS_SELL_GAP':
                if 'affinity_score' in row:
                    finding['metric'] = 'affinity_score'
                    finding['current_value'] = float(row.get('affinity_score', 0))
                    finding['explanation'] = f"High affinity opportunity ({row.get('affinity_score', 0):.0%})"
                if 'purchase_count' in row:
                    finding['purchase_count'] = int(row.get('purchase_count', 0))
            
            elif insight_type == 'VALUE_DECLINE':
                if 'value_last_30d' in row and 'value_prior_30d' in row:
                    current = float(row.get('value_last_30d', 0))
                    prior = float(row.get('value_prior_30d', 0))
                    if prior > 0:
                        change = ((current - prior) / prior) * 100
                        finding['metric'] = 'order_value'
                        finding['current_value'] = current
                        finding['baseline_value'] = prior
                        finding['change_percent'] = round(change, 1)
                        finding['explanation'] = f"Order value changed {change:.1f}%"
            
            findings.append(finding)
        
        return findings
    
    def _compute_deterministic_severity(
        self,
        findings: List[Dict[str, Any]],
        insight_type: str,
        results: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Compute severity deterministically in Python (NOT by LLM).
        
        This ensures consistent, auditable severity assignments.
        LLM may suggest severity, but this method overrides with rules.
        
        CHURN_RISK severity:
        - HIGH: days_since_order > 14 OR order decline > 30%
        - MEDIUM: days_since_order > 7 OR order decline 15-30%
        - LOW: days_since_order <= 7 OR order decline < 15%
        
        CROSS_SELL_GAP severity:
        - HIGH: affinity_score > 0.6 AND purchase_count >= 10
        - MEDIUM: affinity_score > 0.5 AND purchase_count >= 5
        - LOW: everything else
        
        VALUE_DECLINE severity:
        - HIGH: value decline > 25%
        - MEDIUM: value decline 10-25%
        - LOW: value decline < 10%
        """
        # Build lookup from results DataFrame for additional context
        result_lookup = {}
        if results is not None and 'retailer_id' in results.columns:
            for _, row in results.iterrows():
                rid = str(row.get('retailer_id', ''))
                result_lookup[rid] = row.to_dict()
        
        for finding in findings:
            rid = str(finding.get('retailer_id', ''))
            row_data = result_lookup.get(rid, {})
            
            # Merge row data with finding for complete picture
            merged = {**row_data, **finding}
            
            if insight_type == 'CHURN_RISK':
                finding['severity'] = self._compute_churn_severity(merged)
            elif insight_type == 'CROSS_SELL_GAP':
                finding['severity'] = self._compute_crosssell_severity(merged)
            elif insight_type == 'VALUE_DECLINE':
                finding['severity'] = self._compute_value_severity(merged)
            else:
                # Default to MEDIUM if unknown type
                finding['severity'] = finding.get('severity', 'MEDIUM')
        
        return findings
    
    def _compute_churn_severity(self, data: Dict[str, Any]) -> str:
        """
        Deterministic churn severity based on days inactive OR order decline.
        
        REFERENCES SEVERITY_THRESHOLDS (Single Source of Truth):
        - HIGH: days_since_order > 14 OR decline > 30%
        - MEDIUM: days_since_order > 7 OR decline > 15%
        - LOW: everything else
        """
        # Get thresholds from SEVERITY_THRESHOLDS (single source of truth)
        high_thresholds = self.SEVERITY_THRESHOLDS['CHURN_RISK']['HIGH']
        medium_thresholds = self.SEVERITY_THRESHOLDS['CHURN_RISK']['MEDIUM']
        
        days_high = high_thresholds['days_since_order']      # 14
        decline_high = high_thresholds['decline_percent']     # 30
        days_medium = medium_thresholds['days_since_order']   # 7
        decline_medium = medium_thresholds['decline_percent'] # 15
        
        # Check days since order
        days = data.get('days_since_order', data.get('current_value', 0))
        if isinstance(days, (int, float)) and days > days_high:
            return 'HIGH'
        
        # Check order frequency change
        change = data.get('change_percent', 0)
        if change and change < -decline_high:
            return 'HIGH'
        if change and change < -decline_medium:
            return 'MEDIUM'
        
        # Check orders comparison (compute decline if not pre-computed)
        current = data.get('orders_last_14d', data.get('orders_last_30d', 0))
        prior = data.get('orders_prior_14d', data.get('orders_prior_30d', 0))
        if prior and prior > 0:
            decline_pct = ((current - prior) / prior) * 100
            if decline_pct < -decline_high:
                return 'HIGH'
            if decline_pct < -decline_medium:
                return 'MEDIUM'
        
        if isinstance(days, (int, float)) and days > days_medium:
            return 'MEDIUM'
        
        return 'LOW'
    
    def _compute_crosssell_severity(self, data: Dict[str, Any]) -> str:
        """
        Deterministic cross-sell severity based on affinity + purchase history.
        
        REFERENCES SEVERITY_THRESHOLDS (Single Source of Truth):
        - HIGH: affinity > 0.6 AND purchases >= 10
        - MEDIUM: affinity > 0.5 AND purchases >= 5
        - LOW: everything else
        """
        # Get thresholds from SEVERITY_THRESHOLDS (single source of truth)
        high_thresholds = self.SEVERITY_THRESHOLDS['CROSS_SELL_GAP']['HIGH']
        medium_thresholds = self.SEVERITY_THRESHOLDS['CROSS_SELL_GAP']['MEDIUM']
        
        affinity_high = high_thresholds['affinity_score']     # 0.6
        purchase_high = high_thresholds['purchase_count']     # 10
        affinity_medium = medium_thresholds['affinity_score'] # 0.5
        purchase_medium = medium_thresholds['purchase_count'] # 5
        
        affinity = data.get('affinity_score', 0)
        purchases = data.get('purchase_count', 0)
        
        if affinity > affinity_high and purchases >= purchase_high:
            return 'HIGH'
        if affinity > affinity_medium and purchases >= purchase_medium:
            return 'MEDIUM'
        
        return 'LOW'
    
    def _compute_value_severity(self, data: Dict[str, Any]) -> str:
        """
        Deterministic value decline severity based on % change.
        
        REFERENCES SEVERITY_THRESHOLDS (Single Source of Truth):
        - HIGH: decline > 25%
        - MEDIUM: decline > 10%
        - LOW: everything else
        """
        # Get thresholds from SEVERITY_THRESHOLDS (single source of truth)
        high_thresholds = self.SEVERITY_THRESHOLDS['VALUE_DECLINE']['HIGH']
        medium_thresholds = self.SEVERITY_THRESHOLDS['VALUE_DECLINE']['MEDIUM']
        
        decline_high = high_thresholds['decline_percent']     # 25
        decline_medium = medium_thresholds['decline_percent'] # 10
        
        change = data.get('change_percent', 0)
        
        if change and change < -decline_high:
            return 'HIGH'
        if change and change < -decline_medium:
            return 'MEDIUM'
        
        # Check raw values if change_percent not available
        current = data.get('value_last_30d', data.get('current_value', 0))
        prior = data.get('value_prior_30d', data.get('baseline_value', 0))
        if prior and prior > 0:
            decline_pct = ((current - prior) / prior) * 100
            if decline_pct < -decline_high:
                return 'HIGH'
            if decline_pct < -decline_medium:
                return 'MEDIUM'
        
        return 'LOW'
    
    def _prioritize(
        self, 
        findings: List[Dict[str, Any]], 
        insight_type: str
    ) -> Dict[str, Any]:
        """
        Apply deterministic prioritization rules.
        
        Priority hierarchy:
        1. CHURN_RISK > CROSS_SELL_GAP > VALUE_DECLINE
        2. Within type: HIGH severity > MEDIUM > LOW
        3. Within severity: Gold tier > Silver > Bronze
        """
        if not findings:
            return {
                'priority': 'P4_LOW',
                'findings': [],
                'recommended_action': 'No action required',
                'action_type': 'MESSAGE'
            }
        
        # Sort findings by severity and tier
        def sort_key(f):
            severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
            tier_order = {'Gold': 0, 'Silver': 1, 'Bronze': 2}
            return (
                severity_order.get(f.get('severity', 'LOW'), 2),
                tier_order.get(f.get('tier', 'Bronze'), 2)
            )
        
        sorted_findings = sorted(findings, key=sort_key)
        
        # Determine overall priority
        top_severity = sorted_findings[0].get('severity', 'LOW') if sorted_findings else 'LOW'
        type_priority = self.PRIORITY_ORDER.get(insight_type, 4)
        
        if type_priority == 1 and top_severity == 'HIGH':
            priority = 'P1_CRITICAL'
        elif type_priority == 1 or top_severity == 'HIGH':
            priority = 'P2_HIGH'
        elif top_severity == 'MEDIUM':
            priority = 'P3_MEDIUM'
        else:
            priority = 'P4_LOW'
        
        # =================================================================
        # FIX: INJECT PRIORITY INTO EACH FINDING (CTO CRITICAL #2)
        # =================================================================
        # UI does: priority = finding.get('priority', 'P3_MEDIUM')
        # Without this injection, findings silently default → hides bugs.
        # Each finding must carry its priority for consistent UI rendering.
        # =================================================================
        for f in sorted_findings:
            f['priority'] = priority
        
        # Determine action type
        action_type = self.ACTION_MAPPING.get(
            (insight_type, top_severity), 
            'MESSAGE'
        )
        
        # Build recommendation
        top = sorted_findings[0]
        if insight_type == 'CHURN_RISK':
            recommended_action = f"Contact {top.get('retailer_name', 'retailer')} ({top.get('retailer_id', '')}) - {top.get('explanation', 'declining activity')}"
        elif insight_type == 'CROSS_SELL_GAP':
            recommended_action = f"Introduce missing category to {top.get('retailer_name', 'retailer')}"
        else:
            recommended_action = f"Review {top.get('retailer_name', 'retailer')}'s account"
        
        return {
            'priority': priority,
            'findings': sorted_findings,
            'recommended_action': recommended_action,
            'action_type': action_type
        }
    
    def _apply_business_rules(self, prioritized: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply business logic rules.
        
        CRITICAL RULE: Cross-sell is SUPPRESSED if churn risk is HIGH.
        You never upsell a retailer who is about to churn.
        """
        # This rule applies when we have mixed findings
        # For now, mark if suppression would apply
        findings = prioritized.get('findings', [])
        
        has_high_churn = any(
            f.get('insight_type') == 'CHURN_RISK' and f.get('severity') == 'HIGH'
            for f in findings
        )
        
        if has_high_churn:
            # Remove cross-sell findings when high churn detected
            filtered = [
                f for f in findings 
                if f.get('insight_type') != 'CROSS_SELL_GAP'
            ]
            if len(filtered) < len(findings):
                prioritized['findings'] = filtered
                prioritized['suppressed_crosssell'] = True
        
        return prioritized
    
    def _calculate_confidence(
        self, 
        prioritized: Dict[str, Any],
        result_metadata: Dict[str, Any]
    ) -> str:
        """
        Calculate confidence level for downstream tone adjustment.
        
        =======================================================================
        CONFIDENCE CALCULATION ALGORITHM
        =======================================================================
        Confidence determines Copywriter tone:
        - HIGH → ASSERTIVE ("Visit Kumar Stores immediately")
        - MEDIUM → SUGGESTIVE ("Consider reaching out to Kumar Stores")
        - LOW → EXPLORATORY ("You may want to check on Kumar Stores")
        
        Factors Considered:
        1. Finding count: More affected retailers = stronger pattern
        2. Row count: More data points = more reliable signal
        3. Severity consistency: (TODO Phase 4: check if severities agree)
        4. Data quality: (TODO Phase 4: check for NULL metrics)
        
        Current Thresholds:
        - HIGH: ≥5 findings AND ≥10 rows
        - MEDIUM: ≥2 findings AND ≥3 rows
        - LOW: Everything else
        
        Why These Thresholds:
        - 5 retailers = meaningful segment, not noise
        - 10 rows = statistical significance for pattern
        - <3 rows = could be data quality issue, be cautious
        =======================================================================
        """
        findings = prioritized.get('findings', [])
        row_count = result_metadata.get('row_count', 0)
        
        # More findings = higher confidence
        if len(findings) >= 5 and row_count >= 10:
            return 'HIGH'
        elif len(findings) >= 2 and row_count >= 3:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_business_impact(self, findings: List[Dict[str, Any]]) -> str:
        """
        Calculate aggregate business impact in readable terms.
        """
        if not findings:
            return "No immediate impact"
        
        # Count by tier
        tier_counts = {}
        for f in findings:
            tier = f.get('tier', 'Unknown')
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Build impact string
        parts = []
        if tier_counts.get('Gold', 0):
            parts.append(f"{tier_counts['Gold']} Gold retailers")
        if tier_counts.get('Silver', 0):
            parts.append(f"{tier_counts['Silver']} Silver retailers")
        
        if parts:
            return f"{len(findings)} retailers at risk ({', '.join(parts)})"
        return f"{len(findings)} retailers require attention"
    
    def _extract_evidence(self, findings: List[Dict[str, Any]]) -> List[str]:
        """
        Extract evidence statements from findings.
        """
        evidence = []
        for f in findings[:5]:  # Top 5 only
            exp = f.get('explanation', '')
            if exp:
                evidence.append(exp)
        return evidence
    
    def _inject_metrics_from_dataframe(
        self,
        findings: List[Dict[str, Any]],
        results: pd.DataFrame,
        insight_type: str
    ) -> List[Dict[str, Any]]:
        """
        Inject structured metrics into each finding FROM THE DATAFRAME.
        
        =======================================================================
        CRITICAL: METRICS MUST BE DATAFRAME-DERIVED, NOT LLM-DERIVED
        =======================================================================
        The LLM may describe patterns, but NUMBERS must come from data.
        This ensures:
        1. Charts have reliable, verifiable data
        2. Metrics are deterministic and reproducible
        3. No hallucinated numbers in UI
        
        The LLM can explain WHY something matters, but not WHAT the numbers are.
        
        FIX #2: Uses COLUMN_MAP for dynamic column resolution.
        No longer hardcodes column names like 'orders_last_14d'.
        =======================================================================
        """
        if results is None or results.empty:
            return findings
        
        # Build lookup from DataFrame
        data_lookup = {}
        id_col = 'retailer_id' if 'retailer_id' in results.columns else None
        if id_col:
            for _, row in results.iterrows():
                rid = str(row.get(id_col, ''))
                data_lookup[rid] = row.to_dict()
        
        # Get column mapping for this insight type
        col_map = self.COLUMN_MAP.get(insight_type, {})
        
        for finding in findings:
            rid = str(finding.get('retailer_id', ''))
            row_data = data_lookup.get(rid, {})
            
            # ==================================================================
            # FIX #4: NORMALIZE TIER TO TITLE CASE
            # ==================================================================
            # Database stores 'Gold', 'Silver', 'Bronze' (title case).
            # LLM might return 'GOLD', 'gold', etc.
            # Normalize here to ensure TIER_PRIORITY lookups work.
            # ==================================================================
            if 'tier' in finding:
                finding['tier'] = self._normalize_tier(finding['tier'])
            elif 'tier' in row_data:
                finding['tier'] = self._normalize_tier(str(row_data.get('tier', 'Bronze')))
            
            # ==================================================================
            # ENFORCE retailer_id PRESENCE (CONTROLLED FAILURE)
            # ==================================================================
            # retailer_id is NOT optional. Every valid finding must have one.
            # 
            # WHY ValueError INSTEAD OF assert:
            # - assert is stripped with -O flag in production
            # - ValueError is catchable, loggable, recoverable
            # - Explicit exception beats silent default
            #
            # Callers can catch this and filter out invalid findings.
            # ==================================================================
            if not finding.get('retailer_id'):
                raise ValueError(
                    f"Finding missing required retailer_id. "
                    f"Finding keys: {list(finding.keys())}. "
                    f"This indicates upstream LLM or validation bug."
                )
            
            # Initialize metrics dict
            metrics = {}
            
            # ==================================================================
            # GENERATE FINDING_ID (PHASE 5: HUMAN-IN-THE-LOOP IDENTITY)
            # ==================================================================
            # finding_id is the PRIMARY KEY for approval tracking.
            # Generated here (single place) to ensure:
            # - Every finding gets a unique ID
            # - ID is stable for this finding's lifecycle
            # - ApprovalManager can track by finding_id
            #
            # This happens AFTER validation but BEFORE persistence.
            # ==================================================================
            if not finding.get('finding_id'):
                finding['finding_id'] = generate_finding_id()
            
            if insight_type == 'CHURN_RISK':
                # FIX #2: Use dynamic column resolution via COLUMN_MAP
                current_candidates = col_map.get('current', [])
                baseline_candidates = col_map.get('baseline', [])
                days_candidates = col_map.get('days_since_order', [])
                
                current_val = self._get_first_existing(row_data, current_candidates)
                baseline_val = self._get_first_existing(row_data, baseline_candidates)
                days_val = self._get_first_existing(row_data, days_candidates)
                
                if current_val is not None:
                    metrics['current'] = int(current_val)
                if baseline_val is not None:
                    metrics['baseline'] = int(baseline_val)
                if days_val is not None:
                    metrics['days_since_order'] = int(days_val)
                
                # Compute change_percent deterministically
                if metrics.get('baseline', 0) > 0:
                    metrics['change_percent'] = round(
                        ((metrics.get('current', 0) - metrics['baseline']) / metrics['baseline']) * 100, 
                        1
                    )
                else:
                    metrics['change_percent'] = 0
                    
            elif insight_type == 'CROSS_SELL_GAP':
                # FIX #2: Use dynamic column resolution
                affinity_candidates = col_map.get('affinity_score', [])
                purchase_candidates = col_map.get('purchase_count', [])
                has_cat_candidates = col_map.get('has_category', [])
                missing_cat_candidates = col_map.get('missing_category', [])
                
                affinity_val = self._get_first_existing(row_data, affinity_candidates)
                purchase_val = self._get_first_existing(row_data, purchase_candidates)
                has_cat = self._get_first_existing(row_data, has_cat_candidates)
                missing_cat = self._get_first_existing(row_data, missing_cat_candidates)
                
                if affinity_val is not None:
                    metrics['affinity_score'] = float(affinity_val)
                if purchase_val is not None:
                    metrics['purchase_count'] = int(purchase_val)
                if has_cat:
                    metrics['has_category'] = has_cat
                if missing_cat:
                    metrics['missing_category'] = missing_cat
                elif 'missing_category' in finding:
                    metrics['missing_category'] = finding.get('missing_category', '')
                    
            elif insight_type == 'VALUE_DECLINE':
                # FIX #2: Use dynamic column resolution
                current_candidates = col_map.get('current', [])
                baseline_candidates = col_map.get('baseline', [])
                
                current_val = self._get_first_existing(row_data, current_candidates)
                baseline_val = self._get_first_existing(row_data, baseline_candidates)
                
                if current_val is not None:
                    metrics['current'] = float(current_val)
                if baseline_val is not None:
                    metrics['baseline'] = float(baseline_val)
                
                if metrics.get('baseline', 0) > 0:
                    metrics['change_percent'] = round(
                        ((metrics.get('current', 0) - metrics['baseline']) / metrics['baseline']) * 100,
                        1
                    )
                else:
                    metrics['change_percent'] = 0
            
            # Inject metrics into finding
            finding['metrics'] = metrics
        
        return findings
    
    def _compute_summary(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute summary statistics from POST-BUSINESS-RULE findings.
        
        =======================================================================
        CRITICAL: SUMMARY REFLECTS WHAT USER SEES, NOT RAW FINDINGS
        =======================================================================
        This summary is computed AFTER:
        1. Cross-sell suppression (if HIGH churn)
        2. Severity filtering
        3. Priority sorting
        
        UI MUST use these counts directly. UI cannot recompute them.
        If UI needs different counts, add them HERE, not in UI code.
        =======================================================================
        """
        if not findings:
            return {
                'total_issues': 0,
                'churn_risks': 0,
                'crosssell_opportunities': 0,
                'value_declines': 0,
                'high_severity_count': 0,
                'medium_severity_count': 0,
                'low_severity_count': 0,
                'gold_tier_affected': 0,
                'silver_tier_affected': 0,
                'bronze_tier_affected': 0,  # FIX: Added bronze count
            }
        
        summary = {
            'total_issues': len(findings),
            'churn_risks': sum(1 for f in findings if f.get('insight_type') == 'CHURN_RISK'),
            'crosssell_opportunities': sum(1 for f in findings if f.get('insight_type') == 'CROSS_SELL_GAP'),
            'value_declines': sum(1 for f in findings if f.get('insight_type') == 'VALUE_DECLINE'),
            'high_severity_count': sum(1 for f in findings if f.get('severity') == 'HIGH'),
            'medium_severity_count': sum(1 for f in findings if f.get('severity') == 'MEDIUM'),
            'low_severity_count': sum(1 for f in findings if f.get('severity') == 'LOW'),
            'gold_tier_affected': sum(1 for f in findings if f.get('tier') == 'Gold'),
            'silver_tier_affected': sum(1 for f in findings if f.get('tier') == 'Silver'),
            'bronze_tier_affected': sum(1 for f in findings if f.get('tier') == 'Bronze'),  # FIX: Added
        }
        
        return summary
    
    def _create_empty_insight(self, query: str, view_used: Optional[str]) -> Dict[str, Any]:
        """
        Create insight for empty results (valid answer, not error).
        
        =======================================================================
        WHY NO_ISSUES IS A SUCCESS STATE (DESIGN PHILOSOPHY)
        =======================================================================
        EMPTY_RESULT is treated as NO_ISSUES because:
        
        1. The system's job is RISK DETECTION, not forcing output
           - Finding no churn risk is good news, not failure
           - "No problems found" is a valid, actionable answer
        
        2. This prevents false positives
           - Better to say "all clear" than invent problems
           - LLMs tend to hallucinate if forced to find issues
        
        3. Sales managers need confidence in silence
           - If the system says "no action needed", trust it
           - This builds long-term credibility
        
        4. Downstream handling:
           - Copywriter receives NO_ISSUES → positive reinforcement message
           - Priority is P4_LOW (no urgency)
           - Confidence is HIGH (we're confident nothing is wrong)
        
        This is NOT an error state - it's a successful determination.
        =======================================================================
        """
        # Empty summary for NO_ISSUES case
        empty_summary = {
            'total_issues': 0,
            'churn_risks': 0,
            'crosssell_opportunities': 0,
            'value_declines': 0,
            'high_severity_count': 0,
            'medium_severity_count': 0,
            'low_severity_count': 0,
            'gold_tier_affected': 0,
            'silver_tier_affected': 0,
            'bronze_tier_affected': 0,  # FIX: Added bronze count
        }
        
        return {
            'success': True,
            'insight_type': 'NO_ISSUES',
            'priority': 'P4_LOW',
            'findings': [],
            'top_finding': None,
            'recommended_action': 'No action required - all metrics within normal range',
            'action_type': 'MESSAGE',
            'confidence_level': 'HIGH',  # Confident that nothing is wrong
            'business_impact': 'No immediate concerns',
            'evidence': [f"Query returned no results matching criteria"],
            'suppressed_crosssell': False,
            'suggested_discount': 0,
            'summary': empty_summary  # UI needs this even for empty results
        }
    
    def calculate_impact(self, insight: Dict[str, Any]) -> float:
        """
        Calculate numeric impact score for ranking.
        
        Returns score between 0 and 1.
        
        TODO (Phase 4): Implement multi-finding aggregation logic.
        Current behavior: Takes top_finding only, others are secondary.
        Future need: Aggregate multiple finding types into composite actions.
        
        Example scenarios requiring aggregation:
        - 3 MEDIUM churn + 1 HIGH value decline = composite priority?
        - Multiple retailers across different insight types
        - Time-sensitive vs. opportunity-based findings
        
        For now, we prioritize by type hierarchy then severity.
        """
        priority_scores = {
            'P1_CRITICAL': 1.0,
            'P2_HIGH': 0.75,
            'P3_MEDIUM': 0.5,
            'P4_LOW': 0.25
        }
        
        base_score = priority_scores.get(insight.get('priority', 'P4_LOW'), 0.25)
        
        # Adjust for tier composition
        findings = insight.get('findings', [])
        gold_count = sum(1 for f in findings if f.get('tier') == 'Gold')
        
        tier_bonus = min(gold_count * 0.05, 0.15)  # Up to 15% bonus
        
        return min(base_score + tier_bonus, 1.0)
    
    def validate_insight(self, insight: Dict[str, Any]) -> bool:
        """
        Ensure insight meets quality thresholds.
        
        Args:
            insight: Generated insight
            
        Returns:
            True if insight is actionable and grounded in data
        """
        # Must have findings or be explicitly empty
        if insight.get('insight_type') == 'NO_ISSUES':
            return True
        
        findings = insight.get('findings', [])
        if not findings:
            return False
        
        # Each finding must have required fields
        required_fields = ['retailer_id', 'severity']
        for f in findings:
            if not all(f.get(field) for field in required_fields):
                return False
        
        return True
