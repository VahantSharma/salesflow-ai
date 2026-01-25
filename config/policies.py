"""
SalesFlow AI Governance Policies
================================

This file is DOCUMENTATION, not executable logic.
It exists to make implicit business decisions EXPLICIT.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL CONSTRAINT: This file must NEVER be imported by agents.            ║
║  Agents have their own logic. This file documents WHY that logic exists.     ║
║  If Strategist imports TierPolicy, you create a second source of truth.      ║
╚══════════════════════════════════════════════════════════════════════════════╝

This file serves three purposes:
1. UI can display policy summaries to users
2. Tests can validate behavior against documented policy
3. New engineers understand WHY the system behaves as it does

Last updated: Phase 4 implementation
"""

from typing import Final

# =============================================================================
# TIER POLICY
# =============================================================================
# This documents the tier system. Actual tier logic lives in:
# - schema.sql (view definitions)
# - seed_data.py (tier assignment)
# - strategist.py (prioritization weights)
#
# DO NOT create executable logic here. This is reference documentation.

TIER_POLICY: Final[dict] = {
    "Gold": {
        "description": "Highest-value retailers with consistent high purchase volume",
        "expected_behavior": {
            "orders_per_month": "8-12",
            "preferred_category_affinity": "70%+ purchases from top categories",
            "churn_sensitivity": "HIGH - any decline requires immediate attention",
        },
        "business_rationale": (
            "Gold retailers represent disproportionate revenue. "
            "A single Gold churner may equal 5+ Bronze churners in impact. "
            "System prioritizes Gold preservation over Bronze acquisition."
        ),
        "churn_monitoring": "Included in v_churn_candidates when days_since_order > 14",
    },
    "Silver": {
        "description": "Mid-tier retailers with moderate, stable purchase patterns",
        "expected_behavior": {
            "orders_per_month": "4-8",
            "preferred_category_affinity": "Moderate category loyalty",
            "churn_sensitivity": "MEDIUM - monitor but don't over-invest",
        },
        "business_rationale": (
            "Silver retailers are growth candidates. "
            "Cross-sell opportunities may upgrade them to Gold. "
            "But over-investment in at-risk Silver is wasteful."
        ),
        "churn_monitoring": "Included in v_churn_candidates when days_since_order > 14",
    },
    "Bronze": {
        "description": "Lower-volume retailers with sporadic ordering patterns",
        "expected_behavior": {
            "orders_per_month": "2-4",
            "preferred_category_affinity": "Low - purchases often opportunistic",
            "churn_sensitivity": "LOW - accept natural attrition",
        },
        "business_rationale": (
            "Bronze retailers have high variability by nature. "
            "14-day silence may be normal, not churn signal. "
            "Excluding Bronze from churn focus prevents false positives."
        ),
        "churn_monitoring": "EXCLUDED from v_churn_candidates (see schema.sql)",
    },
}


# =============================================================================
# BUSINESS ASSUMPTIONS
# =============================================================================
# These are the foundational beliefs that justify system behavior.
# They are NOT configurable at runtime. Changing them requires code changes.
# This documentation ensures future engineers understand the reasoning.

BUSINESS_ASSUMPTIONS: Final[dict] = {
    "churn_is_behavioral": {
        "assumption": "Churn is defined by absence of ordering, not by account status",
        "rationale": (
            "A retailer who hasn't ordered in 14+ days shows behavioral churn risk. "
            "This is distinct from administrative closure (status='CLOSED'). "
            "Behavioral signals are more actionable than status flags."
        ),
        "implementation": "v_churn_candidates uses days_since_order > 14, excludes CLOSED",
    },
    "closed_is_not_churn": {
        "assumption": "CLOSED retailers are excluded from all analysis",
        "rationale": (
            "CLOSED is a terminal state. These retailers cannot be recovered. "
            "Including them would pollute churn metrics and waste sales effort. "
            "They are filtered at the VIEW level, not the agent level."
        ),
        "implementation": "All views include WHERE status != 'CLOSED'",
    },
    "tier_determines_attention": {
        "assumption": "Higher tiers deserve disproportionate attention",
        "rationale": (
            "Revenue concentration means Gold/Silver churn has outsized impact. "
            "Bronze natural attrition is expected and acceptable. "
            "This is a business decision, not an ML optimization."
        ),
        "implementation": "Bronze excluded from v_churn_candidates, prioritization favors Gold",
    },
    "suppression_prevents_confusion": {
        "assumption": "A retailer cannot be both churn-risk AND cross-sell target",
        "rationale": (
            "Sales cannot simultaneously save and upsell. "
            "Churn risk takes priority - retain before expand. "
            "Cross-sell on at-risk accounts appears tone-deaf."
        ),
        "implementation": "strategist.py cross-sell suppression rule",
    },
    "determinism_over_ml": {
        "assumption": "Rule-based severity is preferred over ML confidence",
        "rationale": (
            "Explainability > accuracy for sales ops. "
            "Sales must understand WHY a retailer is flagged. "
            "'Days since order' is universally understood. "
            "ML confidence scores are not actionable."
        ),
        "implementation": "SEVERITY_THRESHOLDS in strategist.py, deterministic computation",
    },
}


# =============================================================================
# NON-GOALS
# =============================================================================
# These are things the system EXPLICITLY does not do.
# This protects against scope creep and stakeholder pressure.

NON_GOALS: Final[dict] = {
    "predictive_churn": {
        "description": "We do not predict future churn probability",
        "rationale": (
            "Prediction requires ML, training data, and confidence calibration. "
            "Current system identifies CURRENT risk based on CURRENT behavior. "
            "Prediction is a Phase 6+ feature requiring separate validation."
        ),
    },
    "automated_outreach": {
        "description": "System does not send emails/SMS to retailers",
        "rationale": (
            "Automation without human review risks brand damage. "
            "System provides recommendations, humans execute. "
            "This is decision SUPPORT, not decision AUTOMATION."
        ),
    },
    "price_optimization": {
        "description": "System does not dynamically adjust discounts based on behavior",
        "rationale": (
            "Dynamic pricing requires economic modeling and A/B testing. "
            "Current discounts are caps (MAX 15%), not optimizations. "
            "Price optimization is a separate product concern."
        ),
    },
    "real_time_processing": {
        "description": "System operates on batch data, not streaming",
        "rationale": (
            "Real-time adds latency requirements and infrastructure complexity. "
            "Daily/weekly analysis cadence is sufficient for FMCG sales. "
            "Real-time is premature optimization for this use case."
        ),
    },
    "multi_tenant": {
        "description": "System is single-organization, not SaaS",
        "rationale": (
            "Multi-tenancy requires data isolation, access control, billing. "
            "Current scope is single FMCG company deployment. "
            "SaaS conversion is a business model decision, not a feature."
        ),
    },
}


# =============================================================================
# OVERRIDE CONTRACT
# =============================================================================
# Defines how human operators can override system recommendations.
# This is the safety valve that makes AI recommendations acceptable.

OVERRIDE_CONTRACT: Final[dict] = {
    "principle": (
        "System recommendations are SUGGESTIONS, not COMMANDS. "
        "Human operators have final authority. "
        "Overrides are expected, not exceptional."
    ),
    "what_can_be_overridden": {
        "action_taken": "Operator can mark any action as completed/ignored/deferred",
        "priority_adjustment": "Operator can reprioritize within their workflow",
        "contact_timing": "Operator decides WHEN to act on recommendations",
    },
    "what_cannot_be_overridden": {
        "severity_calculation": (
            "Operators cannot change system-calculated severity. "
            "Severity is a SIGNAL, not a judgment. "
            "If severity feels wrong, it's a data quality issue."
        ),
        "tier_assignment": (
            "Tiers are data-driven, not operator-assigned. "
            "Manual tier changes corrupt analytics."
        ),
        "historical_data": (
            "Past behavior cannot be edited. "
            "Audit trail integrity is non-negotiable."
        ),
    },
    "feedback_mechanism": {
        "description": (
            "Operators may flag recommendations as 'unhelpful' for review. "
            "Flags go to system administrators, NOT to the AI. "
            "This prevents silent feedback loops that corrupt logic."
        ),
        "important": (
            "Feedback does NOT automatically update rules. "
            "Rule changes require human review and code deployment."
        ),
    },
}


# =============================================================================
# THRESHOLD DOCUMENTATION
# =============================================================================
# Documents why specific numbers exist.
# Actual thresholds live in strategist.py - this is reference only.

THRESHOLD_DOCUMENTATION: Final[dict] = {
    "churn_14_days": {
        "value": 14,
        "unit": "days since last order",
        "rationale": (
            "Two-week silence is significant for active FMCG retailers. "
            "Most active retailers order at least bi-weekly. "
            "14 days balances early detection vs. false positives."
        ),
        "source": "schema.sql v_churn_candidates definition",
    },
    "max_discount_15_percent": {
        "value": 15,
        "unit": "percent",
        "rationale": (
            "15% is the maximum approved discount authority for field sales. "
            "Higher discounts require manager approval. "
            "System will never recommend exceeding this cap."
        ),
        "source": "settings.py MAX_DISCOUNT_PERCENT",
    },
    "frequency_decline_30_percent": {
        "value": 30,
        "unit": "percent decline in order frequency",
        "rationale": (
            "30% decline is statistically significant for most retailers. "
            "Below 30%, variability may be normal seasonality. "
            "Above 30% indicates genuine behavior change."
        ),
        "source": "settings.py FREQUENCY_DECLINE_SIGNIFICANT",
    },
    "frequency_decline_50_percent": {
        "value": 50,
        "unit": "percent decline in order frequency",
        "rationale": (
            "50% decline is severe and requires urgent attention. "
            "This level of change is unlikely to be noise. "
            "Triggers 'critical' severity assignment."
        ),
        "source": "settings.py FREQUENCY_DECLINE_CRITICAL",
    },
}


# =============================================================================
# INTENT CLASSIFICATION BOUNDARIES
# =============================================================================
# Documents what user intent classification can and cannot do.
# This is the CTO constraint against "intent creep".

INTENT_BOUNDARIES: Final[dict] = {
    "allowed_uses": {
        "ui_flow_routing": "Intent can determine which UI panels to show",
        "response_formatting": "Intent can affect prose style (scan=brief, explain=detailed)",
        "logging_context": "Intent is recorded in decision trace for audit",
    },
    "forbidden_uses": {
        "data_selection": (
            "Intent must NEVER change which views are queried. "
            "A 'quick scan' and 'deep analysis' query the same data."
        ),
        "rule_modification": (
            "Intent must NEVER change thresholds or severity calculations. "
            "'Scan' intent doesn't mean 'use looser thresholds'."
        ),
        "prioritization": (
            "Intent must NEVER affect how retailers are prioritized. "
            "Business rules determine priority, not user mood."
        ),
    },
    "critical_invariant": (
        "Two identical business states must produce identical recommendations, "
        "regardless of how the user phrased their query. "
        "Intent affects PRESENTATION, not SUBSTANCE."
    ),
}


# =============================================================================
# AUDIT REQUIREMENTS
# =============================================================================
# Documents what must be preserved for compliance/audit purposes.

AUDIT_REQUIREMENTS: Final[dict] = {
    "decision_trace": {
        "description": "Every analysis produces an immutable decision trace",
        "retention": "Traces should be retained for compliance period (TBD by legal)",
        "access": "Read-only after workflow completion",
    },
    "data_provenance": {
        "description": "Trace must include which views and columns were accessed",
        "constraints": (
            "Provenance must NOT be sufficient to reconstruct private data. "
            "Retailer IDs are acceptable (already in findings). "
            "Order IDs, transaction counts per day, dates, SKU IDs are FORBIDDEN."
        ),
    },
    "no_silent_changes": {
        "description": "Rule changes require code deployment, not runtime config",
        "rationale": (
            "Audit requires knowing what rules were active at any point in time. "
            "Runtime-configurable rules make this impossible."
        ),
    },
}
