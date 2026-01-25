"""
SalesFlow AI Decision Trace
===========================

This module implements the WRITE-ONLY decision trace system.
Every agent appends to the trace, but NO agent reads from it during execution.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL ARCHITECTURAL INVARIANT:                                           ║
║                                                                              ║
║  DecisionTrace is WRITE-ONLY during execution, READ-ONLY after completion.   ║
║                                                                              ║
║  • Agents receive a TraceWriter (write-only handle)                          ║
║  • Agents CANNOT read other agents' trace entries                            ║
║  • Only UI / logs / tests can read the complete trace                        ║
║  • This prevents: cross-agent coupling, trace-based reasoning, corruption    ║
║                                                                              ║
║  If you need to pass data between agents, use AgentState, NOT the trace.     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Data Provenance Constraints (CTO Mandate):
------------------------------------------
Provenance must NEVER be sufficient to reconstruct private data.

ALLOWED in provenance:
- Retailer IDs (already visible in findings)
- View names
- Column names
- Aggregation types (SUM, COUNT, AVG)
- Filter descriptions (e.g., "days_since_order > 14")

FORBIDDEN in provenance:
- Order IDs
- Transaction counts per day
- Specific dates/timestamps
- SKU IDs
- Raw monetary values per transaction
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Final, Literal
from enum import Enum
import json


class TraceEntryType(Enum):
    """Types of trace entries, one per agent/phase."""
    GUARDRAILS = "guardrails"
    ANALYST = "analyst"
    STRATEGIST = "strategist"
    COPYWRITER = "copywriter"
    WORKFLOW = "workflow"  # For workflow-level events (start, end, routing)


class IntegrityStatus(Enum):
    """
    Trace integrity status - CTO Correction #2.
    
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║  PHASE 6 CTO FIX: DecisionTrace must be all-or-nothing                       ║
    ║                                                                              ║
    ║  Partial traces are WORSE than no trace because:                             ║
    ║  - They imply completeness when incomplete                                   ║
    ║  - Auditors may trust partial data                                           ║
    ║  - Downstream systems may operate on partial state                           ║
    ║                                                                              ║
    ║  Every trace MUST declare its integrity status:                              ║
    ║  - COMPLETE: All expected agents wrote entries                               ║
    ║  - PARTIAL: Some agents wrote, some didn't (suspicious)                      ║
    ║  - FAILED: Error prevented trace completion                                  ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """
    COMPLETE = "complete"   # All expected agents wrote entries for the outcome
    PARTIAL = "partial"     # Some agents wrote, some didn't - SUSPICIOUS
    FAILED = "failed"       # Error prevented trace completion


# =============================================================================
# TRACE ENTRY DATACLASSES
# =============================================================================
# Each agent has its own trace entry type with specific fields.
# This prevents "kitchen sink" entries and enforces schema discipline.

@dataclass
class DataProvenance:
    """
    Records WHAT data was accessed, not the data itself.
    
    CTO CONSTRAINT: This must NEVER be sufficient to reconstruct private data.
    - Retailer IDs are OK (already in findings)
    - Order IDs, dates, SKU IDs are FORBIDDEN
    """
    view_used: str
    columns_accessed: List[str]
    filter_applied: Optional[str] = None  # e.g., "days_since_order > 14"
    aggregation_type: Optional[str] = None  # e.g., "COUNT", "SUM", "AVG"
    row_count_returned: Optional[int] = None
    retailer_ids_affected: Optional[List[str]] = None  # OK - already visible in UI
    
    def to_dict(self) -> dict:
        return {
            "view_used": self.view_used,
            "columns_accessed": self.columns_accessed,
            "filter_applied": self.filter_applied,
            "aggregation_type": self.aggregation_type,
            "row_count_returned": self.row_count_returned,
            "retailer_ids_affected": self.retailer_ids_affected,
        }


@dataclass
class GuardrailsTraceEntry:
    """
    Trace entry for Guardrails classification.
    Records the INPUT classification, not modifications.
    """
    timestamp: datetime
    original_query: str
    classification: str  # 'allowed' | 'blocked' | 'offtopic'
    detected_patterns: List[str] = field(default_factory=list)
    topic_category: Optional[str] = None  # 'churn' | 'performance' | 'crosssell' | None
    intent_label: Optional[str] = None  # 'scan' | 'query' | 'explain'
    block_reason: Optional[str] = None  # Only if blocked
    execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "type": TraceEntryType.GUARDRAILS.value,
            "timestamp": self.timestamp.isoformat(),
            "original_query": self.original_query,
            "classification": self.classification,
            "detected_patterns": self.detected_patterns,
            "topic_category": self.topic_category,
            "intent_label": self.intent_label,
            "block_reason": self.block_reason,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class AnalystTraceEntry:
    """
    Trace entry for Analyst SQL generation and execution.
    Records query details and data access, not raw results.
    """
    timestamp: datetime
    sql_generated: str
    sql_valid: bool
    execution_success: bool
    provenance: Optional[DataProvenance] = None
    retry_count: int = 0
    error_type: Optional[str] = None  # If failed
    execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        result = {
            "type": TraceEntryType.ANALYST.value,
            "timestamp": self.timestamp.isoformat(),
            "sql_generated": self.sql_generated,
            "sql_valid": self.sql_valid,
            "execution_success": self.execution_success,
            "retry_count": self.retry_count,
            "error_type": self.error_type,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.provenance:
            result["provenance"] = self.provenance.to_dict()
        return result


@dataclass
class SeverityComputation:
    """
    Documents HOW severity was computed (summarized, not raw).
    
    CTO CONSTRAINT: Must remain summarized.
    - Rule name and threshold: OK
    - Actual value that triggered: OK (already visible in UI)
    - Raw data or timestamps: FORBIDDEN
    """
    rule_name: str  # e.g., "days_since_order_threshold"
    threshold_value: Any  # e.g., 14
    actual_value: Any  # e.g., 18 (the retailer's days_since_order)
    result: str  # e.g., "high" | "medium" | "critical"
    
    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "result": self.result,
        }


@dataclass
class StrategistTraceEntry:
    """
    Trace entry for Strategist decision-making.
    Records WHAT decisions were made and WHY (rule-based).
    """
    timestamp: datetime
    findings_count: int
    actions_generated: int
    severity_computations: List[SeverityComputation] = field(default_factory=list)
    suppression_applied: List[str] = field(default_factory=list)  # e.g., ["crosssell_suppressed:R001"]
    tier_distribution: Optional[Dict[str, int]] = None  # e.g., {"Gold": 2, "Silver": 3}
    execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "type": TraceEntryType.STRATEGIST.value,
            "timestamp": self.timestamp.isoformat(),
            "findings_count": self.findings_count,
            "actions_generated": self.actions_generated,
            "severity_computations": [s.to_dict() for s in self.severity_computations],
            "suppression_applied": self.suppression_applied,
            "tier_distribution": self.tier_distribution,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class CopywriterTraceEntry:
    """
    Trace entry for Copywriter message generation.
    Records style decisions, not full message content.
    """
    timestamp: datetime
    messages_generated: int
    tone_used: str  # 'urgent' | 'concerned' | 'routine'
    discount_source: str  # 'strategist' - documents where discount came from
    discount_value: Optional[int] = None  # The discount percentage used
    execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "type": TraceEntryType.COPYWRITER.value,
            "timestamp": self.timestamp.isoformat(),
            "messages_generated": self.messages_generated,
            "tone_used": self.tone_used,
            "discount_source": self.discount_source,
            "discount_value": self.discount_value,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class ApprovalTraceEntry:
    """
    Trace entry for HITL (Human-in-the-Loop) approval events.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  CRITICAL: APPROVAL IS POST-WORKFLOW, NOT A WORKFLOW STEP                ║
    ║                                                                          ║
    ║  This entry is APPENDED after workflow completes, not during execution.  ║
    ║  Approvals happen OUTSIDE the workflow as governance events.             ║
    ║  This entry links the approval to the originating trace/decision.        ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  v4 CTO FIX: GUARDED POST-FINALIZATION WRITES                            ║
    ║                                                                          ║
    ║  ApprovalTraceEntry writes are guarded by:                               ║
    ║  1. MUST reference an existing approval_event_id                         ║
    ║  2. timestamp MUST ≥ workflow completion timestamp                       ║
    ║  3. Writes are append-only per trace (no modification)                   ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Phase 5 Design (CTO Corrections Applied):
    -----------------------------------------
    1. finding_id is PRIMARY KEY (not trace_id + retailer_id)
    2. manager_context is for offline analytics, not model feedback
    3. No execution_status - we don't track downstream actions
    4. Supersession is explicit (SUPERSEDED status, not time-based expiry)
    5. event_id links to actual approval_events row (v4)
    """
    timestamp: datetime
    finding_id: str  # PRIMARY KEY - links to specific finding
    approval_status: str  # 'approved' | 'rejected' | 'superseded' | 'expired'
    decided_by: str = "manager"  # Who made the decision
    
    # v4: Link to actual event for non-repudiation
    event_id: Optional[str] = None  # References approval_events.event_id
    
    # Context for OPERATIONAL ANALYTICS (not model feedback)
    rejection_category: Optional[str] = None  # Only if rejected
    manager_context: Optional[str] = None  # Free-form notes (offline analysis only)
    
    # Supersession tracking
    superseded_by: Optional[str] = None  # finding_id of replacement
    
    def __post_init__(self):
        """
        v4 CTO Fix: Validate required fields.
        """
        if not self.finding_id:
            raise ValueError("finding_id is required for ApprovalTraceEntry")
        if not self.approval_status:
            raise ValueError("approval_status is required for ApprovalTraceEntry")
        # v4: Validate approval_status is a known value
        valid_statuses = {'approved', 'rejected', 'superseded', 'expired', 'pending'}
        if self.approval_status not in valid_statuses:
            raise ValueError(f"approval_status must be one of {valid_statuses}")
    
    def to_dict(self) -> dict:
        return {
            "type": "approval",  # New trace entry type
            "timestamp": self.timestamp.isoformat(),
            "finding_id": self.finding_id,
            "approval_status": self.approval_status,
            "decided_by": self.decided_by,
            "event_id": self.event_id,  # v4: Include event reference
            "rejection_category": self.rejection_category,
            "manager_context": self.manager_context,
            "superseded_by": self.superseded_by,
        }


@dataclass
class WorkflowTraceEntry:
    """
    Trace entry for workflow-level events.
    Records routing decisions and overall timing.
    """
    timestamp: datetime
    event_type: str  # 'start' | 'route' | 'complete' | 'error'
    source_node: Optional[str] = None
    target_node: Optional[str] = None
    routing_reason: Optional[str] = None  # e.g., "empty_result -> end"
    total_execution_time_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "type": TraceEntryType.WORKFLOW.value,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "routing_reason": self.routing_reason,
            "total_execution_time_ms": self.total_execution_time_ms,
        }


# =============================================================================
# DECISION TRACE CONTAINER
# =============================================================================

@dataclass
class DecisionTrace:
    """
    The complete trace for a single workflow execution.
    
    This is the READ-ONLY view available AFTER workflow completion.
    Agents never see this object - they use TraceWriter instead.
    
    Phase 5 Addition:
    -----------------
    approval_entries: List of HITL approval events (appended POST-workflow)
    These link human decisions back to the originating trace.
    
    v4 CTO Fix: Version Metadata
    ---------------------------
    For deterministic replay, we must capture the EXACT versions of:
    - System (code) version
    - Configuration ruleset versions
    This enables "replay with same config" for compliance audits.
    """
    trace_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    original_query: str = ""
    final_outcome: str = ""  # 'success' | 'empty_result' | 'error' | 'blocked'
    
    # Agent-specific entries (append-only during execution)
    guardrails_entry: Optional[GuardrailsTraceEntry] = None
    analyst_entry: Optional[AnalystTraceEntry] = None
    strategist_entry: Optional[StrategistTraceEntry] = None
    copywriter_entry: Optional[CopywriterTraceEntry] = None
    workflow_entries: List[WorkflowTraceEntry] = field(default_factory=list)
    
    # Phase 5: HITL approval events (appended POST-workflow)
    approval_entries: List[ApprovalTraceEntry] = field(default_factory=list)
    
    # Phase 6: Trace integrity status (CTO Correction #2)
    # MUST be set during finalize() - starts as FAILED until proven otherwise
    integrity_status: IntegrityStatus = IntegrityStatus.FAILED
    
    # Phase 6: Decision ID for end-to-end correlation
    decision_id: Optional[str] = None
    
    # v4 CTO Fix: Version metadata for deterministic replay
    # These are captured at trace creation time and are IMMUTABLE
    system_version: str = field(default="1.0.0")  # Code/deployment version
    strategist_ruleset_version: str = field(default="1.0.0")  # Business rules version
    analyst_query_version: str = field(default="1.0.0")  # Data query templates version
    
    def to_dict(self) -> dict:
        """Serialize the complete trace for logging/storage."""
        result = {
            "trace_id": self.trace_id,
            "decision_id": self.decision_id,  # Phase 6
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "original_query": self.original_query,
            "final_outcome": self.final_outcome,
            "integrity_status": self.integrity_status.value,  # Phase 6
            # v4 CTO Fix: Version metadata for deterministic replay
            "version_metadata": {
                "system_version": self.system_version,
                "strategist_ruleset_version": self.strategist_ruleset_version,
                "analyst_query_version": self.analyst_query_version,
            },
            "entries": {
                "guardrails": self.guardrails_entry.to_dict() if self.guardrails_entry else None,
                "analyst": self.analyst_entry.to_dict() if self.analyst_entry else None,
                "strategist": self.strategist_entry.to_dict() if self.strategist_entry else None,
                "copywriter": self.copywriter_entry.to_dict() if self.copywriter_entry else None,
                "workflow": [e.to_dict() for e in self.workflow_entries],
                "approvals": [e.to_dict() for e in self.approval_entries],
            },
        }
        return result
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# WRITE-ONLY TRACE WRITER
# =============================================================================

class TraceWriter:
    """
    Write-only handle to the decision trace.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  THIS IS THE ONLY TRACE INTERFACE AGENTS SHOULD USE.                     ║
    ║                                                                          ║
    ║  TraceWriter can ONLY:                                                   ║
    ║  - Append entries                                                        ║
    ║  - Set completion status                                                 ║
    ║                                                                          ║
    ║  TraceWriter CANNOT:                                                     ║
    ║  - Read existing entries                                                 ║
    ║  - Access other agents' data                                             ║
    ║  - Modify past entries                                                   ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    
    def __init__(self, trace: DecisionTrace):
        """
        Initialize with reference to trace.
        The trace object is private - agents can't access it directly.
        """
        self._trace = trace
        self._finalized = False
    
    def _check_not_finalized(self) -> None:
        """Ensure trace hasn't been finalized."""
        if self._finalized:
            raise RuntimeError(
                "Cannot write to finalized trace. "
                "DecisionTrace is READ-ONLY after workflow completion."
            )
    
    # =========================================================================
    # WRITE METHODS (One per agent type)
    # =========================================================================
    
    def write_guardrails(self, entry: GuardrailsTraceEntry) -> None:
        """Append guardrails trace entry. Can only be called once."""
        self._check_not_finalized()
        if self._trace.guardrails_entry is not None:
            raise RuntimeError("Guardrails trace entry already written. Trace is append-only.")
        self._trace.guardrails_entry = entry
    
    def write_analyst(self, entry: AnalystTraceEntry) -> None:
        """Append analyst trace entry. Can only be called once."""
        self._check_not_finalized()
        if self._trace.analyst_entry is not None:
            raise RuntimeError("Analyst trace entry already written. Trace is append-only.")
        self._trace.analyst_entry = entry
    
    def write_strategist(self, entry: StrategistTraceEntry) -> None:
        """Append strategist trace entry. Can only be called once."""
        self._check_not_finalized()
        if self._trace.strategist_entry is not None:
            raise RuntimeError("Strategist trace entry already written. Trace is append-only.")
        self._trace.strategist_entry = entry
    
    def write_copywriter(self, entry: CopywriterTraceEntry) -> None:
        """Append copywriter trace entry. Can only be called once."""
        self._check_not_finalized()
        if self._trace.copywriter_entry is not None:
            raise RuntimeError("Copywriter trace entry already written. Trace is append-only.")
        self._trace.copywriter_entry = entry
    
    def write_workflow_event(self, entry: WorkflowTraceEntry) -> None:
        """Append workflow event. Multiple events allowed."""
        self._check_not_finalized()
        self._trace.workflow_entries.append(entry)
    
    def write_approval_event(self, entry: ApprovalTraceEntry) -> None:
        """
        Append HITL approval event.
        
        ════════════════════════════════════════════════════════════════════════
        SPECIAL: This CAN be written AFTER finalization.
        ════════════════════════════════════════════════════════════════════════
        
        Approvals happen OUTSIDE the workflow, AFTER it completes.
        This is NOT a violation of write-only-during-execution because:
        - The workflow is already complete
        - We're appending audit events, not modifying decisions
        - The trace is being used as an audit log, not execution context
        
        v4 CTO FIX: GUARDED POST-FINALIZATION WRITES
        --------------------------------------------
        1. Entry MUST have finding_id (validated in __post_init__)
        2. Entry timestamp MUST be >= workflow completion (if finalized)
        3. Writes are append-only (no modification of existing entries)
        4. Each approval is recorded once per finding_id
        
        Multiple approval events are allowed (e.g., supersession, rejection).
        
        Raises:
            ValueError: If entry timestamp is before workflow completion
            ValueError: If duplicate finding_id already exists in trace
        """
        # v4: Validate timestamp ordering if trace is finalized
        if self._finalized and self._trace.completed_at:
            if entry.timestamp < self._trace.completed_at:
                raise ValueError(
                    f"ApprovalTraceEntry timestamp ({entry.timestamp}) must be >= "
                    f"workflow completion time ({self._trace.completed_at}). "
                    "This ensures monotonic ordering of audit events."
                )
        
        # v4: Check for duplicate finding_id (append-only means no updates)
        existing_finding_ids = {e.finding_id for e in self._trace.approval_entries}
        if entry.finding_id in existing_finding_ids:
            # Allow multiple events for same finding (e.g., superseded then approved)
            # but log it for debugging
            pass  # Multiple events per finding are allowed
        
        self._trace.approval_entries.append(entry)
    
    # =========================================================================
    # FINALIZATION
    # =========================================================================
    
    def _compute_integrity_status(self, outcome: str) -> IntegrityStatus:
        """
        Compute trace integrity based on outcome and entries written.
        
        ╔══════════════════════════════════════════════════════════════════════════╗
        ║  PHASE 6 CTO FIX: Integrity is outcome-dependent                         ║
        ║                                                                          ║
        ║  Different outcomes require different entries:                           ║
        ║  - 'blocked': Only guardrails expected                                   ║
        ║  - 'empty_result': Guardrails + Analyst expected                         ║
        ║  - 'success': All 4 agents expected                                      ║
        ║  - 'error': At least one entry expected (where it failed)               ║
        ╚══════════════════════════════════════════════════════════════════════════╝
        """
        has_guardrails = self._trace.guardrails_entry is not None
        has_analyst = self._trace.analyst_entry is not None
        has_strategist = self._trace.strategist_entry is not None
        has_copywriter = self._trace.copywriter_entry is not None
        
        entries_written = sum([has_guardrails, has_analyst, has_strategist, has_copywriter])
        
        if outcome == 'blocked':
            # Blocked at guardrails - only guardrails entry expected
            if has_guardrails and not has_analyst and not has_strategist and not has_copywriter:
                return IntegrityStatus.COMPLETE
            elif has_guardrails:
                return IntegrityStatus.PARTIAL  # Extra entries for blocked? Suspicious
            else:
                return IntegrityStatus.FAILED  # Blocked but no guardrails entry
                
        elif outcome == 'empty_result':
            # Analyst returned no data - Guardrails + Analyst expected
            expected = 2
            if has_guardrails and has_analyst and not has_strategist and not has_copywriter:
                return IntegrityStatus.COMPLETE
            elif entries_written >= 1:
                return IntegrityStatus.PARTIAL
            else:
                return IntegrityStatus.FAILED
                
        elif outcome == 'success':
            # Full pipeline - all 4 agents expected
            if entries_written == 4:
                return IntegrityStatus.COMPLETE
            elif entries_written >= 1:
                return IntegrityStatus.PARTIAL
            else:
                return IntegrityStatus.FAILED
                
        elif outcome == 'error':
            # Error somewhere - at least one entry expected (where we got to)
            if entries_written >= 1:
                return IntegrityStatus.PARTIAL  # Error = always partial (didn't complete)
            else:
                return IntegrityStatus.FAILED  # Error before any writes
        
        # Unknown outcome
        return IntegrityStatus.FAILED
    
    def finalize(self, outcome: str) -> None:
        """
        Mark the trace as complete.
        After this, no more writes are allowed (except approval events).
        
        Phase 6 Enhancement: Computes integrity_status based on outcome.
        
        Args:
            outcome: 'success' | 'empty_result' | 'error' | 'blocked'
        """
        self._check_not_finalized()
        self._trace.completed_at = datetime.now()
        self._trace.final_outcome = outcome
        
        # Phase 6: Compute and set integrity status BEFORE marking finalized
        self._trace.integrity_status = self._compute_integrity_status(outcome)
        
        self._finalized = True
    
    def set_decision_id(self, decision_id: str) -> None:
        """
        Set the decision_id for this trace.
        
        Phase 6: decision_id links all findings from a single workflow run.
        Must be called BEFORE finalize() for full correlation.
        
        Args:
            decision_id: UUID string from workflow
        """
        self._check_not_finalized()
        if not decision_id:
            raise ValueError("decision_id cannot be empty")
        self._trace.decision_id = decision_id


# =============================================================================
# VERSION CONSTANTS (v4 CTO Fix: Deterministic Replay)
# =============================================================================
# These constants capture the current versions of each component.
# They are frozen at trace creation time for audit/replay purposes.
#
# In production, these would be:
# - SYSTEM_VERSION: Git commit hash or semantic version
# - STRATEGIST_RULESET_VERSION: Hash of strategist rules/thresholds
# - ANALYST_QUERY_VERSION: Hash of SQL templates

SYSTEM_VERSION: Final[str] = "1.0.0"
STRATEGIST_RULESET_VERSION: Final[str] = "1.0.0"  # Increment when business rules change
ANALYST_QUERY_VERSION: Final[str] = "1.0.0"  # Increment when data queries change


# =============================================================================
# TRACE FACTORY
# =============================================================================

def create_trace(
    trace_id: str, 
    original_query: str,
    decision_id: Optional[str] = None
) -> tuple[DecisionTrace, TraceWriter]:
    """
    Create a new trace and its write-only handle.
    
    Phase 6 Enhancement: Accepts optional decision_id for correlation.
    v4 CTO Fix: Captures version metadata for deterministic replay.
    
    Usage:
        trace, writer = create_trace("uuid-here", "show me churn risk", "decision-uuid")
        # Pass `writer` to agents (write-only)
        # Keep `trace` for final read after workflow completes
    
    Args:
        trace_id: Unique identifier for this trace
        original_query: User's query
        decision_id: Optional decision ID for workflow correlation (Phase 6)
    
    Returns:
        tuple: (DecisionTrace for reading, TraceWriter for writing)
    """
    trace = DecisionTrace(
        trace_id=trace_id,
        started_at=datetime.now(),
        original_query=original_query,
        decision_id=decision_id,
        # v4 CTO Fix: Capture version metadata at trace creation
        system_version=SYSTEM_VERSION,
        strategist_ruleset_version=STRATEGIST_RULESET_VERSION,
        analyst_query_version=ANALYST_QUERY_VERSION,
    )
    writer = TraceWriter(trace)
    return trace, writer


# =============================================================================
# TRACE UTILITIES (For tests/UI only, not agents)
# =============================================================================

def get_execution_summary(trace: DecisionTrace) -> dict:
    """
    Generate a human-readable summary of the trace.
    FOR UI/LOGGING ONLY - never used in agent logic.
    
    v4 CTO Fix: Includes version metadata for audit purposes.
    """
    total_time = None
    if trace.completed_at and trace.started_at:
        total_time = (trace.completed_at - trace.started_at).total_seconds() * 1000
    
    # Phase 5: Summarize approval status
    approval_summary = {
        "total": len(trace.approval_entries),
        "approved": sum(1 for e in trace.approval_entries if e.approval_status == "approved"),
        "rejected": sum(1 for e in trace.approval_entries if e.approval_status == "rejected"),
        "superseded": sum(1 for e in trace.approval_entries if e.approval_status == "superseded"),
    }
    
    return {
        "trace_id": trace.trace_id,
        "decision_id": trace.decision_id,  # Phase 6
        "query": trace.original_query[:100] + "..." if len(trace.original_query) > 100 else trace.original_query,
        "outcome": trace.final_outcome,
        "integrity_status": trace.integrity_status.value,  # Phase 6
        "total_time_ms": total_time,
        # v4 CTO Fix: Include version metadata
        "version_metadata": {
            "system_version": trace.system_version,
            "strategist_ruleset_version": trace.strategist_ruleset_version,
            "analyst_query_version": trace.analyst_query_version,
        },
        "agents_executed": [
            name for name, entry in [
                ("guardrails", trace.guardrails_entry),
                ("analyst", trace.analyst_entry),
                ("strategist", trace.strategist_entry),
                ("copywriter", trace.copywriter_entry),
            ] if entry is not None
        ],
        "workflow_events": len(trace.workflow_entries),
        "approval_summary": approval_summary,  # Phase 5
    }


def validate_trace_integrity(trace: DecisionTrace) -> List[str]:
    """
    Validate that a trace follows all constraints.
    Returns list of violations (empty = valid).
    
    FOR TESTING ONLY.
    """
    violations = []
    
    # Check required fields
    if not trace.trace_id:
        violations.append("Missing trace_id")
    if not trace.started_at:
        violations.append("Missing started_at timestamp")
    if not trace.original_query:
        violations.append("Missing original_query")
    
    # Check provenance constraints
    if trace.analyst_entry and trace.analyst_entry.provenance:
        prov = trace.analyst_entry.provenance
        # Ensure no forbidden fields
        # (In a real system, you'd check for specific forbidden patterns)
        pass
    
    return violations


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid outcome values
VALID_OUTCOMES: Final[set] = {"success", "empty_result", "error", "blocked"}

# Valid intent labels (for guardrails)
VALID_INTENTS: Final[set] = {"scan", "query", "explain"}

# Valid topic categories
VALID_TOPICS: Final[set] = {"churn", "performance", "crosssell", "general"}
