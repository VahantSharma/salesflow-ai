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
    }

Usage:
    from graph.state import AgentState, create_initial_state
    
    initial_state = create_initial_state("Show churning retailers")
    # State is passed through nodes, each adding their outputs
"""

from typing import TypedDict, List, Optional, Any, Annotated
from operator import add
from datetime import datetime


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


def create_initial_state(query: str) -> AgentState:
    """
    Create a fresh state for a new query.
    
    Args:
        query: User's natural language question
        
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
        chat_history=[]
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

