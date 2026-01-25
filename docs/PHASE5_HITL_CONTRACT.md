# Phase 5: Human-in-the-Loop (HITL) Contract

## Executive Summary

Phase 5 introduces human oversight of AI recommendations through an approval system. This document defines the behavioral contract between AI-generated advice and human governance.

---

## 🚨 SYSTEM INVARIANT (NON-NEGOTIABLE)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     SYSTEM INVARIANT (NON-NEGOTIABLE)                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ONCE A HUMAN DECISION EXISTS, THE SYSTEM MAY ONLY APPEND KNOWLEDGE —        ║
║  NEVER REINTERPRET IT.                                                       ║
║                                                                              ║
║  • Human approval decisions are IRREVERSIBLE                                 ║
║  • System state may be reconstructed from events but NEVER MUTATED           ║
║  • Legacy representations exist for compatibility only and are               ║
║    NON-AUTHORITATIVE                                                         ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

This invariant frames EVERY design decision in Phase 5.

---

## ⚠️ CRITICAL ARCHITECTURAL INVARIANT

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  Approvals are EVENTS, not workflow steps.                                   ║
║                                                                              ║
║  • Workflow TERMINATES after generating advice                               ║
║  • Approvals happen OUTSIDE the workflow as governance events                ║
║  • NO LangGraph interrupts - approval is post-decision governance            ║
║  • Approval data is APPEND-ONLY (true event sourcing)                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Why This Matters

1. **Scalability**: Workflow should not block on human decisions (could be minutes to days)
2. **Separation of Concerns**: AI generates recommendations, humans govern their execution
3. **Auditability**: Clean separation enables replay and compliance tracking
4. **Simplicity**: No complex interrupt/resume state management
5. **Legal Defensibility**: Deterministic replay guarantees for audit

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 5 DATA FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │   Query     │ -> │  Workflow   │ -> │  Findings   │ -> │   UI         │  │
│  │   Input     │    │  Execution  │    │  + finding_ │    │   Renders    │  │
│  │             │    │             │    │     id      │    │              │  │
│  └─────────────┘    └──────┬──────┘    └──────┬──────┘    └──────┬───────┘  │
│                            │                  │                  │          │
│                            │ TERMINATES       │                  │          │
│                            ▼                  ▼                  ▼          │
│                      ┌─────────────────────────────────────────────────┐    │
│                      │               persistence/                       │    │
│                      │            ApprovalManager                       │    │
│                      │                                                  │    │
│                      │  create_pending() │ approve() │ reject()        │    │
│                      │                                                  │    │
│                      │  ┌────────────────────────────────────────┐     │    │
│                      │  │          DuckDB: approvals             │     │    │
│                      │  │                                        │     │    │
│                      │  │  finding_id (PK) | status | ...        │     │    │
│                      │  └────────────────────────────────────────┘     │    │
│                      └─────────────────────────────────────────────────┘    │
│                                           │                                  │
│                                           │ HUMAN ACTS                       │
│                                           ▼                                  │
│                      ┌─────────────────────────────────────────────────┐    │
│                      │           ApprovalTraceEntry                     │    │
│                      │        (appended to DecisionTrace)               │    │
│                      └─────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## CTO Corrections Applied

### RISK 1: NO Workflow Interrupts

**Wrong Approach (Avoided)**:

```python
# DON'T DO THIS - workflow should not pause for approvals
await interrupt("approval_needed", finding)
# ... wait for human ...
result = resume()
```

**Correct Approach (Implemented)**:

```python
# Workflow runs to completion
findings = workflow.run(query)
# Findings are persisted with PENDING status
for finding in findings:
    approval_manager.create_pending(finding, trace_id)
# UI queries approvals table directly
# Human acts asynchronously
```

### RISK 2: finding_id is PRIMARY KEY

**Wrong**: `recommendation_id = f"{trace_id}_{retailer_id}"`

**Correct**: `finding_id = UUID` (generated by Strategist)

Why:

- Same retailer can have multiple findings in same trace
- Re-runs should not collide
- Stable identity for approval lifecycle

### RISK 3: Rejection Context is Observational

**Wrong**: "Rejection feedback for model improvement"

**Correct**: "Manager context for operational analytics"

```python
@dataclass
class ApprovalRecord:
    # ...
    # This data is collected for OPERATIONAL ANALYTICS.
    # It is NOT consumed by the AI decision system.
    rejection_category: Optional[RejectionCategory] = None
    manager_context: Optional[str] = None  # Free-form notes
```

The `manager_context` field:

- ✅ IS for: Offline analysis, compliance reporting, understanding rejection patterns
- ❌ IS NOT for: Prompt modification, threshold adjustment, real-time learning

### RISK 4: Expiry is SUPERSEDED Status

**Wrong**: Time-based expiry with background jobs

**Correct**: Deterministic supersession when new decision replaces old

```python
def create_pending(self, finding, trace_id, decision_id):
    # Supersede existing PENDING for same retailer
    self._supersede_pending_for_retailer(retailer_id, new_finding_id)
    # Create new record
```

This ensures:

- Expiry is triggered by NEW DATA, not wall-clock time
- No background job complexity
- Clear audit trail (old record links to replacement)

### RISK 5: ApprovalManager in persistence/, NOT graph/

```
salesflow_ai/
├── graph/           # Pure computation (workflow, agents)
│   ├── workflow.py
│   ├── nodes.py
│   └── trace.py     # Includes ApprovalTraceEntry (data structure only)
├── persistence/     # State management (separate concern)
│   ├── __init__.py
│   └── approvals.py # ApprovalManager, ApprovalRecord
```

Why: `graph/` is for pure computation. Stateful operations belong in `persistence/`.

---

## Data Model

### ApprovalRecord

```python
@dataclass
class ApprovalRecord:
    # === Identity ===
    finding_id: str              # PRIMARY KEY - UUID from Strategist
    trace_id: str                # Links to DecisionTrace
    decision_id: str             # Groups findings from same run

    # === Retailer Context ===
    retailer_id: str
    retailer_name: str
    tier: str                    # Gold, Silver, Bronze

    # === Recommendation Details ===
    issue_type: str              # CHURN_RISK, CROSS_SELL_GAP, VALUE_DECLINE
    severity: str                # HIGH, MEDIUM, LOW
    confidence_level: str        # HIGH, MEDIUM, LOW
    recommended_action: str
    action_type: str             # VISIT, CALL, MESSAGE
    suggested_discount: Optional[int]

    # === Lifecycle ===
    status: ApprovalStatus       # PENDING, APPROVED, REJECTED, SUPERSEDED
    created_at: datetime
    decided_at: Optional[datetime]
    decided_by: str

    # === Rejection Context (OFFLINE ANALYTICS ONLY) ===
    rejection_category: Optional[RejectionCategory]
    manager_context: Optional[str]

    # === Supersession ===
    superseded_by: Optional[str]  # finding_id of replacement
    superseded_at: Optional[datetime]
```

### ApprovalStatus

```python
class ApprovalStatus(Enum):
    PENDING = "pending"       # Awaiting human decision
    APPROVED = "approved"     # Manager accepted
    REJECTED = "rejected"     # Manager declined
    SUPERSEDED = "superseded" # Replaced by newer decision
```

### RejectionCategory

```python
class RejectionCategory(Enum):
    INCORRECT_DATA = "incorrect_data"    # "The data shown is wrong"
    ALREADY_HANDLED = "already_handled"  # "I already dealt with this"
    WRONG_PRIORITY = "wrong_priority"    # "Not important right now"
    WRONG_ACTION = "wrong_action"        # "I'd do something different"
    NOT_APPLICABLE = "not_applicable"    # "Doesn't apply to this retailer"
    OTHER = "other"                      # Free-form
```

---

## State Transitions

```
                    ┌──────────────┐
                    │              │
        ┌──────────►│   PENDING    │◄──────────┐
        │           │              │           │
        │           └──────┬───────┘           │
        │                  │                   │
        │         ┌────────┴────────┐          │
        │         │                 │          │
        │         ▼                 ▼          │
        │   ┌──────────┐     ┌──────────┐      │
        │   │ APPROVED │     │ REJECTED │      │
        │   └──────────┘     └──────────┘      │
        │                                      │
        │                                      │
        │        NEW DECISION FOR SAME         │
        │             RETAILER                 │
        │                  │                   │
        │                  ▼                   │
        │           ┌──────────────┐           │
        └───────────│  SUPERSEDED  │───────────┘
                    └──────────────┘
```

**Transition Rules**:

- `PENDING → APPROVED`: Manager approves recommendation
- `PENDING → REJECTED`: Manager rejects with context
- `PENDING → SUPERSEDED`: New decision replaces (not time-based!)
- `APPROVED → (none)`: Terminal state
- `REJECTED → (none)`: Terminal state
- `SUPERSEDED → (none)`: Terminal state

---

## API Contract

### ApprovalManager

```python
class ApprovalManager:
    def __init__(self, db_connection=None):
        """Initialize with DuckDB connection or in-memory store."""

    def create_pending(
        self,
        finding: dict,
        trace_id: str,
        decision_id: str,
        confidence_level: str = "MEDIUM"
    ) -> ApprovalRecord:
        """
        Create PENDING approval from workflow finding.

        Side Effect: Supersedes existing PENDING for same retailer.

        Only workflow calls this - UI cannot create approvals.
        """

    def approve(
        self,
        finding_id: str,
        decided_by: str = "manager"
    ) -> ApprovalRecord:
        """
        Mark approval as APPROVED.

        Raises:
            ApprovalNotFoundError: If finding_id doesn't exist
            ApprovalAlreadyDecidedError: If not PENDING
        """

    def reject(
        self,
        finding_id: str,
        rejection_category: RejectionCategory,
        manager_context: Optional[str] = None,
        decided_by: str = "manager"
    ) -> ApprovalRecord:
        """
        Mark approval as REJECTED with context.

        Context is for OPERATIONAL ANALYTICS ONLY.
        """

    def get_pending(self) -> List[ApprovalRecord]:
        """Get all PENDING approvals."""

    def get_audit_log(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status_filter: Optional[ApprovalStatus] = None
    ) -> List[ApprovalRecord]:
        """Get audit trail for compliance."""
```

---

## UI Integration

### Confidence Badges

Trust calibration through visual indicators:

| Confidence | Icon | Color  | Message                                   |
| ---------- | ---- | ------ | ----------------------------------------- |
| HIGH       | 🟢   | Green  | Strong evidence from multiple data points |
| MEDIUM     | 🟡   | Orange | Moderate evidence - review recommended    |
| LOW        | 🔴   | Red    | Weak evidence - verify before acting      |

### Approval Card

Each recommendation card displays:

- Retailer info (name, tier)
- Issue type and severity
- **Confidence badge** (Phase 5)
- Action buttons: Approve / Reject / Details

### Rejection Modal

When rejecting, manager selects:

1. **Category** (required): One of RejectionCategory values
2. **Context** (optional): Free-form notes

Context is labeled as "for operational review" to set correct expectations.

---

## Database Schema (v3 - Event Sourced)

### Authoritative Tables (Event Sourcing)

```sql
-- AUTHORITATIVE: Immutable finding snapshots
CREATE TABLE approval_findings (
    finding_id VARCHAR PRIMARY KEY,
    trace_id VARCHAR NOT NULL,
    decision_id VARCHAR NOT NULL DEFAULT '',
    retailer_id VARCHAR NOT NULL,
    retailer_name VARCHAR NOT NULL,
    tier VARCHAR DEFAULT 'Bronze',
    issue_type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    confidence_level VARCHAR NOT NULL,
    recommended_action TEXT NOT NULL,
    action_type VARCHAR NOT NULL,
    suggested_discount INTEGER,
    deadline_description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AUTHORITATIVE: Append-only event stream
-- NO UPDATE. NO DELETE. EVER.
CREATE TABLE approval_events (
    event_id VARCHAR PRIMARY KEY,
    finding_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,  -- pending_created, approved, rejected, superseded
    event_timestamp TIMESTAMP NOT NULL,
    actor VARCHAR DEFAULT 'system',
    rejection_category VARCHAR,
    manager_context TEXT,
    superseded_by VARCHAR,
    sequence_num INTEGER DEFAULT 0  -- For deterministic ordering
);

-- Idempotency: Only one decision per finding
CREATE UNIQUE INDEX idx_events_idempotency
ON approval_events(finding_id, event_type)
WHERE event_type IN ('approved', 'rejected');

-- Efficient latest-event queries with deterministic ordering
CREATE INDEX idx_events_finding_ts
ON approval_events(finding_id, event_timestamp DESC, event_id DESC);
```

### Non-Authoritative Projection Table (Legacy Compatibility)

```sql
-- ⚠️ NON-AUTHORITATIVE: Projection for backward compatibility
-- DO NOT use for audit. Use approval_events instead.
CREATE TABLE approvals (
    finding_id VARCHAR PRIMARY KEY,
    -- ... same as before ...
    -- This table is UPDATED for convenience but is NOT the source of truth
);
```

---

## Test Coverage

Phase 5 tests verify:

1. **Finding ID Generation**: UUIDs are unique and stable
2. **ApprovalRecord Lifecycle**: Create, approve, reject, supersede
3. **ApprovalManager Persistence**: Both in-memory and DuckDB
4. **Trace Integration**: ApprovalTraceEntry can be written post-finalization
5. **Business Rules**:
   - No time-based expiry
   - Rejection context is observational only
   - finding_id is primary key
6. **CTO v3 Invariants**:
   - Event ordering is deterministic
   - Idempotency prevents duplicate decisions
   - Clock source is consistent (DB authoritative)
   - Legacy table updates are logged as non-authoritative

Target: 40+ tests in `test_phase5_approval.py`

---

## Migration Path

Phase 5 is additive - no breaking changes to Phases 0-4:

1. **New Tables**: `approval_findings` + `approval_events` (event sourcing)
2. **Legacy Table**: `approvals` maintained for backward compatibility (non-authoritative)
3. **New Module**: `persistence/approvals.py` added
4. **Strategist Update**: Generates `finding_id` for each finding
5. **Trace Update**: `ApprovalTraceEntry` added (optional field)
6. **UI Update**: Confidence badges and approval panel added

Existing workflows continue to work unchanged.

---

## Future Considerations (Out of Scope for Phase 5)

- **Authentication**: `decided_by` currently defaults to "manager"; real user IDs later
- **Execution Tracking**: If needed, create separate `ExternalOutcome` table
- **Learning Loop**: If rejection patterns inform model updates, that's Phase N (offline, human-reviewed)
- **Legacy Table Removal**: After transition period, remove `approvals` projection table

---

## Summary

Phase 5 introduces human oversight with these principles:

1. ✅ **SYSTEM INVARIANT**: Human decisions are irreversible, only append knowledge
2. ✅ Approvals are POST-workflow events (no interrupts)
3. ✅ finding_id is PRIMARY KEY (not compound key)
4. ✅ Rejection context is observational (not model feedback)
5. ✅ Expiry is SUPERSEDED (not time-based)
6. ✅ Persistence layer separate from graph computation
7. ✅ True event sourcing (append-only events, no UPDATE)
8. ✅ Idempotency enforced (no duplicate decisions)
9. ✅ Clock consistency (DB timestamp authoritative)
10. ✅ Deterministic replay (event ordering guaranteed)

The system trusts the AI to generate recommendations, but empowers humans to govern their execution with audit-grade finality.
