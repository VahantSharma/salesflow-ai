# Phase 2: Decision Philosophy & Architecture

> **Status**: LOCKED ✅  
> **Last Updated**: Phase 2 Complete  
> **Next**: Phase 3 (UI & Interaction)

---

## 🎯 Executive Summary

Phase 2 implements a **multi-agent decision support system** for FMCG sales intelligence. The core philosophy is:

**AI extracts signals. Code makes decisions.**

This document captures the architectural decisions, business rules, and guardrails that make this system production-ready.

---

## 🏗️ Architecture Principles

### 1. View-Only SQL (Analyst)

**Why**: Prevent accidental leakage of raw operational tables.

```
✅ ALLOWED: SELECT * FROM v_churn_candidates
❌ BLOCKED: SELECT * FROM retailers
❌ BLOCKED: SELECT * FROM transactions
```

**Real-world parallel**: Production analytics teams access curated data marts, never OLTP tables.

**Implementation**:

- `ALLOWED_VIEWS` = {v_churn_candidates, v_retailer_performance, v_retailer_categories}
- Regex validation requires view name in FROM clause
- Base tables blocked even in JOINs

---

### 2. Deterministic Rules Override AI (Strategist)

**Why**: Severity affects money and human action. That must be auditable.

```python
# LLM suggests severity? We ignore it.
# Code computes severity based on thresholds.
finding['severity'] = self._compute_churn_severity(data)
```

**Three critical patterns**:

1. **LLM extracts signals** (patterns in data)
2. **Code computes severity** (deterministic thresholds)
3. **Business rules override** (cross-sell suppression)

**Interview answer**: "Why not let the LLM decide severity?"

> "Severity affects money and human action. That must be deterministic and auditable."

---

### 3. Cross-Sell Suppression Under Churn

**Business Rule**: You never upsell a retailer who is about to churn.

```python
if has_high_churn:
    findings = [f for f in findings if f['insight_type'] != 'CROSS_SELL_GAP']
    prioritized['suppressed_crosssell'] = True
```

**Why this matters**: Sales managers know this intuitively. The system encoding it shows business maturity.

---

### 4. EMPTY_RESULT is Success, Not Failure

**Philosophy**: The system's job is risk detection, not forcing output.

```
User asks: "Show me churning retailers"
Result: Empty (no one is churning)
Response: "✅ All clear! Portfolio looking healthy."
```

**Why this matters**:

- Finding no problems is good news
- Forces output → hallucinated risks
- Builds trust in "silence"

---

### 5. Fail-Fast Workflow

**Rule**: Analyst failure → Error → END. Never cascade bad data to Strategist.

```
Analyst fails SQL (retry 1) → Analyst fails again (retry 2) → ERROR → END
                                                            ↓
                                                       NEVER to Strategist
```

**Why**: Bad SQL → garbage data → garbage insight → garbage action → lost revenue.

---

## 📊 Confidence Calculation

Confidence level determines downstream message tone:

| Confidence | Tone        | Example                                 |
| ---------- | ----------- | --------------------------------------- |
| HIGH       | ASSERTIVE   | "Visit Kumar Stores immediately"        |
| MEDIUM     | SUGGESTIVE  | "Consider reaching out to Kumar Stores" |
| LOW        | EXPLORATORY | "You may want to check on Kumar Stores" |

**Calculation factors**:

1. Finding count (≥5 = strong pattern)
2. Row count (≥10 = statistical significance)
3. Data completeness (NULLs reduce confidence)
4. Severity consistency (future: Phase 4)

**Thresholds**:

- HIGH: ≥5 findings AND ≥10 rows
- MEDIUM: ≥2 findings AND ≥3 rows
- LOW: Everything else

---

## 📋 Ground Truth Contract

The `ground_truth` table exists for evaluation only, never inference.

### Schema

| Column               | Type    | Description               |
| -------------------- | ------- | ------------------------- |
| retailer_id          | VARCHAR | FK to retailers           |
| churn_label          | BOOLEAN | Actually churned?         |
| cross_sell_gap_label | BOOLEAN | Had a real gap?           |
| stockout_affected    | BOOLEAN | Was affected by stockout? |
| anomaly_type         | ENUM    | Type of seeded anomaly    |

### Rules

- **Analyst**: BLOCKED from querying ground_truth
- **Evaluation**: Only used in accuracy measurement scripts
- **Purpose**: Validate "60% accuracy" claims with real data

---

## 🔢 Severity Thresholds (Single Source of Truth)

Located in `StrategistAgent.SEVERITY_THRESHOLDS`:

```python
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
```

**Change management**: If thresholds change, update both:

1. `SEVERITY_THRESHOLDS` in strategist.py
2. `STRATEGIST_SYSTEM_PROMPT` in prompts.py

---

## 🏷️ Salescode.ai Vocabulary Mapping

Internal terms → Operational terminology:

| Internal       | Salescode Ops      |
| -------------- | ------------------ |
| VISIT          | Field Visit        |
| CALL           | Telecalling        |
| MESSAGE        | WhatsApp Nudge     |
| CHURN_RISK     | Retention Alert    |
| CROSS_SELL_GAP | Growth Opportunity |
| VALUE_DECLINE  | Performance Review |

---

## ⏱️ Workflow Guardrails

| Guardrail         | Value | Purpose                     |
| ----------------- | ----- | --------------------------- |
| MAX_WORKFLOW_TIME | 60s   | Prevent streaming abuse     |
| MAX_RETRIES       | 2     | Limit self-correction loops |
| MAX_ROWS          | 50    | Prevent data overload       |
| MAX_DISCOUNT      | 15%   | Business constraint         |

---

## 🧪 Behavioral Tests (What We Verify)

| Test                          | Validates                            |
| ----------------------------- | ------------------------------------ |
| test_analyst_view_enforcement | FROM clause must have view           |
| test_deterministic_severity   | Code computes, not LLM               |
| test_crosssell_suppression    | HIGH churn → no cross-sell           |
| test_empty_result_propagation | Empty → NO_ISSUES → positive message |
| test_workflow_structure       | Fail-fast path exists                |

---

## 📈 Alignment with Salescode.ai

This system aligns because it:

1. **Thinks in retailer portfolios** (not individual transactions)
2. **Prioritizes retention over growth** (churn beats cross-sell)
3. **Produces sales-ready actions** (VISIT/CALL/MESSAGE)
4. **Respects human-in-the-loop** (decisions, not commands)
5. **Treats AI as decision support** (code makes final call)

---

## 🔒 Phase 2 Lock-In Checklist

- [x] View-only Analyst enforcement
- [x] Deterministic severity computation
- [x] Cross-sell suppression under churn
- [x] EMPTY_RESULT as success state
- [x] Fail-fast workflow routing
- [x] Confidence calculation documented
- [x] Ground truth contract defined
- [x] Severity thresholds centralized
- [x] Salescode vocabulary mapping
- [x] Workflow time ceiling
- [x] 11/11 tests passing

---

## 📝 Future TODOs (Documented, Not Blocking)

- [ ] **Phase 4**: Multi-finding aggregation logic
- [ ] **Phase 4**: Severity consistency check in confidence
- [ ] **Phase 4**: NULL detection in confidence calculation
- [ ] **Phase 5**: Schema drift test (prompts vs code)
- [ ] **Phase 6**: Human-in-the-loop approval flow

---

**Phase 2 is COMPLETE and LOCKED.**
