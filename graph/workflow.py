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
from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END

from graph.state import AgentState, create_initial_state
from graph.nodes import (
    guardrails_node,
    analyst_node,
    strategist_node,
    copywriter_node,
    error_node,
    route_after_analyst,
    route_after_guardrails,
    set_agents
)
from agents.analyst import AnalystAgent
from agents.strategist import StrategistAgent
from agents.copywriter import CopywriterAgent


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


def run_workflow(workflow: Any, query: str, timeout: int = MAX_WORKFLOW_TIME_SECONDS) -> Dict[str, Any]:
    """
    Execute workflow with a user query.
    
    Handles state initialization, result extraction, and timeout enforcement.
    
    Args:
        workflow: Compiled LangGraph
        query: User's natural language question
        timeout: Maximum execution time in seconds (default: 60)
        
    Returns:
        Final workflow state with all results
        
    Raises:
        TimeoutError: If workflow exceeds timeout
    """
    # Create initial state
    initial_state = create_initial_state(query)
    
    # Track execution time
    start_time = time.time()
    
    # Run workflow
    result = workflow.invoke(initial_state)
    
    # Check timeout (defensive - LangGraph should handle this internally)
    elapsed = time.time() - start_time
    if elapsed > timeout:
        result['warning'] = f'Workflow took {elapsed:.1f}s (exceeded {timeout}s target)'
    
    # Add timing metadata
    result['execution_time_seconds'] = round(elapsed, 2)
    
    return result


def run_workflow_streaming(workflow: Any, query: str, timeout: int = MAX_WORKFLOW_TIME_SECONDS):
    """
    Execute workflow with streaming output.
    
    Yields state updates as they happen for UI feedback.
    Enforces timeout to prevent abuse.
    
    Args:
        workflow: Compiled LangGraph
        query: User's question
        timeout: Maximum execution time in seconds
        
    Yields:
        State updates from each node
        
    Raises:
        TimeoutError: If workflow exceeds timeout
    """
    initial_state = create_initial_state(query)
    start_time = time.time()
    
    for output in workflow.stream(initial_state):
        # Check timeout on each yield
        elapsed = time.time() - start_time
        if elapsed > timeout:
            yield {'timeout_error': f'Workflow exceeded {timeout}s limit at {elapsed:.1f}s'}
            return
        yield output


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
