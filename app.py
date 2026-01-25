"""
SalesFlow AI - Command Center

Responsibility:
- Initialize Streamlit application
- Configure page settings and styling
- Orchestrate UI layout and components
- Handle user interactions and session state
- Invoke the agent workflow pipeline

Explicitly NOT responsible for:
- Business logic (handled by agents)
- Computing summary/metrics (backend provides these)
- Deciding severity/priority (Strategist's job)
- Data processing (handled by data layer)

Architecture Principle:
    UI is a CONSUMER of decisions, never a CREATOR of decisions.
    If UI needs a value, backend must provide it.
    UI renders, responds, routes - never reasons.

Usage:
    streamlit run app.py
"""

import os
import streamlit as st
from typing import Optional

# Page configuration must be first Streamlit command
st.set_page_config(
    page_title="SalesFlow AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def init_session_state() -> None:
    """
    Initialize all session state fields defensively.
    
    Every field that UI uses must be initialized here.
    This prevents KeyError and ensures consistent behavior.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  PHASE 6 CTO CORRECTION #3: Session State is COSMETIC                    ║
    ║                                                                          ║
    ║  Session state is for UI responsiveness ONLY.                            ║
    ║  Backend (ApprovalService) is ALWAYS the source of truth.                ║
    ║                                                                          ║
    ║  REMOVED:                                                                ║
    ║  - 'approved': [] - UI MUST query backend for approval status            ║
    ║  - 'rejected': [] - UI MUST query backend for rejection status           ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    defaults = {
        # Workflow output
        'workflow_result': None,      # Full workflow state dict
        'action_cards': [],           # List of finding dicts (from insight['findings'])
        'summary': None,              # Pre-computed counts (None = not computed yet, {} = computed but empty)
        'primary_message': None,      # Copywriter output
        
        # Phase 6: Correlation IDs
        'current_decision_id': None,  # Decision ID from latest workflow run
        'current_trace_id': None,     # Trace ID from latest workflow run
        
        # UI state (COSMETIC ONLY - not authoritative)
        'selected_card': None,        # Currently selected card for detail view
        # REMOVED: 'approved': [] - CTO Correction #3: Backend is authoritative
        # REMOVED: 'rejected': [] - CTO Correction #3: Backend is authoritative
        
        # v4 CTO Fix: UI staleness indicator
        'approval_syncing': False,    # True during approval/rejection backend sync
        'last_sync_time': None,       # Timestamp of last backend sync
        
        # Processing state
        'processing': False,          # Show spinner during workflow
        'current_node': None,         # Current processing stage
        'error_message': None,        # Error to display
        
        # Query console
        'last_query': None,           # Last query submitted
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# =============================================================================
# WORKFLOW EXECUTION
# =============================================================================

def execute_workflow(query: str) -> dict:
    """
    Execute the full agent workflow.
    
    Returns the complete workflow state including:
    - insight (with findings, summary, metrics)
    - primary_message
    - error (if any)
    
    This function is the ONLY place where workflow is invoked from UI.
    """
    from langchain_openai import ChatOpenAI
    from data.database import get_connection, init_database
    from graph.workflow import create_workflow, run_workflow
    from config.settings import Settings
    
    try:
        # Initialize LLM from centralized config (Phase 0 contract)
        settings = Settings()
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        # Initialize database
        conn = get_connection()
        init_database(conn)
        
        # Create and run workflow
        workflow = create_workflow(llm, conn)
        result = run_workflow(workflow, query)
        
        return result
        
    except Exception as e:
        return {
            'error': str(e),
            'error_stage': 'workflow_execution',
            'workflow_complete': False
        }


def get_retailer_count() -> int:
    """Get total active retailer count from database."""
    try:
        from data.database import get_connection
        conn = get_connection()
        result = conn.execute(
            "SELECT COUNT(*) FROM retailers WHERE lifecycle_status = 'ACTIVE'"
        ).fetchone()
        return result[0] if result else 0
    except Exception:
        return 0


# =============================================================================
# BASIC GUARDRAILS (NO LLM)
# =============================================================================

def is_on_topic(query: str) -> bool:
    """
    Basic keyword-based topic detection.
    
    No LLM required - simple heuristics for Phase 3.
    Full guardrails will be implemented in Phase 4.
    
    Returns True if query appears to be about sales analytics.
    """
    query_lower = query.lower()
    
    # On-topic keywords (sales analytics domain)
    on_topic_keywords = [
        'retailer', 'store', 'shop', 'outlet', 'customer',
        'churn', 'risk', 'at-risk', 'declining', 'inactive',
        'sales', 'order', 'transaction', 'revenue', 'value',
        'cross-sell', 'opportunity', 'gap', 'category', 'product',
        'gold', 'silver', 'bronze', 'tier',
        'performance', 'trend', 'frequency', 'visit',
        'why', 'show', 'list', 'find', 'who', 'which', 'scan'
    ]
    
    # Off-topic indicators (clearly not sales related)
    off_topic_indicators = [
        'weather', 'news', 'joke', 'story', 'poem',
        'write me a', 'help me with', 'translate',
        'code', 'program', 'python', 'javascript',
        'recipe', 'movie', 'song', 'game', 'play',
        'who is', 'what is the capital', 'history of'
    ]
    
    # Check off-topic first (explicit rejection)
    for indicator in off_topic_indicators:
        if indicator in query_lower:
            return False
    
    # Check on-topic keywords
    for keyword in on_topic_keywords:
        if keyword in query_lower:
            return True
    
    # If no clear signal, default to on-topic (let workflow handle)
    return True


# =============================================================================
# ACTION HANDLERS
# =============================================================================

def handle_card_action(card: dict, action: str) -> None:
    """
    Handle approve/reject/detail actions on a card.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  PHASE 6 CTO CORRECTION #3: Backend is AUTHORITATIVE                     ║
    ║                                                                          ║
    ║  Approvals and rejections are persisted via ApprovalService.             ║
    ║  Session state is NOT used for tracking approval status.                 ║
    ║                                                                          ║
    ║  v4 CTO Fix: UI shows syncing indicator during backend operations.       ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    from datetime import datetime
    
    finding_id = card.get('finding_id')
    retailer_name = card.get('retailer_name') or card.get('name', 'Retailer')
    
    if not finding_id:
        st.warning(f"⚠️ Cannot process action: Missing finding_id for {retailer_name}")
        return
    
    if action == "approve":
        try:
            # v4 CTO Fix: Set syncing state for UI staleness indicator
            st.session_state.approval_syncing = True
            
            from services.approval_service import ApprovalService
            service = ApprovalService()
            service.approve(finding_id, manager_id="manager")
            
            # v4: Update sync timestamp
            st.session_state.last_sync_time = datetime.now()
            st.success(f"✅ Action approved for {retailer_name}")
        except Exception as e:
            st.error(f"❌ Failed to approve: {e}")
        finally:
            st.session_state.approval_syncing = False
        
    elif action == "reject":
        try:
            # v4 CTO Fix: Set syncing state for UI staleness indicator
            st.session_state.approval_syncing = True
            
            from services.approval_service import ApprovalService
            service = ApprovalService()
            # Default rejection category - in production, UI would ask user
            service.reject(finding_id, manager_id="manager", category="TIMING_NOT_RIGHT")
            
            # v4: Update sync timestamp
            st.session_state.last_sync_time = datetime.now()
            st.info(f"Action rejected for {retailer_name}")
        except Exception as e:
            st.error(f"❌ Failed to reject: {e}")
        finally:
            st.session_state.approval_syncing = False
        
    elif action == "detail":
        st.session_state.selected_card = card


def process_scan_request() -> None:
    """Process a risk scan request."""
    st.session_state.processing = True
    st.session_state.error_message = None
    st.session_state.selected_card = None
    
    with st.spinner("🔍 Analyzing retailer portfolio..."):
        try:
            result = execute_workflow(
                "Scan for retailers at churn risk and cross-sell opportunities"
            )
            
            st.session_state.workflow_result = result
            
            # Phase 6: Store correlation IDs
            st.session_state.current_decision_id = result.get('decision_id')
            st.session_state.current_trace_id = result.get('trace_id')
            
            if result.get('error'):
                st.session_state.error_message = result['error']
                st.session_state.action_cards = []
                st.session_state.summary = {}
            else:
                # Extract from insight
                insight = result.get('insight', {})
                st.session_state.action_cards = insight.get('findings', [])
                st.session_state.summary = insight.get('summary', {})
                st.session_state.primary_message = result.get('primary_message')
                
        except Exception as e:
            st.session_state.error_message = str(e)
            st.session_state.action_cards = []
            st.session_state.summary = {}
        finally:
            st.session_state.processing = False


def process_query_request(query: str) -> None:
    """Process a free-form query request."""
    st.session_state.last_query = query
    
    with st.spinner("Processing your question..."):
        try:
            result = execute_workflow(query)
            
            # Update state using SAME path as scan
            st.session_state.workflow_result = result
            
            # Phase 6: Store correlation IDs
            st.session_state.current_decision_id = result.get('decision_id')
            st.session_state.current_trace_id = result.get('trace_id')
            
            if result.get('error'):
                st.session_state.error_message = result['error']
            else:
                insight = result.get('insight', {})
                st.session_state.action_cards = insight.get('findings', [])
                st.session_state.summary = insight.get('summary', {})
                st.session_state.primary_message = result.get('primary_message')
                st.session_state.selected_card = None  # Clear selection
                
        except Exception as e:
            st.session_state.error_message = str(e)


# =============================================================================
# UI RENDERING (Imports from ui modules)
# =============================================================================

def render_header() -> None:
    """Render the application header."""
    st.title("📊 SalesFlow AI")
    st.caption("The Agentic Decision Layer for FMCG Sales")


def render_metrics_bar() -> None:
    """Render the top metrics bar using pre-computed summary."""
    from ui.components import render_metrics_bar as render_metrics
    
    # summary=None means not computed yet, use empty dict for safe access
    summary = st.session_state.summary or {}
    retailer_count = get_retailer_count()
    
    render_metrics(summary, retailer_count)


def get_pending_finding_ids() -> set:
    """
    Get the set of finding_ids that are still pending.
    
    Phase 6: Query backend to determine which findings haven't been decided.
    """
    try:
        from services.approval_service import ApprovalService
        service = ApprovalService()
        pending = service.get_pending()
        return {p.finding_id for p in pending}
    except Exception:
        # If service fails, return empty set (show all cards)
        return set()


def render_priority_actions() -> None:
    """
    Render the left panel with action cards.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  PHASE 6 CTO CORRECTION #3: Backend is AUTHORITATIVE                     ║
    ║                                                                          ║
    ║  Active cards are determined by:                                         ║
    ║  1. Findings from current workflow result (session state)                ║
    ║  2. Filtered by ApprovalService.get_pending() (backend authority)        ║
    ║                                                                          ║
    ║  Session state only stores workflow output.                              ║
    ║  Approval status ALWAYS comes from ApprovalService.                      ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    from ui.components import render_action_card
    
    st.subheader("Priority Actions")
    
    # Scan button
    if st.button("🔍 Scan for Risks", type="primary", use_container_width=True):
        process_scan_request()
        st.rerun()
    
    # Display error if any
    if st.session_state.error_message:
        st.error(f"⚠️ {st.session_state.error_message}")
    
    # Get cards from workflow result
    cards = st.session_state.action_cards
    
    # Phase 6: Filter by pending status from backend (not session state)
    # Only show cards that are still pending in the approval system
    pending_ids = get_pending_finding_ids()
    
    # If we have pending findings from backend, use those to filter
    # Otherwise, show all cards (backend might not have them yet)
    if pending_ids:
        active_cards = [c for c in cards if c.get('finding_id') in pending_ids]
    else:
        # No backend data or backend empty - show workflow cards
        # This handles the case where workflow just ran but findings aren't in approval system yet
        active_cards = cards
    
    if active_cards:
        # Primary card (first one) - with defensive priority check
        primary = active_cards[0]
        primary_priority = primary.get('priority', 'P4_LOW')
        is_high_priority = primary_priority in ('P1_CRITICAL', 'P2_HIGH')
        
        action = render_action_card(primary, 0, is_primary=is_high_priority)
        if action:
            handle_card_action(primary, action)
            st.rerun()
        
        # Secondary cards in expander
        if len(active_cards) > 1:
            with st.expander(f"📋 Other Issues ({len(active_cards) - 1})", expanded=False):
                for i, card in enumerate(active_cards[1:], start=1):
                    action = render_action_card(card, i, is_primary=False)
                    if action:
                        handle_card_action(card, action)
                        st.rerun()
                        
    elif st.session_state.workflow_result:
        # Workflow ran but no issues found
        # insight_type is inside insight dict, not at root level
        insight = st.session_state.workflow_result.get('insight', {})
        insight_type = insight.get('insight_type', '')
        if insight_type == 'NO_ISSUES':
            st.success("✅ Portfolio is healthy! No retailers at risk.")
        else:
            st.info("No priority actions at this time.")
    else:
        st.info("👆 Click 'Scan for Risks' to analyze your retailer portfolio")
    
    # Phase 6: Show pending count from backend (not session state)
    if pending_ids:
        st.caption(f"📋 {len(pending_ids)} pending approval(s)")
    
    # v4 CTO Fix: UI staleness indicator
    # Shows when approval status is being synced with backend
    if st.session_state.get('approval_syncing', False):
        st.info("⏳ Approval status syncing with backend...")
    elif st.session_state.get('last_sync_time'):
        # Show how recently the last sync happened (optional UX enhancement)
        from datetime import datetime
        sync_time = st.session_state.last_sync_time
        if isinstance(sync_time, datetime):
            age_seconds = (datetime.now() - sync_time).total_seconds()
            if age_seconds < 5:
                st.caption("✓ Status synced just now")


def render_analysis_panel() -> None:
    """Render the right panel with details and charts."""
    from ui.charts import render_trend_chart, render_crosssell_chart
    
    st.subheader("Analysis Panel")
    
    selected = st.session_state.selected_card
    
    if selected:
        # Header
        retailer_name = selected.get('retailer_name') or selected.get('name', 'Retailer')
        tier = selected.get('tier', '')
        insight_type = selected.get('insight_type', '')
        
        # Use Copywriter vocabulary for display
        from agents.copywriter import CopywriterAgent
        insight_label = CopywriterAgent.INSIGHT_LABELS.get(insight_type, insight_type)
        
        st.markdown(f"### {retailer_name}")
        st.caption(f"{tier} Tier | {insight_label}")
        
        # Chart based on insight type
        metrics = selected.get('metrics', {})
        
        if insight_type == 'CROSS_SELL_GAP':
            render_crosssell_chart(selected)
        elif metrics:
            render_trend_chart(metrics, retailer_name)
        else:
            st.info("No chart data available")
        
        # Details
        with st.expander("📋 Details", expanded=True):
            st.json({
                "Retailer ID": selected.get('retailer_id'),
                "Severity": selected.get('severity'),
                "Priority": selected.get('priority'),
                "Action Type": selected.get('action_type'),
                "Explanation": selected.get('explanation'),
            })
        
        # Message preview
        if st.session_state.primary_message:
            with st.expander("💬 Suggested Message", expanded=False):
                st.info(st.session_state.primary_message)
        
        # Clear selection
        if st.button("← Back to List", use_container_width=True):
            st.session_state.selected_card = None
            st.rerun()
    else:
        st.info("👈 Select a retailer from Priority Actions to see detailed analysis")
        
        # Show summary stats if available
        summary = st.session_state.summary
        if summary and summary.get('total_issues', 0) > 0:
            st.markdown("**Summary:**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("High Severity", summary.get('high_severity_count', 0))
                st.metric("Gold Tier Affected", summary.get('gold_tier_affected', 0))
            with col2:
                st.metric("Medium Severity", summary.get('medium_severity_count', 0))
                st.metric("Silver Tier Affected", summary.get('silver_tier_affected', 0))


def render_query_console() -> None:
    """Render the natural language query input."""
    st.subheader("💬 Ask a Question")
    
    query = st.text_input(
        "Query",
        placeholder="e.g., 'Why is Kumar Stores at risk?' or 'Show Gold tier performance'",
        label_visibility="collapsed",
        key="query_input"
    )
    
    if query and query != st.session_state.last_query:
        # Check topic
        if not is_on_topic(query):
            st.warning(
                "🤔 This question seems outside the scope of sales analytics. "
                "Try asking about retailers, churn risk, cross-sell opportunities, "
                "or sales performance."
            )
        else:
            process_query_request(query)
            st.rerun()


# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()
    
    # Header
    render_header()
    
    st.divider()
    
    # Metrics bar (always visible)
    render_metrics_bar()
    
    st.divider()
    
    # Two-column layout
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        render_priority_actions()
    
    with col_right:
        render_analysis_panel()
    
    st.divider()
    
    # Query console at bottom
    render_query_console()
    
    # Footer
    st.caption("SalesFlow AI v0.6.0 | Phase 6: HITL Integration & Backend Authority")
