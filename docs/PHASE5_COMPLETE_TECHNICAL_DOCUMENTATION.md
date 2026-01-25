# Phase 5: Human-in-the-Loop (HITL) - Complete Technical Documentation

## Document Purpose

This document provides an exhaustive, audit-grade technical specification of every component, design decision, algorithm, and implementation detail in Phase 5 of the SalesFlow AI system. It is intended for:

- Senior engineers conducting code reviews
- Architects evaluating system design
- Auditors verifying compliance requirements
- Interview preparation and technical deep-dives

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Invariant](#2-system-invariant)
3. [Architecture Overview](#3-architecture-overview)
4. [Event Sourcing Implementation](#4-event-sourcing-implementation)
5. [Data Classes](#5-data-classes)
6. [ApprovalManager Implementation](#6-approvalmanager-implementation)
7. [Exception Hierarchy](#7-exception-hierarchy)
8. [Trace Integration](#8-trace-integration)
9. [Database Schema](#9-database-schema)
10. [CTO Corrections (v1 → v2 → v3 → v4)](#10-cto-corrections-v1--v2--v3--v4)
11. [Test Suite Architecture](#11-test-suite-architecture)
12. [API Reference](#12-api-reference)
13. [File-by-File Analysis](#13-file-by-file-analysis)

---

## 1. Executive Summary

### Purpose

Phase 5 introduces **human oversight** for AI-generated sales recommendations. When the AI system (via the Strategist agent) generates findings like "Retailer X is at churn risk - visit immediately", these recommendations are **not auto-executed**. Instead, they enter a **pending approval queue** where human managers review, approve, or reject them.

### Key Innovation

This is **not** a simple approve/reject button system. It is an **audit-grade event-sourced governance layer** with:

- **Irreversible human decisions** (SYSTEM INVARIANT)
- **Full audit trail** with time-travel capability
- **Zero UPDATE/DELETE** on event tables
- **Deterministic replay** guarantees
- **Legal defensibility** through non-repudiation
- **Production-grade hardening** (v4: transactional writes, constraint-driven idempotency)

### Version

**Current**: v4 (Production-Grade) - All CTO corrections implemented and tested.

### Scope

- **In Scope**: Approval lifecycle, event sourcing, audit trails, rejection analytics, explicit expiration
- **Out of Scope**: Authentication (uses default "manager"), execution tracking, ML feedback loops

---

## 2. System Invariant

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

### Why This Matters

1. **Legal Compliance**: Financial and healthcare audits require provable decision trails
2. **Non-Repudiation**: System cannot deny what it knew at time T
3. **Trust Calibration**: Humans must trust that their decisions won't be silently overwritten
4. **Deterministic Replay**: Given the same events, always reach the same state

### Implementation Consequences

| Action                         | Allowed? | Reason                               |
| ------------------------------ | -------- | ------------------------------------ |
| Approve a PENDING finding      | ✅ Yes   | Appends APPROVED event               |
| Re-approve an APPROVED finding | ❌ No    | Human already decided                |
| Reject an APPROVED finding     | ❌ No    | Cannot reverse human decision        |
| UPDATE any event row           | ❌ No    | Events are immutable                 |
| DELETE any event row           | ❌ No    | Events are permanent                 |
| Supersede a PENDING finding    | ✅ Yes   | New data replaces old recommendation |

---

## 3. Architecture Overview

### Critical Architectural Invariant

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

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 5 DATA FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │   Query     │ -> │  Workflow   │ -> │  Findings   │ -> │   UI         │  │
│  │   Input     │    │  Execution  │    │  + finding_ │    │   Renders    │  │
│  │             │    │  (LangGraph)│    │     id      │    │   Cards      │  │
│  └─────────────┘    └──────┬──────┘    └──────┬──────┘    └──────┬───────┘  │
│                            │                  │                  │          │
│                            │ TERMINATES       │ POST-WORKFLOW    │          │
│                            ▼                  ▼                  ▼          │
│                      ┌─────────────────────────────────────────────────┐    │
│                      │               persistence/                       │    │
│                      │            ApprovalManager (v3)                  │    │
│                      │                                                  │    │
│                      │  create_pending() ──► approval_findings (INSERT) │    │
│                      │                   └─► approval_events (INSERT)   │    │
│                      │  approve()        ──► approval_events (INSERT)   │    │
│                      │  reject()         ──► approval_events (INSERT)   │    │
│                      │                                                  │    │
│                      │  NEVER UPDATE. NEVER DELETE.                     │    │
│                      └─────────────────────────────────────────────────┘    │
│                                           │                                  │
│                                           │ HUMAN ACTS                       │
│                                           ▼                                  │
│                      ┌─────────────────────────────────────────────────┐    │
│                      │           ApprovalTraceEntry                     │    │
│                      │        (appended to DecisionTrace)               │    │
│                      │                                                  │    │
│                      │  Can be appended AFTER finalization (exception) │    │
│                      └─────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why NOT Workflow Interrupts

The original design considered using LangGraph's `interrupt()` to pause the workflow for human approval:

```python
# ❌ WRONG APPROACH (Rejected)
async def approval_node(state):
    await interrupt("approval_needed", finding)
    result = resume()  # Waits for human
    return state
```

**Problems with this approach:**

1. **Scalability**: Workflow thread blocked for minutes/hours/days
2. **State Management**: Complex interrupt/resume state serialization
3. **Concurrency**: Multiple workflows waiting = resource exhaustion
4. **Simplicity**: Unnecessary complexity when POST-workflow works

**Correct Implementation:**

```python
# ✅ CORRECT APPROACH (Implemented)
# In workflow.py - workflow runs to completion
findings = workflow.run(query)

# In UI/API layer - create pending approvals POST-workflow
for finding in findings:
    approval_manager.create_pending(finding, trace_id, decision_id)

# Human approves/rejects at their leisure via UI
approval_manager.approve(finding_id)  # No workflow blocked
```

---

## 4. Event Sourcing Implementation

### Core Concept

Traditional CRUD systems UPDATE records in place:

```sql
-- Traditional (WRONG for audit)
UPDATE approvals SET status = 'approved' WHERE finding_id = 'X';
```

Event sourcing APPENDS new events:

```sql
-- Event Sourcing (CORRECT)
INSERT INTO approval_events (finding_id, event_type, ...)
VALUES ('X', 'approved', ...);
-- Never UPDATE, never DELETE
```

### Two-Table Model

| Table               | Purpose                                     | Mutability  |
| ------------------- | ------------------------------------------- | ----------- |
| `approval_findings` | Immutable snapshot of the AI recommendation | INSERT only |
| `approval_events`   | Stream of state-change events               | APPEND only |

**Current state** is computed by:

```sql
SELECT * FROM approval_events
WHERE finding_id = ?
ORDER BY event_timestamp DESC, event_id DESC
LIMIT 1
```

### Event Types

```python
class EventType(Enum):
    """
    Types of approval events in the event stream.
    Each event is a NEW ROW - we never UPDATE existing events.
    """
    PENDING_CREATED = "pending_created"   # Finding submitted for approval
    APPROVED = "approved"                  # Manager approved
    REJECTED = "rejected"                  # Manager rejected
    SUPERSEDED = "superseded"              # Replaced by newer finding
    EXPIRED = "expired"                    # v4: Explicit expiration (not time-inferred)
```

### State Transitions

```
                    ┌──────────────┐
                    │              │
        ┌──────────►│   PENDING    │◄──────────┐
        │           │              │           │
        │           └──────┬───────┘           │
        │                  │                   │
        │      ┌───────────┼───────────┐       │
        │      │           │           │       │
        │      ▼           ▼           ▼       │
        │ ┌──────────┐ ┌──────────┐ ┌─────────┐│
        │ │ APPROVED │ │ REJECTED │ │ EXPIRED ││
        │ └──────────┘ └──────────┘ └─────────┘│
        │ (TERMINAL)   (TERMINAL)   (TERMINAL) │
        │                                      │
        │        NEW DECISION FOR SAME         │
        │        (retailer, issue_type)        │
        │                  │                   │
        │                  ▼                   │
        │           ┌──────────────┐           │
        └───────────│  SUPERSEDED  │───────────┘
                    └──────────────┘
                      (TERMINAL)
```

**Transition Rules:**

- `PENDING → APPROVED`: Manager clicks Approve
- `PENDING → REJECTED`: Manager clicks Reject + provides context
- `PENDING → SUPERSEDED`: New finding arrives for same (retailer_id, issue_type)
- `PENDING → EXPIRED`: System/admin explicitly expires (v4)
- `APPROVED → (none)`: Terminal state - IMMUTABLE
- `REJECTED → (none)`: Terminal state - IMMUTABLE
- `SUPERSEDED → (none)`: Terminal state - IMMUTABLE
- `EXPIRED → (none)`: Terminal state - IMMUTABLE (v4)

### Time-Travel Capability

Because every state change is preserved, we can answer:

> "What was the approval status at 3:45 PM yesterday?"

```python
def get_state_at_time(self, finding_id: str, as_of: datetime) -> Optional[ApprovalRecord]:
    """
    Time-travel query: What was the state at a specific time?
    This is why we use event sourcing - we can answer this question.
    """
    result = self._db.execute("""
        SELECT * FROM approval_events
        WHERE finding_id = ? AND event_timestamp <= ?
        ORDER BY event_timestamp DESC
        LIMIT 1
    """, [finding_id, as_of.isoformat()]).fetchone()
    # ... build ApprovalRecord from event
```

---

## 5. Data Classes

### 5.1 ApprovalFinding

**Purpose**: Immutable snapshot of the AI recommendation at submission time.

**Storage**: `approval_findings` table (one row per finding_id)

```python
@dataclass
class ApprovalFinding:
    """
    Immutable snapshot of a finding at submission time.

    This captures the recommendation EXACTLY as it was when submitted.
    Even if the underlying data changes, this record remains frozen.
    """
    # === Identity ===
    finding_id: str              # PRIMARY KEY - UUID from Strategist
    trace_id: str                # Links to DecisionTrace
    decision_id: str             # Groups findings from same workflow run

    # === Retailer Context ===
    retailer_id: str
    retailer_name: str
    tier: str                    # Gold, Silver, Bronze

    # === Recommendation Details ===
    issue_type: str              # CHURN_RISK, CROSS_SELL_GAP, VALUE_DECLINE
    severity: str                # HIGH, MEDIUM, LOW
    confidence_level: str        # HIGH, MEDIUM, LOW (IMMUTABLE - from Strategist)
    recommended_action: str
    action_type: str             # VISIT, CALL, MESSAGE
    suggested_discount: Optional[int] = None
    deadline_description: str = ""

    # === Metadata ===
    created_at: datetime = field(default_factory=datetime.now)
```

**Key Design Decisions:**

1. **`confidence_level` is IMMUTABLE**: Set by Strategist, cannot be changed after submission
2. **Defensive validation in `__post_init__`**:
   ```python
   def __post_init__(self):
       if not self.finding_id:
           raise ValueError("finding_id is required")
       if not self.trace_id:
           raise ValueError("trace_id is required")
       # ... more validation
   ```

### 5.2 ApprovalEvent

**Purpose**: Single event in the approval lifecycle (append-only stream).

**Storage**: `approval_events` table (multiple rows per finding_id)

```python
@dataclass
class ApprovalEvent:
    """
    A single event in the approval lifecycle.
    This is the APPEND-ONLY event stream.
    Every state change creates a NEW event - we never UPDATE.
    """
    event_id: str                # PRIMARY KEY - UUID
    finding_id: str              # FK to approval_findings
    event_type: EventType        # What happened
    event_timestamp: datetime    # When it happened (DB authoritative)

    # === Who acted ===
    actor: str = "system"        # 'system' for auto, user_id for humans

    # === Rejection context (only for REJECTED events) ===
    rejection_category: Optional[RejectionCategory] = None
    manager_context: Optional[str] = None

    # === Supersession context (only for SUPERSEDED events) ===
    superseded_by: Optional[str] = None  # finding_id of replacement
```

**Lifecycle Example:**

```
Event 1: finding_id=ABC, event_type=PENDING_CREATED, timestamp=T1
Event 2: finding_id=ABC, event_type=APPROVED, timestamp=T2, actor="manager"
```

State at T1.5: PENDING (Event 1 is latest before T1.5)
State at T2.5: APPROVED (Event 2 is latest before T2.5)

### 5.3 ApprovalRecord

**Purpose**: Materialized view combining finding + current state for UI rendering.

**Storage**: Not stored directly - computed from ApprovalFinding + latest ApprovalEvent

```python
@dataclass
class ApprovalRecord:
    """
    Materialized view combining finding + current state.

    This is a COMPUTED object, not stored directly.
    Built from: ApprovalFinding + latest ApprovalEvent

    Used by UI for rendering approval cards.
    """
    # From ApprovalFinding
    finding_id: str
    trace_id: str
    decision_id: str
    retailer_id: str
    retailer_name: str
    tier: str
    issue_type: str
    severity: str
    confidence_level: str
    recommended_action: str
    action_type: str
    suggested_discount: Optional[int] = None
    deadline_description: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # From latest ApprovalEvent
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: Optional[datetime] = None
    decided_by: str = "system"
    rejection_category: Optional[RejectionCategory] = None
    manager_context: Optional[str] = None
    superseded_by: Optional[str] = None
    superseded_at: Optional[datetime] = None
```

**Construction Method:**

```python
@classmethod
def from_finding_and_event(cls, finding: ApprovalFinding, event: ApprovalEvent) -> 'ApprovalRecord':
    """Build ApprovalRecord from finding + latest event."""
    # CTO Fix: Defensive programming - fail loudly on invalid state
    if finding is None:
        raise InvalidApprovalState("Cannot build ApprovalRecord: finding is None")
    if event is None:
        raise InvalidApprovalState("Cannot build ApprovalRecord: event is None")

    # Map event type to status
    status_map = {
        EventType.PENDING_CREATED: ApprovalStatus.PENDING,
        EventType.APPROVED: ApprovalStatus.APPROVED,
        EventType.REJECTED: ApprovalStatus.REJECTED,
        EventType.SUPERSEDED: ApprovalStatus.SUPERSEDED,
    }

    return cls(
        finding_id=finding.finding_id,
        # ... copy fields from finding ...
        status=status_map.get(event.event_type, ApprovalStatus.PENDING),
        decided_at=event.event_timestamp if event.event_type != EventType.PENDING_CREATED else None,
        # ... copy fields from event ...
    )
```

---

## 6. ApprovalManager Implementation

### 6.1 Class Overview

```python
class ApprovalManager:
    """
    Event-sourced approval lifecycle manager.

    Two modes:
    - DuckDB-backed (production)
    - In-memory (testing)
    """

    def __init__(
        self,
        db_connection: Any = None,
        trace_validator: Optional[Callable[[str], bool]] = None
    ):
        self._db = db_connection
        self._use_db = db_connection is not None
        self._trace_validator = trace_validator

        # In-memory stores (fallback for testing)
        self._findings: Dict[str, ApprovalFinding] = {}
        self._events: List[ApprovalEvent] = []

        # Idempotency tracking
        self._processed_events: set = set()

        if self._use_db:
            self._ensure_tables_exist()
```

### 6.2 Core Operations

#### 6.2.1 create_pending()

**Purpose**: Submit a new AI recommendation for human approval.

**Algorithm:**

```
1. Validate trace_id (if validator configured)
2. Validate required fields in finding dict
3. Extract confidence_level from finding (not parameter)
4. Get authoritative timestamp from DB
5. Supersede existing PENDING for same (retailer_id, issue_type)
6. Create ApprovalFinding snapshot
7. Create PENDING_CREATED event
8. Atomically write both to DB
9. Update legacy projection table (for compatibility)
10. Return ApprovalRecord
```

**Implementation Details:**

```python
def create_pending(
    self,
    finding: dict,
    trace_id: str,
    decision_id: str,
    confidence_level: str = None  # DEPRECATED - ignored
) -> ApprovalRecord:
    # === Validate trace_id (CTO Fix #3) ===
    if self._trace_validator and not self._trace_validator(trace_id):
        raise InvalidTraceError(f"trace_id '{trace_id}' does not exist")

    # === Extract confidence from finding (CTO Fix #4) ===
    actual_confidence = finding.get('confidence_level')
    if not actual_confidence:
        actual_confidence = confidence_level or 'MEDIUM'  # Fallback

    # === Get authoritative timestamp (CTO Fix: Clock consistency) ===
    now = self._get_db_timestamp()

    # === Supersede existing PENDING (CTO Fix #2: Scoped) ===
    self._supersede_pending_scoped(retailer_id, issue_type, finding_id)

    # === Create finding snapshot ===
    approval_finding = ApprovalFinding(...)

    # === Create PENDING_CREATED event ===
    pending_event = ApprovalEvent(
        event_id=str(uuid.uuid4()),
        finding_id=finding_id,
        event_type=EventType.PENDING_CREATED,
        event_timestamp=now,
        actor="system",
    )

    # === Atomic persistence ===
    self._atomic_write(approval_finding, pending_event)

    return ApprovalRecord.from_finding_and_event(approval_finding, pending_event)
```

#### 6.2.2 approve()

**Purpose**: Human approves a pending recommendation.

**Algorithm:**

```
1. Check idempotency (no duplicate APPROVED events)
2. Get current state
3. Validate finding exists
4. Validate finding is PENDING
5. Get authoritative timestamp from DB
6. Create APPROVED event
7. Append event to stream
8. Mark as processed (idempotency tracking)
9. Update legacy projection (non-authoritative)
10. Return updated ApprovalRecord
```

**Implementation Details:**

```python
def approve(
    self,
    finding_id: str,
    decided_by: str = "manager"
) -> ApprovalRecord:
    # === Idempotency check (CTO Fix) ===
    if self._check_idempotency(finding_id, EventType.APPROVED):
        raise DuplicateApprovalError(
            f"Finding {finding_id} already has APPROVED event"
        )

    current = self._get_current_state(finding_id)
    if current is None:
        raise ApprovalNotFoundError(f"Finding {finding_id} not found")

    if current.status != ApprovalStatus.PENDING:
        raise ApprovalAlreadyDecidedError(
            f"Finding {finding_id} already decided: {current.status.value}"
        )

    # === Get authoritative timestamp ===
    now = self._get_db_timestamp()

    # === Create APPROVED event (append-only) ===
    event = ApprovalEvent(
        event_id=str(uuid.uuid4()),
        finding_id=finding_id,
        event_type=EventType.APPROVED,
        event_timestamp=now,
        actor=decided_by,
    )
    self._append_event(event)
    self._mark_processed(finding_id, EventType.APPROVED)

    # === Update legacy projection ===
    _logger.debug(f"Updating legacy projection: {finding_id} -> approved")
    self._update_legacy_status(finding_id, 'approved', now, decided_by)

    # === Return updated state ===
    finding = self._get_finding(finding_id)
    return ApprovalRecord.from_finding_and_event(finding, event)
```

#### 6.2.3 reject()

**Purpose**: Human rejects a pending recommendation with context.

**Key Difference from approve():**

- Captures `rejection_category` (required)
- Captures `manager_context` (optional free-form notes)
- Context is for **operational analytics only**, NOT for AI feedback

```python
def reject(
    self,
    finding_id: str,
    rejection_category: RejectionCategory,
    manager_context: Optional[str] = None,
    decided_by: str = "manager"
) -> ApprovalRecord:
    # ... similar to approve() ...

    event = ApprovalEvent(
        # ... standard fields ...
        rejection_category=rejection_category,  # WHY rejected
        manager_context=manager_context,        # Free-form notes
    )
    # ...
```

### 6.3 Query Methods

#### 6.3.1 get_pending()

Returns all findings currently in PENDING state.

```python
def get_pending(self) -> List[ApprovalRecord]:
    result = self._db.execute("""
        SELECT * FROM approvals
        WHERE status = 'pending'
        ORDER BY created_at DESC
    """).fetchall()
    # ... convert to ApprovalRecord list
```

#### 6.3.2 get_by_finding_id()

Returns current state of a specific finding.

#### 6.3.3 get_by_retailer()

Returns all approvals for a retailer (full history).

#### 6.3.4 get_audit_log()

Returns audit trail with optional filters:

- `start_date`: Filter by creation date
- `end_date`: Filter by creation date
- `status_filter`: Filter by status

#### 6.3.5 get_event_history()

Returns **full event history** for a finding - the TRUE audit trail.

```python
def get_event_history(self, finding_id: str) -> List[ApprovalEvent]:
    result = self._db.execute("""
        SELECT * FROM approval_events
        WHERE finding_id = ?
        ORDER BY event_timestamp ASC
    """, [finding_id]).fetchall()
    # ...
```

#### 6.3.6 get_state_at_time()

**Time-travel query**: What was the state at a specific time?

```python
def get_state_at_time(self, finding_id: str, as_of: datetime) -> Optional[ApprovalRecord]:
    result = self._db.execute("""
        SELECT * FROM approval_events
        WHERE finding_id = ? AND event_timestamp <= ?
        ORDER BY event_timestamp DESC
        LIMIT 1
    """, [finding_id, as_of.isoformat()]).fetchone()
    # ...
```

#### 6.3.7 get_rejection_analytics()

Returns rejection statistics for operational review.

**CRITICAL**: This data is for human analysis only, NOT for AI feedback.

```python
def get_rejection_analytics(self) -> Dict[str, Any]:
    """
    IMPORTANT: This data is for HUMAN analysis of rejection patterns.
    It is NOT used to modify AI decision-making behavior.

    Returns:
        {
            "total_rejections": int,
            "by_category": {"incorrect_data": 5, "already_handled": 3, ...},
            "by_issue_type": {"CHURN_RISK": 4, "CROSS_SELL_GAP": 2, ...}
        }
    """
    # CTO Fix: Return pure data, no embedded commentary
    return {
        "total_rejections": len(rejections),
        "by_category": by_category,
        "by_issue_type": by_issue_type,
    }
```

### 6.4 Internal Helpers

#### 6.4.1 \_get_db_timestamp()

**Purpose**: Get authoritative timestamp from DB for clock consistency.

**Why**: Prevents drift between Python `datetime.now()` and DB `CURRENT_TIMESTAMP`.

```python
def _get_db_timestamp(self) -> datetime:
    if self._use_db:
        result = self._db.execute("SELECT CURRENT_TIMESTAMP").fetchone()
        return result[0] if result else datetime.now()
    return datetime.now()
```

#### 6.4.2 \_check_idempotency()

**Purpose**: Check if this event would be a duplicate.

```python
def _check_idempotency(self, finding_id: str, event_type: EventType) -> bool:
    if event_type in (EventType.APPROVED, EventType.REJECTED):
        result = self._db.execute("""
            SELECT 1 FROM approval_events
            WHERE finding_id = ? AND event_type = ?
            LIMIT 1
        """, [finding_id, event_type.value]).fetchone()
        return result is not None
    return False
```

#### 6.4.3 \_get_latest_event()

**Purpose**: Get the most recent event for a finding.

**CTO Fix**: Uses `event_id` as tiebreaker for deterministic ordering.

```python
def _get_latest_event(self, finding_id: str) -> Optional[ApprovalEvent]:
    result = self._db.execute("""
        SELECT * FROM approval_events
        WHERE finding_id = ?
        ORDER BY event_timestamp DESC, event_id DESC  -- event_id as tiebreaker
        LIMIT 1
    """, [finding_id]).fetchone()
    # ...
```

#### 6.4.4 \_supersede_pending_scoped()

**Purpose**: Supersede existing PENDING for same (retailer_id, issue_type).

**CTO Fix #2**: Supersession is scoped - a retailer can have multiple pending for different issue types.

```python
def _supersede_pending_scoped(self, retailer_id: str, issue_type: str, new_finding_id: str):
    # Find PENDING findings for same (retailer_id, issue_type)
    result = self._db.execute("""
        SELECT finding_id FROM approvals
        WHERE retailer_id = ?
          AND issue_type = ?
          AND finding_id != ?
          AND status = 'pending'
    """, [retailer_id, issue_type, new_finding_id]).fetchall()

    for (old_finding_id,) in result:
        # Append SUPERSEDED event
        supersede_event = ApprovalEvent(
            event_type=EventType.SUPERSEDED,
            superseded_by=new_finding_id,
            # ...
        )
        self._append_event(supersede_event)

        # Update legacy projection (NON-AUTHORITATIVE)
        _logger.debug(f"Updating legacy projection: {old_finding_id} -> superseded")
        # ...
```

#### 6.4.5 \_atomic_write()

**Purpose**: Atomically write finding and event together.

```python
def _atomic_write(self, finding: ApprovalFinding, event: ApprovalEvent):
    """
    CTO Fix: All multi-writes must be transactional.
    If any write fails, all are rolled back.
    """
    try:
        self._save_finding(finding)
        self._append_event(event)

        # Legacy projection update (non-authoritative)
        _logger.debug(f"Updating legacy projection for {finding.finding_id}")
        self._save_legacy_record(finding, event)
    except Exception as e:
        _logger.error(f"Atomic write failed: {e}")
        raise
```

---

## 7. Exception Hierarchy

### 7.1 ApprovalAlreadyDecidedError

**When**: Attempting to modify an already-decided approval.

**System Invariant Enforcement**: Human decisions are irreversible.

```python
class ApprovalAlreadyDecidedError(Exception):
    """
    Raised when attempting to modify an already-decided approval.
    Once APPROVED/REJECTED/SUPERSEDED, no further state changes allowed.
    """
    pass
```

### 7.2 ApprovalNotFoundError

**When**: Approval record doesn't exist.

```python
class ApprovalNotFoundError(Exception):
    """Raised when approval record doesn't exist."""
    pass
```

### 7.3 InvalidTraceError

**When**: trace_id validation fails.

```python
class InvalidTraceError(Exception):
    """Raised when trace_id validation fails."""
    pass
```

### 7.4 InvalidApprovalState

**When**: Approval data is in an inconsistent state (indicates bug or data corruption).

```python
class InvalidApprovalState(Exception):
    """
    Raised when approval data is in an inconsistent state.
    This indicates a bug or data corruption - should never happen
    in normal operation.
    """
    pass
```

### 7.5 InvalidApprovalPayload

**When**: Input data for an approval is malformed.

```python
class InvalidApprovalPayload(Exception):
    """
    Raised when input data for an approval is malformed.
    Used for:
    - Missing required fields
    - Invalid field formats
    - API input validation
    """
    pass
```

### 7.6 DuplicateApprovalError

**When**: Attempting to create a duplicate approval event (idempotency violation).

```python
class DuplicateApprovalError(Exception):
    """
    Raised when attempting to create a duplicate approval event.
    Idempotency guard: Same (finding_id, event_type) combination
    cannot be written twice.
    """
    pass
```

---

## 8. Trace Integration

### 8.1 ApprovalTraceEntry

**Location**: `graph/trace.py`

**Purpose**: Link approval events back to the originating trace/decision.

```python
@dataclass
class ApprovalTraceEntry:
    """
    Trace entry for HITL approval events.

    ════════════════════════════════════════════════════════════════════════
    CRITICAL: APPROVAL IS POST-WORKFLOW, NOT A WORKFLOW STEP

    This entry is APPENDED after workflow completes, not during execution.
    Approvals happen OUTSIDE the workflow as governance events.
    ════════════════════════════════════════════════════════════════════════
    """
    timestamp: datetime
    finding_id: str  # PRIMARY KEY - links to specific finding
    approval_status: str  # 'approved' | 'rejected' | 'superseded'
    decided_by: str = "manager"

    # Context for OPERATIONAL ANALYTICS (not model feedback)
    rejection_category: Optional[str] = None
    manager_context: Optional[str] = None

    # Supersession tracking
    superseded_by: Optional[str] = None
```

### 8.2 Post-Finalization Writing

**Special Exception**: Approval events can be written AFTER trace finalization.

```python
def write_approval_event(self, entry: ApprovalTraceEntry) -> None:
    """
    ════════════════════════════════════════════════════════════════════════
    SPECIAL: This CAN be written AFTER finalization.
    ════════════════════════════════════════════════════════════════════════

    Approvals happen OUTSIDE the workflow, AFTER it completes.
    This is NOT a violation of write-only-during-execution because:
    - The workflow is already complete
    - We're appending audit events, not modifying decisions
    - The trace is being used as an audit log, not execution context
    """
    # Note: We do NOT check _check_not_finalized() here
    self._trace.approval_entries.append(entry)
```

---

## 9. Database Schema

### 9.1 Authoritative Tables (Event Sourcing)

#### approval_findings

```sql
-- AUTHORITATIVE: Immutable finding snapshots
CREATE TABLE approval_findings (
    finding_id VARCHAR PRIMARY KEY,       -- UUID from Strategist
    trace_id VARCHAR NOT NULL,            -- Links to DecisionTrace
    decision_id VARCHAR NOT NULL DEFAULT '', -- Groups findings from same run
    retailer_id VARCHAR NOT NULL,
    retailer_name VARCHAR NOT NULL,
    tier VARCHAR DEFAULT 'Bronze',
    issue_type VARCHAR NOT NULL,          -- CHURN_RISK, CROSS_SELL_GAP, etc.
    severity VARCHAR NOT NULL,            -- HIGH, MEDIUM, LOW
    confidence_level VARCHAR NOT NULL,    -- HIGH, MEDIUM, LOW (immutable)
    recommended_action TEXT NOT NULL,
    action_type VARCHAR NOT NULL,         -- VISIT, CALL, MESSAGE
    suggested_discount INTEGER,
    deadline_description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### approval_events

```sql
-- AUTHORITATIVE: Append-only event stream
-- NO UPDATE. NO DELETE. EVER.
CREATE TABLE approval_events (
    event_id VARCHAR PRIMARY KEY,         -- UUID
    finding_id VARCHAR NOT NULL,          -- FK to approval_findings
    event_type VARCHAR NOT NULL,          -- pending_created, approved, rejected, superseded
    event_timestamp TIMESTAMP NOT NULL,   -- DB authoritative
    actor VARCHAR DEFAULT 'system',       -- 'system' or user_id
    rejection_category VARCHAR,           -- Only for REJECTED
    manager_context TEXT,                 -- Only for REJECTED (analytics only)
    superseded_by VARCHAR,                -- Only for SUPERSEDED
    sequence_num INTEGER DEFAULT 0        -- For deterministic ordering
);

-- Idempotency: Only one decision per finding
CREATE UNIQUE INDEX idx_events_idempotency
ON approval_events(finding_id, event_type)
WHERE event_type IN ('approved', 'rejected');

-- Efficient latest-event queries with deterministic ordering
CREATE INDEX idx_events_finding_ts
ON approval_events(finding_id, event_timestamp DESC, event_id DESC);
```

### 9.2 Non-Authoritative Projection Table

```sql
-- ⚠️ NON-AUTHORITATIVE: Projection for backward compatibility
-- DO NOT use for audit. Use approval_events instead.
CREATE TABLE approvals (
    finding_id VARCHAR PRIMARY KEY,
    trace_id VARCHAR NOT NULL,
    decision_id VARCHAR,
    retailer_id VARCHAR NOT NULL,
    retailer_name VARCHAR NOT NULL,
    tier VARCHAR DEFAULT 'Bronze',
    issue_type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    confidence_level VARCHAR DEFAULT 'MEDIUM',
    recommended_action TEXT NOT NULL,
    action_type VARCHAR NOT NULL,
    suggested_discount INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deadline_description VARCHAR,
    status VARCHAR DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    decided_at TIMESTAMP,
    decided_by VARCHAR DEFAULT 'manager',
    rejection_category VARCHAR,
    manager_context TEXT,
    superseded_by VARCHAR,
    superseded_at TIMESTAMP
);
```

**Why Keep Legacy Table?**

- Backward compatibility with existing queries
- Simpler queries for common operations (get_pending())
- Transition period until all consumers migrate to event tables

**Warning on Every Update:**

```python
_logger.debug(f"Updating legacy projection: {finding_id} -> approved")
```

---

## 10. CTO Corrections (v1 → v2 → v3 → v4)

### 10.1 Version History

| Version | Focus            | Key Changes                                                  |
| ------- | ---------------- | ------------------------------------------------------------ |
| v1      | Initial          | Basic CRUD approval system                                   |
| v2      | Event Sourcing   | Append-only events, scoped supersession                      |
| v3      | Audit-Grade      | Idempotency, clock consistency, defensive programming        |
| v4      | Production-Grade | Transactional writes, constraint-driven idempotency, EXPIRED |

### 10.2 v2 Corrections (Event Sourcing)

#### CTO Fix #1: TRUE APPEND-ONLY

**Wrong (v1)**:

```python
def approve(self, finding_id):
    self._db.execute("""
        UPDATE approvals SET status = 'approved' WHERE finding_id = ?
    """, [finding_id])  # WRONG - mutates existing record
```

**Correct (v2)**:

```python
def approve(self, finding_id):
    event = ApprovalEvent(event_type=EventType.APPROVED, ...)
    self._db.execute("""
        INSERT INTO approval_events VALUES (?, ?, ?, ...)
    """, [event.event_id, ...])  # CORRECT - new row
```

#### CTO Fix #2: SCOPED SUPERSESSION

**Wrong (v1)**:

```python
# Supersede ALL pending for retailer
self._supersede_pending_for_retailer(retailer_id, new_finding_id)
```

**Correct (v2)**:

```python
# Supersede only same (retailer_id, issue_type)
self._supersede_pending_scoped(retailer_id, issue_type, new_finding_id)
```

**Why**: A retailer can have CHURN_RISK and CROSS_SELL_GAP pending simultaneously.

#### CTO Fix #3: REFERENTIAL INTEGRITY

**Added**: Optional trace_id validation callback.

```python
def __init__(self, db_connection, trace_validator=None):
    self._trace_validator = trace_validator

def create_pending(self, finding, trace_id, ...):
    if self._trace_validator and not self._trace_validator(trace_id):
        raise InvalidTraceError(f"trace_id '{trace_id}' does not exist")
```

#### CTO Fix #4: CONFIDENCE IMMUTABLE

**Wrong (v1)**:

```python
def create_pending(self, finding, trace_id, confidence_level='MEDIUM'):
    record.confidence_level = confidence_level  # Can be overridden
```

**Correct (v2)**:

```python
def create_pending(self, finding, trace_id, confidence_level=None):
    # confidence_level parameter is DEPRECATED and ignored
    actual_confidence = finding.get('confidence_level') or 'MEDIUM'
```

### 10.3 v3 Corrections (Audit-Grade)

#### CTO Fix #5: IDEMPOTENCY ENFORCEMENT

**Problem**: Double-click on Approve button could create inconsistent state.

**Solution**: Check for duplicate events before writing.

```python
def _check_idempotency(self, finding_id: str, event_type: EventType) -> bool:
    if self._check_idempotency(finding_id, EventType.APPROVED):
        raise DuplicateApprovalError(
            f"Finding {finding_id} already has APPROVED event"
        )
```

#### CTO Fix #6: CLOCK SOURCE CONSISTENCY

**Problem**: Python `datetime.now()` and DB `CURRENT_TIMESTAMP` can drift.

**Solution**: Single clock source (DB authoritative).

```python
def _get_db_timestamp(self) -> datetime:
    if self._use_db:
        result = self._db.execute("SELECT CURRENT_TIMESTAMP").fetchone()
        return result[0] if result else datetime.now()
    return datetime.now()
```

#### CTO Fix #7: DETERMINISTIC EVENT ORDERING

**Problem**: Events with same timestamp could return in different order.

**Solution**: Use `event_id` as secondary sort key.

```python
result = self._db.execute("""
    SELECT * FROM approval_events
    WHERE finding_id = ?
    ORDER BY event_timestamp DESC, event_id DESC  -- event_id as tiebreaker
    LIMIT 1
""", [finding_id]).fetchone()
```

#### CTO Fix #8: DEFENSIVE PROGRAMMING

**Problem**: Silent failures on NULL data.

**Solution**: Fail loudly with semantic errors.

```python
@classmethod
def from_finding_and_event(cls, finding, event):
    if finding is None:
        raise InvalidApprovalState("Cannot build ApprovalRecord: finding is None")
    if event is None:
        raise InvalidApprovalState("Cannot build ApprovalRecord: event is None")
```

#### CTO Fix #9: PURE DATA ANALYTICS

**Problem**: Mixing data with commentary in analytics response.

**Wrong (v2)**:

```python
return {
    "total_rejections": len(rejections),
    "by_category": by_category,
    "note": "This data is for operational analytics only."  # WRONG
}
```

**Correct (v3)**:

```python
return {
    "total_rejections": len(rejections),
    "by_category": by_category,
    # No note - pure data only
}
```

### 10.4 v4 Corrections (Production-Grade)

CTO Final Hardening Review determined that Phase 5 was "architecturally correct but not yet operationally final." The following seven issues were addressed to make Phase 5 truly production-grade.

#### CTO Fix #10: SINGLE SOURCE OF TRUTH

**Problem**: Legacy `approvals` projection was mutable, violating event sourcing invariant.

**Solution**: Establish clear hierarchy:

1. **Events are THE source** - `approval_events` table is authoritative
2. **Projection is computed** - Legacy status is read-only, derived from events
3. **Never mutate projection independently** - All state changes go through events

```python
# Module docstring now documents this:
"""
SINGLE SOURCE OF TRUTH:
- approval_events → Authoritative event stream
- approval_findings → Immutable snapshot at submission time
- approvals (legacy) → READ-ONLY projection, NEVER mutate directly
"""
```

#### CTO Fix #11: TRANSACTIONAL WRITES

**Problem**: `_atomic_write` method was not actually atomic - failure mid-write could leave inconsistent state.

**Solution**: True transaction support with begin/commit/rollback.

```python
def _begin_transaction(self):
    """Begin a database transaction."""
    if self._use_db:
        self._db.execute("BEGIN TRANSACTION")
        self._in_transaction = True

def _commit_transaction(self):
    """Commit the current transaction."""
    if self._use_db and self._in_transaction:
        self._db.execute("COMMIT")
        self._in_transaction = False

def _rollback_transaction(self):
    """Rollback the current transaction."""
    if self._use_db and self._in_transaction:
        self._db.execute("ROLLBACK")
        self._in_transaction = False
```

**Usage in create_pending:**

```python
def create_pending(self, finding, trace_id, decision_id, ...):
    if self._use_db:
        try:
            self._begin_transaction()
            self._supersede_pending_scoped(...)
            self._save_finding(approval_finding)
            self._append_event(pending_event)
            self._commit_transaction()
        except Exception as e:
            self._rollback_transaction()
            raise TransactionError(f"Failed to create pending: {e}") from e
```

#### CTO Fix #12: POST-FINALIZATION WRITE GUARDS

**Problem**: `ApprovalTraceEntry` could be written with stale timestamps after trace finalization.

**Solution**: Validation in `ApprovalTraceEntry.__post_init__` and `write_approval_event()`.

```python
@dataclass
class ApprovalTraceEntry:
    def __post_init__(self):
        # v4: finding_id is required
        if not self.finding_id:
            raise ValueError("finding_id is required for ApprovalTraceEntry")

        # v4: status must be valid
        valid_statuses = {'pending', 'approved', 'rejected', 'superseded', 'expired'}
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {valid_statuses}")

def write_approval_event(self, entry: ApprovalTraceEntry) -> None:
    # v4: Validate timestamp ordering for post-finalization writes
    if self._trace.completed_at:
        if entry.timestamp < self._trace.completed_at:
            raise InvalidTraceOperation(
                f"Cannot write approval event with timestamp {entry.timestamp} "
                f"before trace completion {self._trace.completed_at}"
            )
```

#### CTO Fix #13: CONSTRAINT-DRIVEN IDEMPOTENCY

**Problem**: v3 idempotency used SELECT-before-INSERT, which has race conditions.

**Solution**: Database constraint as source of truth.

```python
def approve(self, finding_id, decided_by="manager"):
    # Pre-check is ADVISORY only
    current = self._get_current_state(finding_id)
    if current.status != ApprovalStatus.PENDING:
        if current.status == ApprovalStatus.APPROVED:
            raise DuplicateApprovalError(f"Finding {finding_id} already APPROVED")
        else:
            raise ApprovalAlreadyDecidedError(f"Finding {finding_id} already decided")

    # v4: Constraint-driven - INSERT will fail if constraint violated
    try:
        self._append_event(event)
    except Exception as e:
        error_str = str(e).lower()
        if 'unique' in error_str or 'duplicate' in error_str or 'constraint' in error_str:
            raise DuplicateApprovalError(f"Constraint violation: {finding_id}")
        raise
```

**Key Insight**: The pre-check is advisory (handles 99.9% of cases cleanly). The DB constraint is the true guard (handles race conditions).

#### CTO Fix #14: DECISION_ID REQUIRED

**Problem**: `decision_id` was optional but semantically required for grouping findings.

**Solution**: Enforce as NOT NULL at dataclass and method level.

```python
@dataclass
class ApprovalFinding:
    def __post_init__(self):
        # v4: decision_id is REQUIRED and IMMUTABLE
        if not self.decision_id:
            raise ValueError("decision_id is required (v4: enforced as NOT NULL)")

def create_pending(self, finding, trace_id, decision_id, ...):
    # v4: decision_id is REQUIRED
    if not decision_id:
        raise DecisionIdRequiredError("decision_id is required (v4: NOT NULL)")
```

**New Exception:**

```python
class DecisionIdRequiredError(ApprovalError):
    """Raised when decision_id is not provided (v4: required field)."""
    pass
```

#### CTO Fix #15: EXPIRED EVENT TYPE

**Problem**: Expiration was inferred, not explicit in the event stream.

**Solution**: Add `EXPIRED` to `EventType` enum and `expire()` method.

```python
class EventType(Enum):
    PENDING_CREATED = "pending_created"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"  # v4: Explicit expiration event

def expire(self, finding_id: str, reason: str = "manual_expiration") -> ApprovalRecord:
    """
    Expire a pending finding (v4 CTO Fix).

    Expiration is now an explicit EVENT, not inferred from time.
    Only PENDING findings can be expired.
    """
    current = self._get_current_state(finding_id)
    if current is None:
        raise ApprovalNotFoundError(f"Finding {finding_id} not found")

    if current.status != ApprovalStatus.PENDING:
        raise ApprovalAlreadyDecidedError(
            f"Cannot expire finding {finding_id}: already {current.status.value}"
        )

    event = ApprovalEvent(
        event_id=str(uuid.uuid4()),
        finding_id=finding_id,
        event_type=EventType.EXPIRED,
        event_timestamp=self._get_db_timestamp(),
        actor="system",
        manager_context=reason,
    )
    self._append_event(event)
    # ... return updated record
```

#### CTO Fix #16: GET_PENDING READS EVENTS

**Problem**: `get_pending()` was reading from legacy projection table.

**Solution**: Aligned with Issue #10 - projection is now computed from events, so `get_pending()` inherently reads authoritative state.

### 10.5 v4 Exception Hierarchy

```python
class ApprovalError(Exception):
    """Base class for all approval-related errors."""

class ApprovalNotFoundError(ApprovalError):
    """Finding does not exist."""

class ApprovalAlreadyDecidedError(ApprovalError):
    """Cannot change a finding that already has a human decision (cross-decision)."""

class DuplicateApprovalError(ApprovalError):
    """Duplicate operation on same finding (idempotent rejection)."""

class InvalidApprovalState(ApprovalError):
    """Internal consistency violation."""

class TransactionError(ApprovalError):
    """Database transaction failed (v4)."""

class DecisionIdRequiredError(ApprovalError):
    """decision_id is required but was not provided (v4)."""

class InvalidTraceError(ApprovalError):
    """trace_id validation failed."""
```

### 10.6 v4 Test Coverage

New test class: `TestCTOv4ProductionGrade` with 13 tests:

| Test                                             | CTO Fix | Purpose                                            |
| ------------------------------------------------ | ------- | -------------------------------------------------- |
| test_decision_id_required_raises_error           | #14     | Empty decision_id raises error                     |
| test_decision_id_none_raises_error               | #14     | None decision_id raises error                      |
| test_expired_event_type_exists                   | #15     | EXPIRED in EventType enum                          |
| test_expire_pending_finding                      | #15     | expire() method works                              |
| test_cannot_expire_already_decided               | #15     | Can't expire APPROVED/REJECTED                     |
| test_approval_trace_entry_validates_finding_id   | #12     | Trace entry requires finding_id                    |
| test_approval_trace_entry_validates_status       | #12     | Trace entry validates status                       |
| test_approval_trace_entry_valid_statuses         | #12     | 'expired' is valid status                          |
| test_trace_writer_validates_timestamp_ordering   | #12     | Timestamp must be after finalization               |
| test_trace_writer_allows_valid_post_finalization | #12     | Valid post-finalization allowed                    |
| test_constraint_driven_idempotency_in_memory     | #13     | Idempotency works in-memory too                    |
| test_new_exceptions_exported                     | #11,#14 | TransactionError, DecisionIdRequiredError exported |
| test_approval_finding_requires_decision_id       | #14     | ApprovalFinding validates decision_id              |

---

## 11. Test Suite Architecture

### 11.1 Test File Location

`tests/test_phase5_approval.py` - 59 tests total (v4: +13 from v3's 46)

### 11.2 Test Categories

| Category                    | Tests | Purpose                         |
| --------------------------- | ----- | ------------------------------- |
| TestFindingIdGeneration     | 3     | UUID generation and uniqueness  |
| TestApprovalRecord          | 4     | Data class validation           |
| TestApprovalManagerInMemory | 8     | In-memory manager operations    |
| TestApprovalManagerDuckDB   | 4     | DuckDB persistence              |
| TestApprovalTraceEntry      | 4     | Trace integration               |
| TestExecutionSummary        | 1     | Summary statistics              |
| TestBusinessRules           | 3     | CTO-mandated rules              |
| TestEdgeCases               | 5     | Error handling                  |
| TestIntegration             | 2     | Full workflows                  |
| TestEventSourcing           | 4     | Event sourcing features         |
| TestBackwardCompatibility   | 2     | API stability                   |
| TestCTOv3Invariants         | 6     | Audit-grade requirements        |
| TestCTOv4ProductionGrade    | 13    | Production-grade hardening (v4) |

### 11.3 Key Test Examples

#### Test: System Invariant - Human Decisions Irreversible

```python
def test_system_invariant_human_decisions_irreversible(self, db_manager, sample_finding):
    """
    CTO v3 SYSTEM INVARIANT: Once a human decision exists,
    the system may only append knowledge — never reinterpret it.
    """
    record = db_manager.create_pending(finding=sample_finding, ...)

    # Human approves
    db_manager.approve(record.finding_id)

    # Verify no API exists to "undo" or "change" the decision
    with pytest.raises((ApprovalAlreadyDecidedError, DuplicateApprovalError)):
        db_manager.approve(record.finding_id)  # Cannot re-approve

    with pytest.raises((ApprovalAlreadyDecidedError, DuplicateApprovalError)):
        db_manager.reject(record.finding_id, RejectionCategory.OTHER)  # Cannot reject after approve

    # The record status is final
    final_record = db_manager.get_by_finding_id(record.finding_id)
    assert final_record.status == ApprovalStatus.APPROVED
```

#### Test: Idempotency Enforcement

```python
def test_double_submit_approval_is_idempotent(self, db_manager, sample_finding):
    """
    CTO v3: Duplicate approval requests must be rejected with DuplicateApprovalError.
    """
    record = db_manager.create_pending(finding=sample_finding, ...)

    # First approval succeeds
    approved = db_manager.approve(record.finding_id)
    assert approved.status == ApprovalStatus.APPROVED

    # Second attempt raises DuplicateApprovalError, not generic error
    with pytest.raises(DuplicateApprovalError) as exc_info:
        db_manager.approve(record.finding_id)

    assert 'APPROVED' in str(exc_info.value)
```

#### Test: Scoped Supersession

```python
def test_scoped_supersession_by_issue_type(self, db_manager, sample_finding):
    """
    Supersession should be scoped by (retailer_id, issue_type).
    CTO Fix #2: A retailer can have multiple pending for different issue types.
    """
    # Create CHURN_RISK pending
    churn_finding = sample_finding.copy()
    churn_finding['insight_type'] = 'CHURN_RISK'
    record1 = db_manager.create_pending(finding=churn_finding, ...)

    # Create CROSS_SELL_GAP pending (same retailer)
    crosssell_finding = sample_finding.copy()
    crosssell_finding['insight_type'] = 'CROSS_SELL_GAP'
    record2 = db_manager.create_pending(finding=crosssell_finding, ...)

    # BOTH should be pending (different issue types)
    pending = db_manager.get_pending()
    assert len(pending) == 2
```

---

## 12. API Reference

### 12.1 Public Classes

| Class               | Purpose                    | Import From   |
| ------------------- | -------------------------- | ------------- |
| `ApprovalRecord`    | Materialized view for UI   | `persistence` |
| `ApprovalFinding`   | Immutable finding snapshot | `persistence` |
| `ApprovalEvent`     | Single event in stream     | `persistence` |
| `ApprovalManager`   | Lifecycle manager          | `persistence` |
| `ApprovalStatus`    | Status enum                | `persistence` |
| `EventType`         | Event type enum            | `persistence` |
| `RejectionCategory` | Rejection reason enum      | `persistence` |

### 12.2 Public Exceptions

| Exception                     | When Raised                |
| ----------------------------- | -------------------------- |
| `ApprovalAlreadyDecidedError` | Modifying decided approval |
| `ApprovalNotFoundError`       | Finding doesn't exist      |
| `InvalidTraceError`           | Invalid trace_id           |
| `InvalidApprovalState`        | Data corruption            |
| `InvalidApprovalPayload`      | Malformed input            |
| `DuplicateApprovalError`      | Idempotency violation      |

### 12.3 Public Functions

| Function                | Purpose                  |
| ----------------------- | ------------------------ |
| `generate_finding_id()` | Create UUID for findings |

---

## 13. File-by-File Analysis

### 13.1 persistence/approvals.py

**Lines**: ~1,434
**Purpose**: Core approval system implementation

**Structure**:

```
Lines 1-65:     Module docstring with SYSTEM INVARIANT
Lines 66-75:    Imports
Lines 76-122:   Enums (ApprovalStatus, EventType, RejectionCategory)
Lines 123-232:  ApprovalFinding dataclass
Lines 233-294:  ApprovalEvent dataclass
Lines 295-430:  ApprovalRecord dataclass
Lines 431-527:  Exceptions
Lines 528-910:  ApprovalManager class
Lines 911-1400: ApprovalManager internal methods
Lines 1401-1434: Utility functions
```

### 13.2 persistence/**init**.py

**Lines**: ~80
**Purpose**: Module exports

**Exports**:

- All data classes
- ApprovalManager
- All enums
- All exceptions
- `generate_finding_id`

### 13.3 docs/PHASE5_HITL_CONTRACT.md

**Lines**: ~508
**Purpose**: Design contract documentation

**Sections**:

- Executive Summary
- System Invariant
- Architecture Overview
- CTO Corrections
- Data Model
- State Transitions
- API Contract
- UI Integration
- Database Schema
- Test Coverage
- Migration Path

### 13.4 tests/test_phase5_approval.py

**Lines**: ~1,112
**Purpose**: Comprehensive test suite

**Test Classes**: 12
**Total Tests**: 46

### 13.5 graph/trace.py (Phase 5 additions)

**Lines added**: ~80
**Purpose**: ApprovalTraceEntry and trace integration

**Key Addition**: `write_approval_event()` method that can be called post-finalization.

---

## Appendix A: Rejection Categories

| Category          | When to Use                      |
| ----------------- | -------------------------------- |
| `INCORRECT_DATA`  | "The data shown is wrong"        |
| `ALREADY_HANDLED` | "I already dealt with this"      |
| `WRONG_PRIORITY`  | "Not important right now"        |
| `WRONG_ACTION`    | "I'd do something different"     |
| `NOT_APPLICABLE`  | "Doesn't apply to this retailer" |
| `OTHER`           | Free-form reason                 |

---

## Appendix B: Confidence Levels

| Level  | UI Badge  | Meaning                                   |
| ------ | --------- | ----------------------------------------- |
| HIGH   | 🟢 Green  | Strong evidence from multiple data points |
| MEDIUM | 🟡 Orange | Moderate evidence - review recommended    |
| LOW    | 🔴 Red    | Weak evidence - verify before acting      |

---

## Appendix C: Glossary

| Term             | Definition                                    |
| ---------------- | --------------------------------------------- |
| **Finding**      | AI-generated recommendation from Strategist   |
| **Event**        | Immutable record of state change              |
| **Projection**   | Derived view from events (non-authoritative)  |
| **Supersession** | Replacing old finding with new one            |
| **Idempotency**  | Same operation can't create duplicate records |
| **Time-Travel**  | Query state as of past timestamp              |
| **HITL**         | Human-in-the-Loop                             |

---

## Document Revision History

| Version | Date     | Changes                             |
| ------- | -------- | ----------------------------------- |
| 1.0     | Jan 2026 | Initial comprehensive documentation |

---

_End of Phase 5 Technical Documentation_
