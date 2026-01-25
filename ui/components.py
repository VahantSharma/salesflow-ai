"""
Reusable UI Components

Responsibility:
- Provide consistent, reusable UI widgets
- Handle styling and theming
- Encapsulate Streamlit complexity

Architecture Principle:
    Components RENDER data, they do NOT compute it.
    All metrics, counts, severities come from backend.
    If a component needs a value, backend must provide it.

Component Guidelines:
- Each component is a function that calls st.* methods
- Components accept typed data, not raw state
- No business logic - just presentation
- Return action signals (strings) for parent to handle

Available Components:
- render_metrics_bar(): Top-level KPI bar from summary dict
- render_action_card(): Single finding card with actions
- render_processing_status(): Show workflow progress
- metric_display(): KPI with comparison to prior period
- status_badge(): Colored status indicator
- loading_spinner(): Branded loading state
- error_display(): User-friendly error message

Usage:
    from ui.components import render_metrics_bar, render_action_card
    
    render_metrics_bar(summary, retailer_count)
    action = render_action_card(finding, index, is_primary=True)
"""

import streamlit as st
from typing import Optional


# =============================================================================
# STYLING CONSTANTS
# =============================================================================

# Severity to color mapping (from backend severity)
SEVERITY_COLORS = {
    'CRITICAL': '#FF4B4B',  # Red
    'HIGH': '#FFA726',      # Orange
    'MEDIUM': '#FFEE58',    # Yellow
    'LOW': '#66BB6A',       # Green
}

# Tier to emoji mapping
# CANONICAL FORMAT: Title Case (Gold, Silver, Bronze)
# Backend normalizes all tiers to this format via Strategist._normalize_tier()
# UI must NOT call .upper() - just use the tier directly
TIER_EMOJIS = {
    'Gold': '🥇',
    'Silver': '🥈',
    'Bronze': '🥉',
}

# Insight type to icon mapping
INSIGHT_ICONS = {
    'CHURN_RISK': '⚠️',
    'CROSS_SELL_GAP': '🎯',
    'VALUE_DECLINE': '📉',
    'NO_ISSUES': '✅',
}

# Phase 5: Confidence level colors and text
CONFIDENCE_STYLES = {
    'HIGH': {
        'color': '#4CAF50',  # Green
        'bg': '#E8F5E9',
        'icon': '🟢',
        'label': 'High Confidence',
        'tooltip': 'Strong evidence from multiple data points',
    },
    'MEDIUM': {
        'color': '#FF9800',  # Orange
        'bg': '#FFF3E0',
        'icon': '🟡',
        'label': 'Medium Confidence',
        'tooltip': 'Moderate evidence - review recommended',
    },
    'LOW': {
        'color': '#F44336',  # Red
        'bg': '#FFEBEE',
        'icon': '🔴',
        'label': 'Low Confidence',
        'tooltip': 'Weak evidence - verify before acting',
    },
}

# Phase 5: Rejection category labels
REJECTION_CATEGORY_LABELS = {
    'incorrect_data': '📊 Data is incorrect',
    'already_handled': '✅ Already handled',
    'wrong_priority': '📋 Wrong priority',
    'wrong_action': '🔄 Different action needed',
    'not_applicable': '❌ Not applicable',
    'other': '💬 Other reason',
}


# =============================================================================
# METRICS BAR
# =============================================================================

def render_metrics_bar(summary: dict, total_retailers: int = 0) -> None:
    """
    Render the top-level metrics bar.
    
    Uses PRE-COMPUTED values from summary dict.
    UI does NOT count or aggregate - backend provides all numbers.
    
    Args:
        summary: Dict with total_issues, churn_risks, crosssell_opportunities, etc.
        total_retailers: Total active retailers (from database query)
    """
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total = summary.get('total_issues', 0)
        st.metric(
            label="🚨 Total Issues",
            value=str(total),
            help="Total issues requiring attention"
        )
    
    with col2:
        churn = summary.get('churn_risks', 0)
        st.metric(
            label="⚠️ Churn Risks",
            value=str(churn),
            help="Retailers at risk of churning"
        )
    
    with col3:
        crosssell = summary.get('crosssell_opportunities', 0)
        st.metric(
            label="🎯 Cross-sell Opportunities",
            value=str(crosssell),
            help="Retailers with category gaps"
        )
    
    with col4:
        st.metric(
            label="📊 Active Retailers",
            value=str(total_retailers),
            help="Total retailers in portfolio"
        )


# =============================================================================
# ACTION CARDS
# =============================================================================

def render_action_card(
    finding: dict, 
    index: int, 
    is_primary: bool = False
) -> Optional[str]:
    """
    Render a single action card for a finding.
    
    Uses BACKEND-PROVIDED fields:
    - retailer_name, tier: Identification
    - severity, priority: Already computed by Strategist
    - insight_type: Category of issue
    - explanation: LLM-generated description
    - metrics: Numbers extracted from DataFrame (not LLM)
    
    Args:
        finding: Dict with all finding fields (from Strategist)
        index: Card index for unique keys
        is_primary: Whether this is the primary (highlighted) card
        
    Returns:
        Action string ('approve', 'reject', 'detail') or None
    """
    # Extract fields defensively
    retailer_name = finding.get('retailer_name') or finding.get('name', 'Unknown Retailer')
    tier = finding.get('tier', 'BRONZE')
    severity = finding.get('severity', 'MEDIUM')
    priority = finding.get('priority', 'P3_MEDIUM')
    insight_type = finding.get('insight_type', 'CHURN_RISK')
    explanation = finding.get('explanation', 'No details available.')
    metrics = finding.get('metrics', {})
    
    # Visual elements from backend data
    # NOTE: tier is already normalized to Title Case by Strategist._normalize_tier()
    # Do NOT call .upper() - use tier directly for canonical lookup
    tier_emoji = TIER_EMOJIS.get(tier, '📍')
    insight_icon = INSIGHT_ICONS.get(insight_type, '📋')
    severity_color = SEVERITY_COLORS.get(severity, '#FFEE58')
    
    # Container styling
    if is_primary:
        container = st.container(border=True)
    else:
        container = st.container()
    
    with container:
        # Header row
        header_col, badge_col = st.columns([3, 1])
        
        with header_col:
            st.markdown(f"**{tier_emoji} {retailer_name}**")
        
        with badge_col:
            # Severity badge - color from backend severity
            st.markdown(
                f"<span style='background-color:{severity_color};padding:2px 8px;"
                f"border-radius:4px;font-size:12px;color:#333;'>{severity}</span>",
                unsafe_allow_html=True
            )
        
        # Issue type and explanation
        st.caption(f"{insight_icon} {insight_type.replace('_', ' ').title()}")
        st.write(explanation[:150] + "..." if len(explanation) > 150 else explanation)
        
        # Metrics display (if available) - NEVER computed by UI
        if metrics:
            _render_finding_metrics(metrics, insight_type)
        
        # Action buttons
        action_col1, action_col2, action_col3 = st.columns([1, 1, 1])
        
        with action_col1:
            if st.button(
                "✅ Approve",
                key=f"approve_{index}",
                type="primary" if is_primary else "secondary"
            ):
                return "approve"
        
        with action_col2:
            if st.button(
                "❌ Reject",
                key=f"reject_{index}"
            ):
                return "reject"
        
        with action_col3:
            if st.button(
                "📊 Details",
                key=f"detail_{index}"
            ):
                return "detail"
        
        if is_primary:
            st.divider()
    
    return None


def _render_finding_metrics(metrics: dict, insight_type: str) -> None:
    """
    Render metrics for a finding (helper function).
    
    Metrics come FROM backend (DataFrame extraction), NOT LLM.
    UI just displays - never computes.
    """
    if insight_type == 'CHURN_RISK':
        current = metrics.get('current', 0)
        baseline = metrics.get('baseline', 0)
        change = metrics.get('change_percent', 0)
        days_inactive = metrics.get('days_since_order', 0)
        
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            st.caption(f"Value: ₹{current:,.0f} → ₹{baseline:,.0f} ({change:+.1f}%)")
        with mcol2:
            st.caption(f"Days inactive: {days_inactive}")
            
    elif insight_type == 'CROSS_SELL_GAP':
        affinity = metrics.get('affinity_score', 0)
        has_cat = metrics.get('has_category', '')
        missing_cat = metrics.get('missing_category', '')
        
        st.caption(f"Affinity: {affinity:.0%}")
        if has_cat and missing_cat:
            st.caption(f"Buys {has_cat}, potential: {missing_cat}")
            
    elif insight_type == 'VALUE_DECLINE':
        current = metrics.get('current', 0)
        baseline = metrics.get('baseline', 0)
        change = metrics.get('change_percent', 0)
        
        delta_str = f"{change:+.1f}%" if change else None
        st.caption(f"Value: ₹{current:,.0f} (was ₹{baseline:,.0f})")


# =============================================================================
# PROCESSING STATUS
# =============================================================================

def render_processing_status(current_node: Optional[str] = None) -> None:
    """
    Render workflow processing status.
    
    Shows which agent is currently working.
    
    Args:
        current_node: Current processing node name
    """
    stages = ['analyst', 'strategist', 'copywriter', 'complete']
    stage_labels = {
        'analyst': '📊 Analyzing data...',
        'strategist': '🎯 Prioritizing issues...',
        'copywriter': '✍️ Generating messages...',
        'complete': '✅ Complete!'
    }
    
    if current_node:
        label = stage_labels.get(current_node, f'Processing: {current_node}')
        st.info(label)


# =============================================================================
# LEGACY / UTILITY COMPONENTS
# =============================================================================

def apply_theme():
    """
    Apply consistent theming to the Streamlit app.
    
    Call this at the start of every page.
    """
    # Minimal custom CSS
    st.markdown("""
        <style>
        .stMetric label {
            font-size: 14px;
        }
        .stMetric div[data-testid="stMetricValue"] {
            font-size: 28px;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)


def insight_card(
    title: str,
    priority: str,
    message: str,
    insight_type: str,
    action_text: str = "Take Action"
) -> None:
    """
    Display an AI-generated insight in a styled card.
    
    DEPRECATED: Use render_action_card() instead.
    Kept for backward compatibility.
    """
    st.warning(f"**{title}**\n\n{message}")


def retailer_card(
    name: str,
    tier: str,
    last_order: str,
    revenue: float,
    risk_score: float = None
) -> None:
    """
    Display retailer information in compact card format.
    
    Args:
        name: Retailer name
        tier: Gold, Silver, or Bronze
        last_order: Date of last order
        revenue: Total revenue (₹)
        risk_score: Optional churn risk score (0-1)
    """
    tier_emoji = TIER_EMOJIS.get(tier.upper(), '📍')
    
    with st.container(border=True):
        st.markdown(f"**{tier_emoji} {name}**")
        st.caption(f"{tier} Tier | Last Order: {last_order}")
        st.metric("Revenue", f"₹{revenue:,.0f}")
        if risk_score is not None:
            risk_pct = int(risk_score * 100)
            st.progress(risk_score, text=f"Risk: {risk_pct}%")


def metric_display(
    label: str,
    value: str,
    delta: str = None,
    delta_color: str = "normal"
) -> None:
    """
    Display a KPI metric with optional delta.
    
    Args:
        label: Metric name
        value: Current value (pre-formatted)
        delta: Change from previous period
        delta_color: "normal", "inverse", or "off"
    """
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def action_button(
    label: str,
    action_type: str = "primary",
    confirm: bool = False,
    confirm_message: str = "Are you sure?",
    key: str = None
) -> bool:
    """
    Styled action button with optional confirmation.
    
    Args:
        label: Button text
        action_type: "primary", "secondary", or "danger"
        confirm: Whether to show confirmation dialog
        confirm_message: Confirmation prompt
        key: Unique key for the button
        
    Returns:
        True if button was clicked (and confirmed if applicable)
    """
    button_type = "primary" if action_type == "primary" else "secondary"
    return st.button(label, type=button_type, key=key)


def message_preview(
    messages: dict,
    show_variants: bool = True
) -> None:
    """
    Display generated message variants.
    
    Args:
        messages: Dict with primary_message, whatsapp_variant, etc.
        show_variants: Whether to show all variants or just primary
    """
    primary = messages.get('primary_message', 'No message generated.')
    st.info(f"**Suggested Message:**\n\n{primary}")
    
    if show_variants and 'whatsapp_variant' in messages:
        with st.expander("📱 WhatsApp Version"):
            st.write(messages['whatsapp_variant'])


def status_badge(status: str) -> None:
    """
    Display colored status indicator.
    
    Args:
        status: Status text (color inferred from keywords)
    """
    status_lower = status.lower()
    
    if any(word in status_lower for word in ['critical', 'high', 'urgent']):
        color = '#FF4B4B'
    elif any(word in status_lower for word in ['medium', 'warning']):
        color = '#FFA726'
    elif any(word in status_lower for word in ['low', 'info']):
        color = '#66BB6A'
    else:
        color = '#90CAF9'
    
    st.markdown(
        f"<span style='background-color:{color};padding:4px 12px;"
        f"border-radius:4px;font-size:12px;color:#333;'>{status}</span>",
        unsafe_allow_html=True
    )


def loading_spinner(message: str = "Processing...") -> st.spinner:
    """
    Branded loading spinner.
    
    Args:
        message: Loading text
        
    Returns:
        Context manager for spinner
    """
    return st.spinner(message)


def error_display(
    error_message: str,
    suggestion: str = None
) -> None:
    """
    Display user-friendly error message.
    
    Args:
        error_message: What went wrong
        suggestion: How to fix it
    """
    st.error(f"⚠️ {error_message}")
    if suggestion:
        st.info(f"💡 Suggestion: {suggestion}")


# =============================================================================
# PHASE 5: HUMAN-IN-THE-LOOP COMPONENTS
# =============================================================================
# These components support the approval workflow:
# - Confidence badges (trust calibration)
# - Approval action cards (with finding_id)
# - Rejection modal (with category selection)
# - Pending approvals dashboard
# =============================================================================

def render_confidence_badge(confidence_level: str) -> None:
    """
    Render a confidence badge for trust calibration.
    
    Phase 5 Feature: Helps managers calibrate trust in AI recommendations.
    
    Args:
        confidence_level: 'HIGH', 'MEDIUM', or 'LOW' (from Strategist)
    """
    style = CONFIDENCE_STYLES.get(confidence_level.upper(), CONFIDENCE_STYLES['MEDIUM'])
    
    st.markdown(
        f"""
        <div style="
            display: inline-flex;
            align-items: center;
            background-color: {style['bg']};
            border: 1px solid {style['color']};
            border-radius: 8px;
            padding: 6px 12px;
            margin: 4px 0;
        ">
            <span style="font-size: 14px; margin-right: 6px;">{style['icon']}</span>
            <span style="color: {style['color']}; font-weight: 600; font-size: 12px;">
                {style['label']}
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption(style['tooltip'])


def render_approval_card(
    finding: dict,
    index: int,
    is_primary: bool = False,
    on_approve: callable = None,
    on_reject: callable = None,
) -> Optional[str]:
    """
    Render an action card with Phase 5 approval support.
    
    Extends render_action_card with:
    - finding_id tracking (for approval persistence)
    - Confidence badge display
    - Rejection modal trigger
    - Race condition handling (CTO Fix #5)
    
    Args:
        finding: Dict with finding fields including finding_id
        index: Card index for unique keys
        is_primary: Whether highlighted
        on_approve: Callback for approval (receives finding_id)
        on_reject: Callback for rejection (receives finding_id)
        
    Returns:
        Action string or None
        
    Race Condition Handling:
        If two managers click approve/reject at the same time,
        the second click will see ApprovalAlreadyDecidedError.
        We catch this and show a user-friendly warning.
    """
    # Import here to avoid circular dependencies
    from persistence.approvals import ApprovalAlreadyDecidedError
    
    # Extract fields
    finding_id = finding.get('finding_id', f'temp_{index}')
    retailer_name = finding.get('retailer_name') or finding.get('name', 'Unknown')
    tier = finding.get('tier', 'Bronze')
    severity = finding.get('severity', 'MEDIUM')
    priority = finding.get('priority', 'P3_MEDIUM')
    insight_type = finding.get('insight_type', 'CHURN_RISK')
    explanation = finding.get('explanation', 'No details available.')
    confidence_level = finding.get('confidence_level', 'MEDIUM')
    metrics = finding.get('metrics', {})
    
    # Visual styling
    tier_emoji = TIER_EMOJIS.get(tier, '📍')
    insight_icon = INSIGHT_ICONS.get(insight_type, '📋')
    severity_color = SEVERITY_COLORS.get(severity, '#FFEE58')
    
    container = st.container(border=True) if is_primary else st.container()
    
    with container:
        # Header with confidence badge
        header_col, conf_col, badge_col = st.columns([2, 1, 1])
        
        with header_col:
            st.markdown(f"**{tier_emoji} {retailer_name}**")
        
        with conf_col:
            # Inline confidence indicator
            conf_style = CONFIDENCE_STYLES.get(confidence_level.upper(), CONFIDENCE_STYLES['MEDIUM'])
            st.markdown(
                f"<span style='color:{conf_style['color']};font-size:12px;'>"
                f"{conf_style['icon']} {conf_style['label']}</span>",
                unsafe_allow_html=True
            )
        
        with badge_col:
            st.markdown(
                f"<span style='background-color:{severity_color};padding:2px 8px;"
                f"border-radius:4px;font-size:12px;color:#333;'>{severity}</span>",
                unsafe_allow_html=True
            )
        
        # Issue details
        st.caption(f"{insight_icon} {insight_type.replace('_', ' ').title()}")
        st.write(explanation[:150] + "..." if len(explanation) > 150 else explanation)
        
        # Metrics
        if metrics:
            _render_finding_metrics(metrics, insight_type)
        
        # Action buttons with finding_id
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
        
        action = None
        
        with btn_col1:
            if st.button(
                "✅ Approve",
                key=f"approve_{finding_id}_{index}",
                type="primary" if is_primary else "secondary"
            ):
                action = "approve"
                if on_approve:
                    try:
                        on_approve(finding_id)
                    except ApprovalAlreadyDecidedError as e:
                        # CTO Fix #5: Handle race condition gracefully
                        st.warning(
                            f"⚠️ This recommendation was already decided by another user. "
                            f"Please refresh to see the updated status."
                        )
                        action = None  # Clear action since it failed
        
        with btn_col2:
            if st.button(
                "❌ Reject",
                key=f"reject_{finding_id}_{index}"
            ):
                action = "reject"
                # Rejection needs modal - return action for parent to handle
                # The actual rejection call happens in render_rejection_modal
        
        with btn_col3:
            if st.button(
                "📊 Details",
                key=f"detail_{finding_id}_{index}"
            ):
                action = "detail"
        
        # Store finding_id in session for parent access
        if action:
            st.session_state[f'last_action_{index}'] = {
                'action': action,
                'finding_id': finding_id,
                'finding': finding
            }
        
        if is_primary:
            st.divider()
    
    return action


def render_rejection_modal(
    finding_id: str,
    retailer_name: str,
    on_submit: callable = None
) -> Optional[dict]:
    """
    Render rejection reason modal.
    
    Phase 5: Collects manager context for operational analytics.
    This data is NOT fed back into the AI system.
    
    CTO Fix #5: Handles race conditions when two managers reject simultaneously.
    
    Args:
        finding_id: ID of finding being rejected
        retailer_name: For display context
        on_submit: Callback with (finding_id, category, context)
        
    Returns:
        Dict with rejection details or None
    """
    # Import here to avoid circular dependencies
    from persistence.approvals import ApprovalAlreadyDecidedError
    
    with st.expander(f"📝 Rejection Context for {retailer_name}", expanded=True):
        st.caption(
            "Help us understand why this recommendation wasn't useful. "
            "This is for operational review only and does not affect AI decisions."
        )
        
        # Category selection
        category = st.selectbox(
            "Reason",
            options=list(REJECTION_CATEGORY_LABELS.keys()),
            format_func=lambda x: REJECTION_CATEGORY_LABELS.get(x, x),
            key=f"reject_category_{finding_id}"
        )
        
        # Optional context
        context = st.text_area(
            "Additional context (optional)",
            key=f"reject_context_{finding_id}",
            placeholder="Any details that might be helpful for review..."
        )
        
        if st.button("Submit Rejection", key=f"submit_reject_{finding_id}"):
            if on_submit:
                try:
                    on_submit(finding_id, category, context)
                    return {
                        'finding_id': finding_id,
                        'rejection_category': category,
                        'manager_context': context
                    }
                except ApprovalAlreadyDecidedError as e:
                    # CTO Fix #5: Handle race condition gracefully
                    st.warning(
                        f"⚠️ This recommendation was already decided by another user. "
                        f"Please refresh to see the updated status."
                    )
                    return None
            return {
                'finding_id': finding_id,
                'rejection_category': category,
                'manager_context': context
            }
    
    return None


def render_pending_approvals_panel(
    pending_approvals: list,
    on_approve: callable = None,
    on_reject: callable = None
) -> None:
    """
    Render dashboard panel showing all pending approvals.
    
    Phase 5: Provides overview of recommendations awaiting action.
    
    Args:
        pending_approvals: List of ApprovalRecord dicts
        on_approve: Callback for approval action
        on_reject: Callback for rejection action
    """
    st.subheader("📋 Pending Approvals")
    
    if not pending_approvals:
        st.info("No pending approvals. All recommendations have been reviewed.")
        return
    
    # Summary metrics
    total = len(pending_approvals)
    high_priority = sum(1 for a in pending_approvals if a.get('severity') == 'HIGH')
    
    metric_col1, metric_col2 = st.columns(2)
    with metric_col1:
        st.metric("Total Pending", total)
    with metric_col2:
        st.metric("High Priority", high_priority, delta_color="inverse")
    
    st.divider()
    
    # Group by issue type
    by_type = {}
    for approval in pending_approvals:
        issue_type = approval.get('issue_type', 'OTHER')
        if issue_type not in by_type:
            by_type[issue_type] = []
        by_type[issue_type].append(approval)
    
    # Render grouped
    for issue_type, approvals in by_type.items():
        icon = INSIGHT_ICONS.get(issue_type, '📋')
        with st.expander(f"{icon} {issue_type.replace('_', ' ').title()} ({len(approvals)})"):
            for i, approval in enumerate(approvals):
                finding_dict = {
                    'finding_id': approval.get('finding_id'),
                    'retailer_name': approval.get('retailer_name'),
                    'tier': approval.get('tier'),
                    'severity': approval.get('severity'),
                    'insight_type': approval.get('issue_type'),
                    'explanation': approval.get('recommended_action'),
                    'confidence_level': approval.get('confidence_level', 'MEDIUM'),
                }
                render_approval_card(
                    finding_dict,
                    index=i,
                    is_primary=(i == 0 and approval.get('severity') == 'HIGH'),
                    on_approve=on_approve,
                    on_reject=on_reject
                )


def render_approval_history_panel(
    history: list,
    show_rejected: bool = True,
    show_superseded: bool = False
) -> None:
    """
    Render panel showing approval history (audit trail).
    
    Phase 5: Provides audit trail for compliance and analytics.
    
    Args:
        history: List of ApprovalRecord dicts (all statuses)
        show_rejected: Include rejected approvals
        show_superseded: Include superseded approvals
    """
    st.subheader("📜 Approval History")
    
    if not history:
        st.info("No approval history yet.")
        return
    
    # Filter by status
    filtered = history
    if not show_rejected:
        filtered = [h for h in filtered if h.get('status') != 'rejected']
    if not show_superseded:
        filtered = [h for h in filtered if h.get('status') != 'superseded']
    
    # Render as table
    for record in filtered[:20]:  # Limit to 20 most recent
        status = record.get('status', 'pending')
        status_icons = {
            'approved': '✅',
            'rejected': '❌',
            'superseded': '🔄',
            'pending': '⏳'
        }
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.write(f"{status_icons.get(status, '❓')} {record.get('retailer_name', 'Unknown')}")
        
        with col2:
            st.caption(record.get('issue_type', 'N/A'))
        
        with col3:
            decided_at = record.get('decided_at')
            if decided_at:
                st.caption(str(decided_at)[:10])
            else:
                st.caption("Pending")
