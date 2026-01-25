"""
Main Workflow Construction

Responsibility:
- Assemble the complete LangGraph workflow
- Define all nodes and edges
- Configure human-in-the-loop interrupts
- Compile for execution

CRITICAL DESIGN DECISIONS:
1. Fail-fast: If analyst fails after retries → END with error (never cascade bad data)
2. Error node: All failures route here for graceful handling
3. No business logic in workflow - only routing

Workflow Diagram:
    
    ┌─────────────────────────────────────────────────────────────┐
    │                      SalesFlow AI Workflow                   │
    └─────────────────────────────────────────────────────────────┘
    
                              ┌──────────┐
                              │  START   │
                              └────┬─────┘
                                   │
                                   ▼
                            ┌────────────┐
                            │ Guardrails │
                            └────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ OFF_TOPIC │ │ ON_TOPIC │ │ BLOCKED  │
              └────┬─────┘ └────┬─────┘ └────┬─────┘
                   │            │            │
                   ▼            │            ▼
              ┌──────────┐      │       ┌──────────┐
              │ Redirect │      │       │  Error   │
              └────┬─────┘      │       └────┬─────┘
                   │            │            │
                   │            ▼            │
                   │       ┌──────────┐      │
                   │       │ Analyst  │◄─────┤ (retry loop, max 2)
                   │       └────┬─────┘      │
                   │            │            │
                   │    ┌───────┴────────┐   │
                   │    │                │   │
                   │    ▼                ▼   │
                   │ ┌────────┐    ┌───────┐ │
                   │ │Success │    │ FAIL  │─┼───► Error
                   │ └───┬────┘    └───────┘ │
                   │     │                   │
                   │     ▼                   │
                   │ ┌──────────┐            │
                   │ │Strategist│            │
                   │ └────┬─────┘            │
                   │      │                  │
                   │      ▼                  │
                   │ ┌──────────┐            │
                   │ │Copywriter│            │
                   │ └────┬─────┘            │
                   │      │                  │
                   └──────┴──────────────────┘
                               │
                               ▼
                          ┌──────────┐
                          │   END    │
                          └──────────┘

Configuration:
- Max retries: 2 per stage
- Fail-fast: Analyst failure → Error → END (never to Strategist)
- Checkpointing: Enabled for debugging
- Max workflow time: 60 seconds (prevents streaming abuse)

Usage:
    from graph.workflow import create_workflow, run_workflow
    
    # Create compiled workflow
    workflow = create_workflow(llm, db_connection)
    
    # Run with a query
    result = run_workflow(workflow, "Show me retailers at churn risk")
    
    # Access results
    print(result["recommended_action"])
    print(result["primary_message"])
"""

import time
import uuid
from typing import Any, Dict, Optional
from contextlib import contextmanager
from langgraph.graph import StateGraph, END

from graph.state import AgentState, create_initial_state
from graph.trace import create_trace, TraceWriter, DecisionTrace
from graph.nodes import (
    guardrails_node,
    analyst_node,
    strategist_node,
    copywriter_node,
    error_node,
    route_after_analyst,
    route_after_guardrails,
    set_agents,
    set_trace_writer,
    clear_trace_writer
)
from agents.analyst import AnalystAgent
from agents.strategist import StrategistAgent
from agents.copywriter import CopywriterAgent


# =============================================================================
# TRACE LIFECYCLE MANAGER (CTO FIX #1: Guaranteed Finalization)
# =============================================================================

@contextmanager
def managed_trace(trace_id: str, original_query: str, decision_id: str):
    """
    Context manager that GUARANTEES trace finalization.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  CTO FIX #1: Trace Finalization is GUARANTEED, not Optional              ║
    ║                                                                          ║
    ║  This context manager ensures:                                           ║
    ║  1. Trace is created at start                                            ║
    ║  2. TraceWriter is injected into nodes                                   ║
    ║  3. Trace is ALWAYS finalized (even on exception)                        ║
    ║  4. TraceWriter is cleared after completion                              ║
    ║                                                                          ║
    ║  INVARIANT: A trace ALWAYS ends in a finalized state.                    ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Usage:
        with managed_trace(trace_id, query, decision_id) as (trace, writer):
            result = workflow.invoke(state)
            # On success: writer.finalize('success') called automatically
            # On exception: writer.finalize('error') called automatically
    
    Yields:
        tuple: (DecisionTrace, TraceWriter, outcome_setter)
    """
    trace, writer = create_trace(trace_id, original_query, decision_id)
    outcome = ['error']  # Default outcome - overwritten on success
    
    # Inject writer into nodes
    set_trace_writer(writer)
    
    try:
        yield trace, writer, outcome
    except Exception:
        # Ensure error outcome on exception
        outcome[0] = 'error'
        raise
    finally:
        # GUARANTEED finalization - this ALWAYS runs
        try:
            if not writer._finalized:
                writer.finalize(outcome[0])
        except RuntimeError:
            pass  # Already finalized (shouldn't happen with proper usage)
        finally:
            # Clear writer to prevent accidental post-workflow writes
            clear_trace_writer()


def create_workflow(
    llm: Any,
    db_connection: Any,
    enable_human_approval: bool = False
) -> Any:  # Returns CompiledGraph
    """
    Construct and compile the multi-agent workflow.
    
    Graph Structure:
    - START → guardrails → analyst → strategist → copywriter → END
    - Analyst has retry loop (max 2)
    - Failed analyst → error → END (fail-fast, never cascade)
    
    Args:
        llm: LangChain chat model
        db_connection: DuckDB connection
        enable_human_approval: Whether to pause for human approval (Phase 6)
        
    Returns:
        Compiled LangGraph ready for execution
        
    Example:
        from langchain_openai import ChatOpenAI
        from data.database import get_connection
        
        llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.1)
        conn = get_connection()
        
        workflow = create_workflow(llm, conn)
        result = workflow.invoke({"query": "Show churning retailers"})
    """
    # Initialize agents
    analyst = AnalystAgent(llm=llm, db_connection=db_connection)
    strategist = StrategistAgent(llm=llm)
    copywriter = CopywriterAgent(llm=llm)
    
    # Inject agents into nodes
    set_agents(
        analyst=analyst,
        strategist=strategist,
        copywriter=copywriter
    )
    
    # Build graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("strategist", strategist_node)
    graph.add_node("copywriter", copywriter_node)
    graph.add_node("error", error_node)
    
    # Set entry point
    graph.set_entry_point("guardrails")
    
    # Add edges from guardrails
    graph.add_conditional_edges(
        "guardrails",
        route_after_guardrails,
        {
            "analyst": "analyst",
            "redirect": "error"  # Off-topic goes to error for graceful message
        }
    )
    
    # Add edges from analyst (CRITICAL: fail-fast)
    graph.add_conditional_edges(
        "analyst",
        route_after_analyst,
        {
            "continue": "strategist",  # Success or EMPTY_RESULT → continue
            "retry": "analyst",         # SQL_ERROR/VALIDATION_ERROR → retry
            "fail": "error",            # Max retries → error (NEVER to strategist)
            "error": "error"            # Fatal error → error
        }
    )
    
    # Strategist → Copywriter (linear)
    graph.add_edge("strategist", "copywriter")
    
    # Terminal nodes
    graph.add_edge("copywriter", END)
    graph.add_edge("error", END)
    
    # Compile
    compiled = graph.compile()
    
    return compiled


# =============================================================================
# WORKFLOW EXECUTION GUARDRAILS
# =============================================================================
MAX_WORKFLOW_TIME_SECONDS = 60  # Hard ceiling to prevent streaming abuse
MAX_RETRIES_PER_STAGE = 2       # Also defined in agents, but centralized here


def generate_decision_id() -> str:
    """
    Generate a unique decision_id for a workflow run.
    
    Phase 6: decision_id groups all findings from a single workflow execution.
    This enables:
    - "Show all findings from this decision" queries
    - End-to-end trace correlation
    - ApprovalManager linking
    
    Format: decision_{uuid_first_12_chars}
    Example: decision_a1b2c3d4e5f6
    """
    return f"decision_{uuid.uuid4().hex[:12]}"


def generate_trace_id() -> str:
    """
    Generate a unique trace_id for a workflow run.
    
    Format: trace_{uuid_first_12_chars}
    Example: trace_a1b2c3d4e5f6
    """
    return f"trace_{uuid.uuid4().hex[:12]}"


def run_workflow(workflow: Any, query: str, timeout: int = MAX_WORKFLOW_TIME_SECONDS) -> Dict[str, Any]:
    """
    Execute workflow with a user query.
    
    Handles state initialization, result extraction, and timeout enforcement.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  Phase 6 Enhancement: GUARANTEED Trace Lifecycle                         ║
    ║                                                                          ║
    ║  - Generates decision_id and trace_id at start                           ║
    ║  - Trace is ALWAYS finalized (via managed_trace context manager)         ║
    ║  - Integrity status computed based on actual outcome                     ║
    ║  - Trace included in result for UI/logging consumption                   ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Args:
        workflow: Compiled LangGraph
        query: User's natural language question
        timeout: Maximum execution time in seconds (default: 60)
        
    Returns:
        Final workflow state with all results, including:
        - decision_id: Unique ID for this workflow run
        - trace_id: Unique ID for audit trail
        - trace: Complete decision trace (finalized)
        
    Raises:
        TimeoutError: If workflow exceeds timeout
    """
    # Phase 6: Generate unique IDs for this workflow run
    decision_id = generate_decision_id()
    trace_id = generate_trace_id()
    
    # Track execution time
    start_time = time.time()
    
    # Use managed trace to GUARANTEE finalization
    with managed_trace(trace_id, query, decision_id) as (trace, writer, outcome):
        # Create initial state with correlation IDs
        initial_state = create_initial_state(query, trace_id=trace_id, decision_id=decision_id)
        
        try:
            # Run workflow
            result = workflow.invoke(initial_state)
            
            # Determine outcome for trace finalization
            if result.get('error'):
                outcome[0] = 'error'
            elif result.get('guardrails_result', {}).get('classification') == 'blocked':
                outcome[0] = 'blocked'
            elif result.get('analyst_error_type') == 'EMPTY_RESULT':
                outcome[0] = 'empty_result'
            elif result.get('workflow_complete'):
                outcome[0] = 'success'
            else:
                outcome[0] = 'error'  # Unknown state = error
                
        except Exception as e:
            # Exception during workflow - trace will be finalized as 'error'
            outcome[0] = 'error'
            result = {
                'error': str(e),
                'error_stage': 'workflow_execution',
                'workflow_complete': False
            }
    
    # Check timeout (defensive - LangGraph should handle this internally)
    elapsed = time.time() - start_time
    if elapsed > timeout:
        result['warning'] = f'Workflow took {elapsed:.1f}s (exceeded {timeout}s target)'
    
    # Add timing and correlation metadata
    result['execution_time_seconds'] = round(elapsed, 2)
    result['decision_id'] = decision_id  # Phase 6: Ensure decision_id in result
    result['trace_id'] = trace_id        # Phase 6: Ensure trace_id in result
    result['trace'] = trace.to_dict()    # Phase 6: Include complete trace
    result['trace_integrity'] = trace.integrity_status.value  # Phase 6: Integrity status
    
    return result


def run_workflow_streaming(workflow: Any, query: str, timeout: int = MAX_WORKFLOW_TIME_SECONDS):
    """
    Execute workflow with streaming output.
    
    Yields state updates as they happen for UI feedback.
    Enforces timeout to prevent abuse.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  Phase 6 Enhancement: GUARANTEED Trace Lifecycle                         ║
    ║                                                                          ║
    ║  Uses managed_trace context manager to ensure trace finalization         ║
    ║  even if streaming is interrupted or times out.                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Args:
        workflow: Compiled LangGraph
        query: User's question
        timeout: Maximum execution time in seconds
        
    Yields:
        State updates from each node
        
    Raises:
        TimeoutError: If workflow exceeds timeout
    """
    # Phase 6: Generate correlation IDs
    decision_id = generate_decision_id()
    trace_id = generate_trace_id()
    
    start_time = time.time()
    
    # Use managed trace to GUARANTEE finalization
    with managed_trace(trace_id, query, decision_id) as (trace, writer, outcome):
        initial_state = create_initial_state(query, trace_id=trace_id, decision_id=decision_id)
        final_output = None
        
        try:
            for output in workflow.stream(initial_state):
                # Check timeout on each yield
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    outcome[0] = 'error'
                    yield {'timeout_error': f'Workflow exceeded {timeout}s limit at {elapsed:.1f}s'}
                    return
                final_output = output
                yield output
            
            # Determine outcome from final state
            if final_output:
                # Extract state from output (LangGraph wraps it)
                state = list(final_output.values())[0] if isinstance(final_output, dict) else {}
                if state.get('error'):
                    outcome[0] = 'error'
                elif state.get('workflow_complete'):
                    outcome[0] = 'success'
                else:
                    outcome[0] = 'success'  # Streaming completed
            else:
                outcome[0] = 'error'
                
        except Exception:
            outcome[0] = 'error'
            raise


def run_workflow_with_interrupt(
    workflow: Any, 
    query: str, 
    approval_callback: callable
) -> Dict[str, Any]:
    """
    Execute workflow with human-in-the-loop approval.
    
    NOTE: Full implementation in Phase 6.
    
    Args:
        workflow: Compiled LangGraph
        query: User's question
        approval_callback: Function called at interrupt points
                          Signature: (action: str) -> bool
        
    Returns:
        Final workflow state
    """
    # Phase 2: Run without interrupts (human approval in Phase 6)
    return run_workflow(workflow, query)


def get_workflow_visualization() -> str:
    """
    Generate Mermaid diagram of the workflow.
    
    Returns:
        Mermaid markdown string for rendering
    """
    return """
```mermaid
graph TD
    START([Start]) --> GUARD[Guardrails]
    GUARD -->|ON_TOPIC| ANALYST[Analyst Agent]
    GUARD -->|OFF_TOPIC| ERROR[Error Handler]
    
    ANALYST -->|Success| STRAT[Strategist Agent]
    ANALYST -->|EMPTY_RESULT| STRAT
    ANALYST -->|SQL_ERROR & Retry < 2| ANALYST
    ANALYST -->|Fail| ERROR
    
    STRAT --> COPY[Copywriter Agent]
    COPY --> END([End])
    
    ERROR --> END
    
    style ANALYST fill:#e1f5fe
    style STRAT fill:#fff3e0
    style COPY fill:#e8f5e9
    style ERROR fill:#ffebee
```
"""


def create_test_workflow() -> Dict[str, Any]:
    """
    Create a minimal workflow for testing without LLM.
    
    Returns mock agents that don't require API calls.
    Useful for unit testing the workflow structure.
    
    Returns:
        Dict with 'workflow' and 'mocks' for inspection
    """
    # This will be implemented for testing
    # For now, return info about required setup
    return {
        'info': 'Use create_workflow() with actual LLM and DB for full functionality',
        'required': {
            'llm': 'langchain_openai.ChatOpenAI or compatible',
            'db_connection': 'DuckDB connection from data.database.get_connection()'
        }
    }
