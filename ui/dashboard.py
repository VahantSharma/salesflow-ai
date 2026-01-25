"""
Manager Dashboard - Analytics View
===================================

This module provides a read-only analytics dashboard for managers.
It displays approval patterns, rejection statistics, and operational metrics.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CTO CORRECTION #4: Analytics Code is ISOLATED                               ║
║                                                                              ║
║  This module is ANALYTICS-ONLY:                                              ║
║  - Read-only access to ApprovalManager                                       ║
║  - NEVER imports business logic modules (agents, strategist, etc.)           ║
║  - All computations are for DISPLAY, not decision-making                     ║
║  - Code here MUST NOT be reused by business logic                            ║
║                                                                              ║
║  WHY THIS MATTERS:                                                           ║
║  - Prevents implicit learning loops (dashboard → model feedback)             ║
║  - Ensures analytics don't influence AI recommendations                      ║
║  - Maintains clear separation between observation and action                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    import streamlit as st
    from ui.dashboard import render_manager_dashboard
    
    render_manager_dashboard()
"""

import streamlit as st
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


# =============================================================================
# ANALYTICS-ONLY LABEL
# =============================================================================
# Every function in this module MUST be prefixed with this label in docstrings
# to ensure consumers understand the data is for observation only.

ANALYTICS_LABEL = """
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️  ANALYTICS-ONLY: This data is for operational review.                    ║
║      NOT for model feedback, prompt modification, or threshold adjustment.   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


def render_manager_dashboard() -> None:
    """
    Render the manager analytics dashboard.
    
    ⚠️ ANALYTICS-ONLY: This data is for operational review only.
    NOT for model feedback, prompt modification, or threshold adjustment.
    
    This dashboard provides:
    - Approval/rejection statistics
    - Rejection patterns by category
    - Pending approval queue summary
    - Audit trail access
    
    All data is read-only and for human analysis only.
    """
    
    st.header("📊 Manager Dashboard")
    st.caption("⚠️ Analytics View - Data below is for operational review only")
    
    # Get data from ApprovalService
    from services.approval_service import ApprovalService
    service = ApprovalService()
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    pending = service.get_pending()
    analytics = service.get_rejection_analytics()
    
    with col1:
        st.metric(
            label="📋 Pending",
            value=len(pending),
            help="Findings awaiting manager review"
        )
    
    with col2:
        st.metric(
            label="❌ Total Rejections",
            value=analytics.get('total_rejections', 0),
            help="All-time rejection count (analytics)"
        )
    
    with col3:
        # High severity pending
        high_sev = sum(1 for p in pending if p.severity == 'HIGH')
        st.metric(
            label="🔴 High Severity",
            value=high_sev,
            help="High severity items needing attention"
        )
    
    with col4:
        # Gold tier pending
        gold_tier = sum(1 for p in pending if p.tier == 'Gold')
        st.metric(
            label="🥇 Gold Tier",
            value=gold_tier,
            help="Gold tier retailers with pending actions"
        )
    
    st.divider()
    
    # Two column layout
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        render_pending_queue(pending)
    
    with col_right:
        render_rejection_patterns(analytics)
    
    st.divider()
    
    # Audit trail section
    render_audit_trail(service)


def render_pending_queue(pending: List) -> None:
    """
    Render the pending approval queue.
    
    ⚠️ ANALYTICS-ONLY: This data is for operational review only.
    NOT for model feedback, prompt modification, or threshold adjustment.
    """
    
    st.subheader("📋 Pending Queue")
    
    if not pending:
        st.info("No pending approvals at this time.")
        return
    
    # Group by issue type
    by_type: Dict[str, List] = {}
    for p in pending:
        issue_type = p.issue_type or 'UNKNOWN'
        if issue_type not in by_type:
            by_type[issue_type] = []
        by_type[issue_type].append(p)
    
    # Display counts
    for issue_type, items in by_type.items():
        icon = {
            'CHURN_RISK': '⚠️',
            'CROSS_SELL_GAP': '🎯',
            'VALUE_DECLINE': '📉',
        }.get(issue_type, '📌')
        
        with st.expander(f"{icon} {issue_type} ({len(items)})", expanded=False):
            for item in items[:5]:  # Show first 5
                st.markdown(
                    f"**{item.retailer_name}** ({item.tier}) - "
                    f"Severity: {item.severity}"
                )
            if len(items) > 5:
                st.caption(f"... and {len(items) - 5} more")


def render_rejection_patterns(analytics: Dict[str, Any]) -> None:
    """
    Render rejection pattern analytics.
    
    ⚠️ ANALYTICS-ONLY: This data is for operational review only.
    NOT for model feedback, prompt modification, or threshold adjustment.
    
    This shows WHY managers are rejecting recommendations.
    Used for operational improvement, NOT model feedback.
    """
    
    st.subheader("📊 Rejection Patterns")
    st.caption("⚠️ For operational review only - NOT model feedback")
    
    by_category = analytics.get('by_category', {})
    by_issue_type = analytics.get('by_issue_type', {})
    
    if not by_category and not by_issue_type:
        st.info("No rejection data available yet.")
        return
    
    # Category breakdown
    if by_category:
        st.markdown("**By Rejection Category:**")
        
        # Sort by count
        sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        
        # Map category to label
        category_labels = {
            'incorrect_data': '📊 Incorrect Data',
            'already_handled': '✅ Already Handled',
            'wrong_priority': '📋 Wrong Priority',
            'wrong_action': '🔄 Wrong Action',
            'not_applicable': '❌ Not Applicable',
            'other': '💬 Other',
            'unknown': '❓ Unknown',
        }
        
        for cat, count in sorted_cats:
            label = category_labels.get(cat, f'📌 {cat}')
            st.markdown(f"- {label}: **{count}**")
    
    # Issue type breakdown
    if by_issue_type:
        st.markdown("**By Issue Type:**")
        sorted_types = sorted(by_issue_type.items(), key=lambda x: x[1], reverse=True)
        
        for issue_type, count in sorted_types:
            icon = {
                'CHURN_RISK': '⚠️',
                'CROSS_SELL_GAP': '🎯',
                'VALUE_DECLINE': '📉',
            }.get(issue_type, '📌')
            st.markdown(f"- {icon} {issue_type}: **{count}**")


def render_audit_trail(service) -> None:
    """
    Render audit trail access.
    
    {ANALYTICS_LABEL}
    """.format(ANALYTICS_LABEL=ANALYTICS_LABEL)
    
    st.subheader("📜 Audit Trail")
    
    # Date range selector
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        days_back = st.selectbox(
            "Time Range",
            options=[7, 14, 30, 90],
            format_func=lambda x: f"Last {x} days",
            index=0
        )
    
    with col2:
        status_filter = st.selectbox(
            "Status Filter",
            options=['all', 'approved', 'rejected', 'pending', 'superseded'],
            format_func=lambda x: x.title(),
            index=0
        )
    
    with col3:
        if st.button("🔍 Load Audit Log"):
            st.session_state.show_audit_log = True
    
    # Show audit log if requested
    if st.session_state.get('show_audit_log', False):
        start_date = datetime.now() - timedelta(days=days_back)
        status = status_filter if status_filter != 'all' else None
        
        try:
            audit_log = service.get_audit_log(
                start_date=start_date,
                status_filter=status
            )
            
            if audit_log:
                st.markdown(f"**Found {len(audit_log)} records:**")
                
                # Display as table
                import pandas as pd
                
                df_data = []
                for record in audit_log[:50]:  # Limit to 50 rows
                    df_data.append({
                        'Finding ID': record.finding_id[:8] + '...',
                        'Retailer': record.retailer_name,
                        'Type': record.issue_type,
                        'Status': record.status,
                        'Created': record.created_at.strftime('%Y-%m-%d %H:%M') if record.created_at else 'N/A',
                    })
                
                if df_data:
                    df = pd.DataFrame(df_data)
                    st.dataframe(df, use_container_width=True)
                
                if len(audit_log) > 50:
                    st.caption(f"Showing first 50 of {len(audit_log)} records")
            else:
                st.info("No records found for the selected criteria.")
                
        except Exception as e:
            st.error(f"Failed to load audit log: {e}")


def render_trace_correlation(service, decision_id: str) -> None:
    """
    Render trace correlation view.
    
    Phase 6: Shows all findings from a single workflow run.
    
    {ANALYTICS_LABEL}
    """.format(ANALYTICS_LABEL=ANALYTICS_LABEL)
    
    st.subheader("🔗 Trace Correlation")
    
    if not decision_id:
        st.info("No decision_id available. Run a workflow first.")
        return
    
    st.markdown(f"**Decision ID:** `{decision_id}`")
    
    try:
        findings = service.get_by_decision_id(decision_id)
        
        if findings:
            st.markdown(f"**Findings from this decision:** {len(findings)}")
            
            for f in findings:
                status_icon = {
                    'pending': '🟡',
                    'approved': '✅',
                    'rejected': '❌',
                    'superseded': '🔄',
                }.get(f.status, '❓')
                
                st.markdown(
                    f"- {status_icon} **{f.retailer_name}** - "
                    f"{f.issue_type} ({f.status})"
                )
        else:
            st.info("No findings found for this decision.")
            
    except Exception as e:
        st.error(f"Failed to load findings: {e}")


# =============================================================================
# STANDALONE DASHBOARD PAGE
# =============================================================================

def dashboard_page() -> None:
    """
    Standalone dashboard page entry point.
    
    Can be run as a separate Streamlit page:
        streamlit run ui/dashboard.py
    """
    st.set_page_config(
        page_title="SalesFlow AI - Manager Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    # Initialize session state for dashboard
    if 'show_audit_log' not in st.session_state:
        st.session_state.show_audit_log = False
    
    render_manager_dashboard()
    
    # Footer
    st.divider()
    st.caption("SalesFlow AI v0.6.0 | Manager Dashboard - Analytics Only")


if __name__ == "__main__":
    dashboard_page()
