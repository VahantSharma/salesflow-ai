# Phase 6 Lock – HITL & Backend Authority

> **Status**: 🔒 LOCKED  
> **Locked Date**: January 25, 2026  
> **Lock Version**: v0.6.0-phase6  
> **Next Phase**: Phase 7 (Governance Evolution)

---

## ⚠️ THIS PHASE IS CLOSED

Phase 6 is **COMPLETE** and **LOCKED**.

Any modification to Phase 6 invariants requires:
1. CTO-level review
2. New invariant tests added FIRST
3. Explicit sign-off documented in this file

---

## 🔐 Non-Negotiable Invariants

These invariants are **ENFORCED BY TESTS** and **MUST NOT** be violated:

### Invariant 6.1: UI Never Computes Approval State
```
UI queries ApprovalService for status.
UI does NOT maintain approved/rejected lists in session state.
```
- **Enforced by**: `test_invariant_6_1_ui_never_computes_approval_state`
- **Location**: `app.py` uses `get_pending_finding_ids()`

### Invariant 6.2: finding_id Flows End-to-End
```
Strategist generates finding_id.
ApprovalManager receives finding_id.
All downstream references use the SAME finding_id.
```
- **Enforced by**: `test_invariant_6_2_finding_id_flows_end_to_end`
- **Location**: `agents/strategist.py` → `persistence/approvals.py`

### Invariant 6.3: Trace Correlation via decision_id
```
Every workflow run generates ONE decision_id.
trace_id + decision_id link everything.
DecisionTrace captures both immutably.
```
- **Enforced by**: `test_invariant_6_3_trace_correlation`
- **Location**: `graph/workflow.py`, `graph/trace.py`

### Invariant 6.4: Session Independence
```
Different Streamlit sessions see IDENTICAL approval state.
Backend (ApprovalManager) is the single source of truth.
No session-local approval tracking.
```
- **Enforced by**: `test_invariant_6_4_different_sessions_same_state`
- **Location**: `services/approval_service.py`

### Invariant 6.5: No Implicit Learning
```
Rejection analytics are for HUMANS only.
Analytics MUST NOT feed back into AI decisions.
get_rejection_analytics() is observational, not training data.
```
- **Enforced by**: `test_invariant_6_5_no_implicit_learning`
- **Location**: `persistence/approvals.py`

### Invariant 6.6: Deterministic Replay (Partial)
```
Event sourcing supports state reconstruction.
Version metadata captured for future replay.
Full replay is Phase 7 scope.
```
- **Enforced by**: `test_invariant_6_6_deterministic_replay`
- **Location**: `persistence/approvals.py`, `graph/trace.py`

---

## 🚫 DO NOT Rules

| Action | Why Forbidden |
|--------|---------------|
| Add `approved[]` or `rejected[]` to session state | Violates Invariant 6.1, 6.4 |
| Compute approval status in UI code | Violates Invariant 6.1 |
| Generate finding_id outside Strategist | Violates Invariant 6.2 |
| Modify ALLOWED_TRANSITIONS without CTO review | Breaks state machine |
| Use rejection analytics for model training | Violates Invariant 6.5 |
| Bypass `managed_trace()` context manager | Breaks trace finalization guarantee |
| Add UPDATE/DELETE to approval_events table | Breaks event sourcing |

---

## 🧪 Guardian Tests

These tests will **FAIL LOUDLY** if Phase 6 is violated:

| Test File | Test Class | Purpose |
|-----------|------------|---------|
| `test_phase6_hitl.py` | `TestPhase6Invariants` | All 6 invariants |
| `test_phase6_hitl.py` | `TestBackendAuthority` | Session independence |
| `test_phase6_hitl.py` | `TestAnalyticsIsolation` | No AI feedback |
| `test_phase5_approval.py` | `TestCTOv3Invariants` | State machine |
| `test_phase4_trace.py` | `TestTraceIntegrity` | Trace finalization |

**Run before ANY Phase 6-adjacent change:**
```bash
python -m pytest tests/test_phase6_hitl.py tests/test_phase5_approval.py -v
```

---

## 📐 Architectural Boundaries

### What Phase 6 IS Responsible For
- ✅ Backend authority for approvals
- ✅ HITL correctness and state machine
- ✅ Trace integrity and finalization
- ✅ Session independence
- ✅ Analytics isolation
- ✅ Idempotency enforcement

### What Phase 6 IS NOT Responsible For
- ❌ Deterministic replay (Phase 7)
- ❌ Compliance exports (Phase 7)
- ❌ Learning from rejections (NEVER - by design)
- ❌ Multi-user authentication (Phase 7+)
- ❌ SLA/expiry automation (Phase 7)

---

## 🏗️ Key Implementation Files

| File | Phase 6 Responsibility |
|------|------------------------|
| `graph/workflow.py` | `managed_trace()` context manager |
| `persistence/approvals.py` | `ALLOWED_TRANSITIONS`, `validate_state_transition()` |
| `services/approval_service.py` | Thin adapter, backend authority |
| `graph/trace.py` | `DecisionTrace`, `IntegrityStatus` |
| `app.py` | UI queries backend, no local state |

---

## 📊 Test Coverage at Lock Time

```
Total Tests: 247
Passing: 187
Skipped: 60 (LLM-dependent)
Phase 6 Specific: 28 tests in test_phase6_hitl.py
```

---

## 🔄 Change Log

| Date | Author | Change | Approved By |
|------|--------|--------|-------------|
| 2026-01-25 | System | Phase 6 LOCKED | CTO Review |

---

## 📎 Related Documents

- [PHASE5_HITL_CONTRACT.md](PHASE5_HITL_CONTRACT.md) - Event sourcing foundation
- [PHASE5_COMPLETE_TECHNICAL_DOCUMENTATION.md](PHASE5_COMPLETE_TECHNICAL_DOCUMENTATION.md) - Full technical spec
- [PHASE2_DECISION_PHILOSOPHY.md](PHASE2_DECISION_PHILOSOPHY.md) - Decision architecture

---

**Phase 6 is CLOSED. Phase 7 begins from here.**
