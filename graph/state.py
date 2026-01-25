"""
Workflow State Definition

Responsibility:
- Define the typed state schema for LangGraph
- Ensure type safety across agent boundaries
- Provide clear interface documentation
- Support state inspection and debugging

State Design Philosophy:
- Every field has a clear purpose
- Messages accumulate (for conversation history)
- Intermediate outputs are preserved (for debugging)
- Error states are explicit (not hidden in strings)
- Errors accumulate for traceability (List[Dict])

╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 4 ADDITION: Decision Trace                                            ║
║                                                                              ║
║  Decision trace is handled separately from AgentState to enforce the         ║
║  WRITE-ONLY constraint during execution.                                     ║
║                                                                              ║
║  • Agents receive a TraceWriter (write-only handle) via node parameters      ║
║  • Agents CANNOT read the trace during execution                             ║
║  • Only workflow completion returns the full trace for UI/logging            ║
║                                                                              ║
║  The trace is NOT stored in AgentState to prevent accidental reads.          ║
╚══════════════════════════════════════════════════════════════════════════════╝

State Schema:
    AgentState {
        # User Input
        query: str                    # Original user question
        
        # Guardrails Output
        guardrails_result: dict       # Classification and sanitization
        
        # Analyst Output  
        sql_query: str                # Generated SQL
        view_used: str                # Which view was queried (for strategist context)
        query_results: DataFrame      # SQL execution results
        result_metadata: dict         # {row_count, execution_time_ms}
        analyst_error: str | None     # Error if SQL failed
        
        # Strategist Output
        insight: dict                 # Structured insight
        recommended_action: str       # One specific action
        confidence_level: str         # HIGH | MEDIUM | LOW
        
        # Copywriter Output
        messages: dict                # Message variants
        
        # Control Flow
        current_node: str             # For debugging
        retry_count: int              # Self-correction counter
        workflow_complete: bool       # Terminal state flag
        
        # Error Tracking (accumulated across workflow)
        errors: List[dict]            # {stage, error_type, message, timestamp}
        
        # Conversation (for multi-turn)
        chat_history: List[dict]      # Previous messages
        
        # Phase 4: Trace ID (reference only, not the trace itself)
        trace_id: str | None          # For correlation, NOT for reading trace
    }

Usage:
    from graph.state import AgentState, create_initial_state
    
    initial_state = create_initial_state("Show churning retailers")
    # State is passed through nodes, each adding their outputs
"""

from typing import TypedDict, List, Optional, Any, Annotated
from operator import add
from datetime import datetime


# =============================================================================
# FIX #3: SUMMARY TYPEDDICT (STRONG TYPING FOR UI CONTRACT)
# =============================================================================
# Summary MUST be typed to enforce contract with UI.
# UI reads these fields directly - they MUST exist if summary is not None.
# If you add a field here, Strategist._compute_summary() MUST populate it.
# =============================================================================
class Summary(TypedDict, total=False):
    """
    Pre-computed summary statistics from Strategist.
    
    UI consumes these directly - no recomputation allowed.
    All counts reflect POST-business-rule findings (e.g., after cross-sell suppression).
    
    INVARIANT: Every field here MUST be populated by Strategist._compute_summary().
    """
    # Issue counts
    total_issues: int           # Total findings after business rules
    churn_risks: int            # Count of CHURN_RISK findings
    crosssell_opportunities: int  # Count of CROSS_SELL_GAP findings  
    value_declines: int         # Count of VALUE_DECLINE findings
    
    # Severity breakdown
    high_severity_count: int    # Findings with severity=HIGH
    medium_severity_count: int  # Findings with severity=MEDIUM
    low_severity_count: int     # Findings with severity=LOW
    
    # Tier impact (ALL tiers must be counted)
    gold_tier_affected: int     # Findings affecting Gold tier retailers
    silver_tier_affected: int   # Findings affecting Silver tier retailers
    bronze_tier_affected: int   # Findings affecting Bronze tier retailers (FIX: Added)


class AgentState(TypedDict):
    """
    Typed state container for the multi-agent workflow.
    
    This state is passed between all nodes in the LangGraph.
    Each agent adds its outputs to specific fields.
    """
    
    # === User Input ===
    query: str  # Original natural language query from user
    
    # === Guardrails Stage ===
    guardrails_result: Optional[dict]  # Classification result
    is_on_topic: Optional[bool]  # Quick access to topic classification
    sanitized_query: Optional[str]  # Cleaned query for processing
    
    # === Analyst Stage ===
    sql_query: Optional[str]  # Generated SQL query
    view_used: Optional[str]  # Which view was queried (v_churn_candidates, etc.)
    query_results: Optional[Any]  # DataFrame with results (Any to avoid pandas import)
    result_metadata: Optional[dict]  # {row_count: int, execution_time_ms: float, is_empty: bool}
    analyst_error: Optional[str]  # Error message if SQL failed
    analyst_error_type: Optional[str]  # SQL_ERROR, EMPTY_RESULT, VALIDATION_ERROR, VIEW_VIOLATION
    analyst_retry_count: int  # Number of SQL generation retries (max 2)
    
    # === Strategist Stage ===
    # Input contract: strategist receives {query, sql, view_used, results, result_metadata}
    insight: Optional[dict]  # Structured insight from analysis
    insight_type: Optional[str]  # CHURN_RISK, CROSS_SELL_GAP, VALUE_DECLINE
    priority: Optional[str]  # P1_CRITICAL, P2_HIGH, P3_MEDIUM, P4_LOW
    recommended_action: Optional[str]  # Single recommended action
    action_type: Optional[str]  # VISIT, CALL, MESSAGE
    evidence: Optional[List[str]]  # Supporting data points
    business_impact: Optional[str]  # Impact in business terms (e.g., "₹47,000 at risk")
    confidence_level: Optional[str]  # HIGH, MEDIUM, LOW - affects copywriter tone
    # === Summary (Pre-computed for UI - UI must NOT recompute) ===
    # FIX #3: Typed as Summary for strong contract enforcement
    summary: Optional[Summary]  # Typed summary - see Summary TypedDict above
    
    # === Copywriter Stage ===
    messages: Optional[dict]  # Message variants (primary, whatsapp, internal_notes)
    primary_message: Optional[str]  # Main message to display
    
    # === Control Flow ===
    current_node: str  # Current processing stage (for debugging)
    workflow_complete: bool  # Whether workflow has finished
    should_interrupt: bool  # Human-in-the-loop flag
    
    # === Error Tracking (Accumulated) ===
    # Each error: {stage: str, error_type: str, message: str, timestamp: str, recoverable: bool}
    errors: Annotated[List[dict], add]  # Errors accumulate across workflow
    
    # === Global Error State ===
    error: Optional[str]  # Fatal error message (workflow cannot continue)
    error_stage: Optional[str]  # Which stage had fatal error
    
    # === Conversation History (for multi-turn) ===
    chat_history: Annotated[List[dict], add]  # Accumulates messages
    
    # === Phase 4: Trace Reference ===
    # NOTE: This is the trace ID only, NOT the trace itself.
    # The actual trace is managed separately via TraceWriter to enforce WRITE-ONLY.
    # Agents must NOT read trace data during execution.
    trace_id: Optional[str]  # Correlation ID for audit trail
    
    # === Phase 6: Decision ID (End-to-End Correlation) ===
    # decision_id groups all findings from a single workflow run.
    # Generated at workflow start, flows through to ApprovalManager.
    # This enables: "Show all findings from this decision" queries.
    decision_id: Optional[str]  # Workflow correlation ID


def create_initial_state(query: str, trace_id: Optional[str] = None, decision_id: Optional[str] = None) -> AgentState:
    """
    Create a fresh state for a new query.
    
    Args:
        query: User's natural language question
        trace_id: Optional trace ID for audit trail (Phase 4)
        decision_id: Optional decision ID for workflow correlation (Phase 6)
        
    Returns:
        Initialized AgentState ready for workflow
    """
    return AgentState(
        # User Input
        query=query,
        
        # Guardrails
        guardrails_result=None,
        is_on_topic=None,
        sanitized_query=None,
        
        # Analyst
        sql_query=None,
        view_used=None,
        query_results=None,
        result_metadata=None,
        analyst_error=None,
        analyst_error_type=None,
        analyst_retry_count=0,
        
        # Strategist
        insight=None,
        insight_type=None,
        priority=None,
        recommended_action=None,
        action_type=None,
        evidence=None,
        business_impact=None,
        confidence_level=None,
        summary=None,  # Pre-computed counts for UI
        
        # Copywriter
        messages=None,
        primary_message=None,
        
        # Control Flow
        current_node="START",
        workflow_complete=False,
        should_interrupt=False,
        
        # Error Tracking
        errors=[],
        error=None,
        error_stage=None,
        
        # Conversation
        chat_history=[],
        
        # Phase 4: Trace Reference
        trace_id=trace_id,
        
        # Phase 6: Decision ID
        decision_id=decision_id
    )


def add_error_to_state(
    state: AgentState,
    stage: str,
    error_type: str,
    message: str,
    recoverable: bool = True
) -> dict:
    """
    Create an error entry to append to state errors.
    
    Use this in nodes to record errors without stopping workflow.
    
    Args:
        state: Current state (unused but for context)
        stage: Which stage errored (e.g., "analyst", "strategist")
        error_type: Type of error (e.g., "SQL_ERROR", "VALIDATION_ERROR")
        message: Human-readable error message
        recoverable: Whether workflow can continue after this error
        
    Returns:
        Error dict to append to state["errors"]
    """
    return {
        "stage": stage,
        "error_type": error_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "recoverable": recoverable
    }

