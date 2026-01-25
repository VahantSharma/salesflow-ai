"""
Graph Nodes (Agent Wrappers)

Responsibility:
- Wrap each agent as a LangGraph node
- Handle state updates correctly
- Implement retry logic for self-correction
- Route to next node based on results

CRITICAL DESIGN RULE:
- Nodes contain NO business logic
- They only: unwrap state → call agent → merge output
- All business logic lives in the agents

╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 4: Decision Trace Integration                                         ║
║                                                                              ║
║  Each node receives an OPTIONAL TraceWriter (write-only handle).             ║
║  Nodes append trace entries but NEVER read the trace.                        ║
║                                                                              ║
║  The trace is passed separately from state to enforce the write-only         ║
║  constraint. If trace_writer is None, tracing is disabled (graceful).        ║
║                                                                              ║
║  CRITICAL: Nodes must NOT make decisions based on trace contents.            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Node Types:
1. guardrails_node: Input validation and topic classification
2. analyst_node: SQL generation and execution
3. strategist_node: Data analysis and insight generation
4. copywriter_node: Message crafting
5. error_node: Handle and format errors
6. human_approval_node: Interrupt for human decision

Node Contract:
- Input: AgentState (full state)
- Output: dict (partial state update)
- Never modify state directly
- Always set current_node for debugging

Error Handling:
- Analyst errors: Distinguish SQL_ERROR (retry) from EMPTY_RESULT (valid)
- All errors accumulated in state["errors"]
- Fatal errors set state["error"] and stop workflow

Self-Correction Pattern:
    def analyst_node(state):
        result = analyst.generate_query(...)
        if result["error_type"] == "SQL_ERROR" and retry_count < 2:
            return {"analyst_retry_count": state["analyst_retry_count"] + 1}
        # EMPTY_RESULT is NOT an error - proceed to strategist
        return {...}

Usage:
    from graph.nodes import analyst_node, strategist_node, copywriter_node
    # Nodes are passed to StateGraph.add_node()
"""

from typing import Any, Dict, Optional
from datetime import datetime
import time

from graph.state import AgentState, add_error_to_state
from graph.trace import (
    TraceWriter,
    GuardrailsTraceEntry,
    AnalystTraceEntry,
    StrategistTraceEntry,
    CopywriterTraceEntry,
    WorkflowTraceEntry,
    DataProvenance,
    SeverityComputation,
)


# === Agent instances (injected at workflow creation) ===
# These are set by workflow.py when building the graph
_analyst_agent = None
_strategist_agent = None
_copywriter_agent = None
_guardrails_agent = None

# === Trace writer (injected per-workflow execution) ===
# This is write-only - nodes append but never read
_trace_writer: Optional[TraceWriter] = None


def set_agents(
    analyst=None, 
    strategist=None, 
    copywriter=None, 
    guardrails=None
):
    """
    Inject agent instances into nodes.
    
    Called by workflow.py during graph construction.
    """
    global _analyst_agent, _strategist_agent, _copywriter_agent, _guardrails_agent
    if analyst:
        _analyst_agent = analyst
    if strategist:
        _strategist_agent = strategist
    if copywriter:
        _copywriter_agent = copywriter
    if guardrails:
        _guardrails_agent = guardrails


def set_trace_writer(writer: Optional[TraceWriter]):
    """
    Inject trace writer for current workflow execution.
    
    This is called at the START of each workflow execution.
    The writer is WRITE-ONLY - nodes can append but never read.
    
    Args:
        writer: TraceWriter instance or None to disable tracing
    """
    global _trace_writer
    _trace_writer = writer


def clear_trace_writer():
    """
    Clear trace writer after workflow completion.
    
    Called at workflow END to prevent accidental writes.
    """
    global _trace_writer
    _trace_writer = None


def guardrails_node(state: AgentState) -> Dict[str, Any]:
    """
    Validate user input and classify topic.
    
    Phase 4: Now uses actual GuardrailsAgent implementation.
    If no agent is configured, falls back to permissive passthrough.
    
    Args:
        state: Current workflow state
        
    Returns:
        State update with guardrails_result, is_on_topic, sanitized_query
        (Note: sanitized_query == original query - we do NOT rewrite)
    """
    global _guardrails_agent, _trace_writer
    
    start_time = time.time()
    query = state['query']
    
    # If no guardrails agent, use permissive passthrough
    if _guardrails_agent is None:
        result = {
            'current_node': 'guardrails',
            'guardrails_result': {
                'classification': 'allowed',
                'original_query': query,
                'detected_patterns': [],
                'topic_category': 'general',
                'intent': 'query',
                'block_reason': None,
            },
            'is_on_topic': True,
            'sanitized_query': query  # UNCHANGED - we do NOT rewrite
        }
        
        # Write trace entry (if tracing enabled)
        if _trace_writer:
            try:
                _trace_writer.write_guardrails(GuardrailsTraceEntry(
                    timestamp=datetime.now(),
                    original_query=query,
                    classification='allowed',
                    detected_patterns=[],
                    topic_category='general',
                    intent_label='query',
                    block_reason=None,
                    execution_time_ms=(time.time() - start_time) * 1000,
                ))
            except RuntimeError:
                pass  # Trace already written or finalized - ignore
        
        return result
    
    # Use actual GuardrailsAgent
    validation_result = _guardrails_agent.validate(query)
    
    # Write trace entry (if tracing enabled)
    if _trace_writer:
        try:
            _trace_writer.write_guardrails(GuardrailsTraceEntry(
                timestamp=datetime.now(),
                original_query=query,
                classification=validation_result.classification,
                detected_patterns=validation_result.detected_patterns,
                topic_category=validation_result.topic_category,
                intent_label=validation_result.intent,
                block_reason=validation_result.block_reason,
                execution_time_ms=validation_result.execution_time_ms,
            ))
        except RuntimeError:
            pass  # Trace already written or finalized - ignore
    
    return {
        'current_node': 'guardrails',
        'guardrails_result': validation_result.to_dict(),
        'is_on_topic': validation_result.is_allowed,
        'sanitized_query': validation_result.original_query  # UNCHANGED
    }


def analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Generate and execute SQL query.
    
    Error Taxonomy:
    - SQL_ERROR or VALIDATION_ERROR: Retry if retry_count < 2
    - EMPTY_RESULT: Valid answer, proceed to strategist
    
    Args:
        state: Current workflow state with sanitized_query
        
    Returns:
        State update with sql_query, query_results, view_used, etc.
    """
    global _analyst_agent, _trace_writer
    
    start_time = time.time()
    
    if _analyst_agent is None:
        return {
            'current_node': 'analyst',
            'error': 'Analyst agent not initialized',
            'error_stage': 'analyst',
            'errors': [add_error_to_state(state, 'analyst', 'INIT_ERROR', 
                                          'Analyst agent not initialized', False)]
        }
    
    # Get query (use sanitized if available, else original)
    query = state.get('sanitized_query') or state['query']
    retry_count = state.get('analyst_retry_count', 0)
    
    # Build retry context if this is a retry
    retry_context = None
    if retry_count > 0 and state.get('analyst_error'):
        retry_context = {
            'error': state['analyst_error'],
            'sql': state.get('sql_query', '')
        }
    
    # Call analyst
    result = _analyst_agent.generate_query(query, retry_context)
    execution_time = (time.time() - start_time) * 1000
    
    # Handle result
    if result['success']:
        # Success (including empty results)
        
        # Write trace entry (if tracing enabled)
        if _trace_writer:
            try:
                # Build provenance from result
                provenance = None
                if result.get('view_used'):
                    provenance = DataProvenance(
                        view_used=result['view_used'],
                        columns_accessed=result.get('columns_accessed', []),
                        filter_applied=result.get('filter_applied'),
                        aggregation_type=result.get('aggregation_type'),
                        row_count_returned=result.get('result_metadata', {}).get('row_count'),
                        retailer_ids_affected=None,  # Populated by strategist
                    )
                
                _trace_writer.write_analyst(AnalystTraceEntry(
                    timestamp=datetime.now(),
                    sql_generated=result['sql'],
                    sql_valid=True,
                    execution_success=True,
                    provenance=provenance,
                    retry_count=retry_count,
                    error_type=result.get('error_type'),  # May be EMPTY_RESULT
                    execution_time_ms=execution_time,
                ))
            except RuntimeError:
                pass  # Trace already written or finalized - ignore
        
        return {
            'current_node': 'analyst',
            'sql_query': result['sql'],
            'view_used': result['view_used'],
            'query_results': result['results'],
            'result_metadata': result['result_metadata'],
            'analyst_error': None,
            'analyst_error_type': result.get('error_type'),  # May be EMPTY_RESULT
        }
    else:
        # Error occurred
        error_type = result.get('error_type', 'SQL_ERROR')
        
        # Write trace entry for failed attempt (if tracing enabled)
        if _trace_writer:
            try:
                _trace_writer.write_analyst(AnalystTraceEntry(
                    timestamp=datetime.now(),
                    sql_generated=result.get('sql', ''),
                    sql_valid=False,
                    execution_success=False,
                    provenance=None,
                    retry_count=retry_count,
                    error_type=error_type,
                    execution_time_ms=execution_time,
                ))
            except RuntimeError:
                pass  # Trace already written or finalized - ignore
        
        # Determine if we should retry
        if error_type in ('SQL_ERROR', 'VALIDATION_ERROR') and retry_count < 2:
            # Retry - increment counter, keep error for context
            return {
                'current_node': 'analyst',
                'sql_query': result['sql'],
                'analyst_error': result['error'],
                'analyst_error_type': error_type,
                'analyst_retry_count': retry_count + 1,
                'errors': [add_error_to_state(state, 'analyst', error_type, 
                                              result['error'], True)]
            }
        else:
            # Max retries or non-retryable error - fail
            return {
                'current_node': 'analyst',
                'sql_query': result.get('sql'),
                'analyst_error': result['error'],
                'analyst_error_type': error_type,
                'error': f"Analyst failed after {retry_count + 1} attempts: {result['error']}",
                'error_stage': 'analyst',
                'errors': [add_error_to_state(state, 'analyst', error_type, 
                                              result['error'], False)]
            }


def strategist_node(state: AgentState) -> Dict[str, Any]:
    """
    Analyze query results and generate strategic insight.
    
    Input Contract: Receives full context from analyst including
    query, sql, view_used, results, result_metadata.
    
    Args:
        state: Current workflow state with query_results
        
    Returns:
        State update with insight, insight_type, priority, etc.
    """
    global _strategist_agent, _trace_writer
    
    start_time = time.time()
    
    if _strategist_agent is None:
        return {
            'current_node': 'strategist',
            'error': 'Strategist agent not initialized',
            'error_stage': 'strategist',
            'errors': [add_error_to_state(state, 'strategist', 'INIT_ERROR',
                                          'Strategist agent not initialized', False)]
        }
    
    # Check for analyst failure (should not reach here, but defensive)
    if state.get('error'):
        return {
            'current_node': 'strategist',
            'insight': None,
            'errors': [add_error_to_state(state, 'strategist', 'UPSTREAM_ERROR',
                                          'Analyst stage failed', False)]
        }
    
    # Build rich input contract for strategist
    analyst_output = {
        'query': state['query'],
        'sql': state.get('sql_query'),
        'view_used': state.get('view_used'),
        'results': state.get('query_results'),
        'result_metadata': state.get('result_metadata', {})
    }
    
    # Call strategist
    try:
        result = _strategist_agent.analyze(analyst_output)
        execution_time = (time.time() - start_time) * 1000
        
        # Write trace entry (if tracing enabled)
        if _trace_writer:
            try:
                # Build severity computations from findings
                severity_comps = []
                findings = result.get('findings', [])
                for finding in findings[:5]:  # Limit to first 5 for trace
                    if finding.get('severity') and finding.get('metrics'):
                        metrics = finding['metrics']
                        # Document the deterministic severity computation
                        if 'days_since_order' in metrics:
                            severity_comps.append(SeverityComputation(
                                rule_name='days_since_order_threshold',
                                threshold_value=14,
                                actual_value=metrics.get('days_since_order'),
                                result=finding.get('severity', 'unknown').lower(),
                            ))
                
                # Count tiers from findings
                tier_dist = {'Gold': 0, 'Silver': 0, 'Bronze': 0}
                for finding in findings:
                    tier = finding.get('tier', '').title()
                    if tier in tier_dist:
                        tier_dist[tier] += 1
                
                # Get suppression info
                suppression = []
                for finding in findings:
                    if finding.get('suppressed_crosssell'):
                        suppression.append(f"crosssell_suppressed:{finding.get('retailer_id', 'unknown')}")
                
                _trace_writer.write_strategist(StrategistTraceEntry(
                    timestamp=datetime.now(),
                    findings_count=len(findings),
                    actions_generated=result.get('summary', {}).get('total_issues', 0),
                    severity_computations=severity_comps,
                    suppression_applied=suppression,
                    tier_distribution=tier_dist,
                    execution_time_ms=execution_time,
                ))
            except RuntimeError:
                pass  # Trace already written or finalized - ignore
        
        return {
            'current_node': 'strategist',
            'insight': result,
            'insight_type': result.get('insight_type'),
            'priority': result.get('priority'),
            'recommended_action': result.get('recommended_action'),
            'action_type': result.get('action_type'),
            'evidence': result.get('evidence'),
            'business_impact': result.get('business_impact'),
            'confidence_level': result.get('confidence_level'),
            'summary': result.get('summary'),  # Pre-computed for UI
        }
    except Exception as e:
        return {
            'current_node': 'strategist',
            'error': f'Strategist analysis failed: {str(e)}',
            'error_stage': 'strategist',
            'errors': [add_error_to_state(state, 'strategist', 'ANALYSIS_ERROR',
                                          str(e), False)]
        }


def copywriter_node(state: AgentState) -> Dict[str, Any]:
    """
    Craft sales messages from insight.
    
    Uses confidence_level from strategist to adjust tone.
    
    Args:
        state: Current workflow state with insight
        
    Returns:
        State update with messages, primary_message
    """
    global _copywriter_agent, _trace_writer
    
    start_time = time.time()
    
    if _copywriter_agent is None:
        return {
            'current_node': 'copywriter',
            'error': 'Copywriter agent not initialized',
            'error_stage': 'copywriter',
            'errors': [add_error_to_state(state, 'copywriter', 'INIT_ERROR',
                                          'Copywriter agent not initialized', False)]
        }
    
    # Check for upstream failure
    if state.get('error'):
        return {
            'current_node': 'copywriter',
            'messages': None,
            'errors': [add_error_to_state(state, 'copywriter', 'UPSTREAM_ERROR',
                                          'Upstream stage failed', False)]
        }
    
    # Get insight from strategist
    insight = state.get('insight')
    if not insight:
        return {
            'current_node': 'copywriter',
            'messages': {'primary_message': 'No insights to report.'},
            'primary_message': 'No insights to report.',
            'workflow_complete': True
        }
    
    # Call copywriter
    try:
        result = _copywriter_agent.craft_message(insight)
        execution_time = (time.time() - start_time) * 1000
        
        # Write trace entry (if tracing enabled)
        if _trace_writer:
            try:
                # Determine tone from confidence level
                confidence = state.get('confidence_level', 'MEDIUM')
                tone_map = {
                    'HIGH': 'urgent',
                    'MEDIUM': 'concerned',
                    'LOW': 'routine',
                }
                tone = tone_map.get(confidence, 'routine')
                
                # Get discount info - single source is Strategist
                discount_value = None
                findings = insight.get('findings', [])
                for finding in findings:
                    if finding.get('recommended_discount'):
                        discount_value = finding['recommended_discount']
                        break
                
                _trace_writer.write_copywriter(CopywriterTraceEntry(
                    timestamp=datetime.now(),
                    messages_generated=len(result.get('messages', [])) or 1,
                    tone_used=tone,
                    discount_source='strategist',  # CTO: Document discount source
                    discount_value=discount_value,
                    execution_time_ms=execution_time,
                ))
            except RuntimeError:
                pass  # Trace already written or finalized - ignore
        
        return {
            'current_node': 'copywriter',
            'messages': result,
            'primary_message': result.get('primary_message'),
            'workflow_complete': True  # Mark workflow as done
        }
    except Exception as e:
        return {
            'current_node': 'copywriter',
            'error': f'Message crafting failed: {str(e)}',
            'error_stage': 'copywriter',
            'errors': [add_error_to_state(state, 'copywriter', 'MESSAGE_ERROR',
                                          str(e), False)]
        }


def error_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle workflow errors gracefully.
    
    Formats errors for user display without exposing internals.
    
    Args:
        state: Current workflow state with error
        
    Returns:
        State update with user-friendly error message
    """
    error = state.get('error', 'An unexpected error occurred')
    error_stage = state.get('error_stage', 'unknown')
    
    # User-friendly messages by stage
    user_messages = {
        'analyst': "I couldn't understand that query. Could you rephrase it?",
        'strategist': "I found the data but had trouble analyzing it. Please try again.",
        'copywriter': "I analyzed the data but couldn't generate a message.",
        'unknown': "Something went wrong. Please try again."
    }
    
    return {
        'current_node': 'error',
        'primary_message': user_messages.get(error_stage, user_messages['unknown']),
        'messages': {
            'error': True,
            'error_stage': error_stage,
            'technical_error': error,  # For debugging
            'user_message': user_messages.get(error_stage, user_messages['unknown'])
        },
        'workflow_complete': True
    }


def human_approval_node(state: AgentState) -> Dict[str, Any]:
    """
    Interrupt workflow for human decision.
    
    This node triggers a LangGraph interrupt, pausing execution
    until a human approves or rejects the proposed action.
    
    NOTE: Implementation requires LangGraph interrupt() which
    will be added in Phase 6.
    
    Args:
        state: Current workflow state with proposed action
        
    Returns:
        State update based on human decision
    """
    # Phase 2: Passthrough (no human approval required yet)
    # Human-in-the-loop will be implemented in Phase 6
    return {
        'current_node': 'human_approval',
        'should_interrupt': False
    }


# === Edge Routing Functions ===

def should_retry_analyst(state: AgentState) -> str:
    """
    Determine if analyst should retry SQL generation.
    
    Retry logic:
    - SQL_ERROR or VALIDATION_ERROR with retry_count < 2 → retry
    - EMPTY_RESULT → continue (valid answer)
    - Max retries reached → fail
    
    Returns:
        "retry" if should retry, "continue" if should proceed, "fail" if max retries
    """
    error = state.get('analyst_error')
    error_type = state.get('analyst_error_type')
    retry_count = state.get('analyst_retry_count', 0)
    
    # No error - continue
    if not error:
        return "continue"
    
    # EMPTY_RESULT is a valid answer - continue to strategist
    if error_type == 'EMPTY_RESULT':
        return "continue"
    
    # Retryable errors with retries left
    if error_type in ('SQL_ERROR', 'VALIDATION_ERROR') and retry_count < 2:
        return "retry"
    
    # Max retries or fatal error
    return "fail"


def route_after_analyst(state: AgentState) -> str:
    """
    Route after analyst based on result.
    
    CRITICAL: Failed analyst should NEVER cascade to strategist.
    
    Returns:
        "strategist" if success, "retry" if retry needed, "error" if failed
    """
    # Check for fatal error
    if state.get('error'):
        return "error"
    
    # Determine retry need
    return should_retry_analyst(state)


def route_after_guardrails(state: AgentState) -> str:
    """
    Route based on topic classification.
    
    Returns:
        "analyst" if on-topic, "redirect" if off-topic
    """
    if state.get('is_on_topic', False):
        return "analyst"
    return "redirect"
