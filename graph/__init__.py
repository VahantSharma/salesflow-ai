"""
Graph Package (LangGraph Orchestration)

This package contains the multi-agent workflow orchestration using LangGraph.

Modules:
- state: Typed state definition for agent communication
- nodes: Graph node implementations (agent wrappers)
- workflow: Main graph construction and compilation

Why LangGraph?
- Supports cycles (agent self-correction loops)
- Built-in checkpointing for debugging
- Human-in-the-loop interrupts
- Better than linear chains for complex workflows

Workflow Architecture:
    
    START → Guardrails → [Decision]
                          ↓
                    ON_TOPIC → Analyst → Strategist → Copywriter → END
                          ↓
                    OFF_TOPIC → Redirect Response → END
                    
    Self-Correction Loops:
    - Analyst: SQL syntax error → Re-generate (max 2 retries)
    - Strategist: No actionable insight → Re-analyze with different lens

Usage:
    from graph.workflow import create_workflow
    workflow = create_workflow()
    result = workflow.invoke({"query": "Show me churning retailers"})
"""

__all__ = ["state", "nodes", "workflow"]
