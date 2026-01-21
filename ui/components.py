"""
Reusable UI Components

Responsibility:
- Provide consistent, reusable UI widgets
- Handle styling and theming
- Encapsulate Streamlit complexity

Component Guidelines:
- Each component is a function that calls st.* methods
- Components accept typed data, not raw state
- No business logic - just presentation
- Return st.* elements for composition

Available Components:
- insight_card(): Display AI-generated insight with priority badge
- retailer_card(): Show retailer details in compact form
- metric_display(): KPI with comparison to prior period
- action_button(): Styled CTA with confirmation
- message_preview(): Show generated message variants
- status_badge(): Colored status indicator
- loading_spinner(): Branded loading state
- error_display(): User-friendly error message

Styling Helpers:
- apply_theme(): Set consistent colors/fonts
- inject_css(): Add custom CSS to page

Usage:
    from ui.components import insight_card, metric_display
    
    insight_card(
        title="Churn Alert",
        priority="P1_CRITICAL",
        message="5 Gold retailers at risk",
        action="View Details"
    )
"""

import streamlit as st


def apply_theme():
    """
    Apply consistent theming to the Streamlit app.
    
    Call this at the start of every page.
    """
    # Implementation will be added in Phase 7
    pass


def insight_card(
    title: str,
    priority: str,
    message: str,
    insight_type: str,
    action_text: str = "Take Action"
) -> None:
    """
    Display an AI-generated insight in a styled card.
    
    Args:
        title: Card header
        priority: P1_CRITICAL, P2_HIGH, or P3_MEDIUM
        message: Main insight text
        insight_type: CHURN_RISK, CROSS_SELL_GAP, etc.
        action_text: Button label
    """
    # Implementation will be added in Phase 7
    pass


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
    # Implementation will be added in Phase 7
    pass


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
    confirm_message: str = "Are you sure?"
) -> bool:
    """
    Styled action button with optional confirmation.
    
    Args:
        label: Button text
        action_type: "primary", "secondary", or "danger"
        confirm: Whether to show confirmation dialog
        confirm_message: Confirmation prompt
        
    Returns:
        True if button was clicked (and confirmed if applicable)
    """
    # Implementation will be added in Phase 7
    return False


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
    # Implementation will be added in Phase 7
    pass


def status_badge(status: str) -> None:
    """
    Display colored status indicator.
    
    Args:
        status: Status text (color inferred from keywords)
    """
    # Implementation will be added in Phase 7
    pass


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
    st.error(error_message)
    if suggestion:
        st.info(f"💡 Suggestion: {suggestion}")
