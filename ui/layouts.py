"""
Page Layouts

Responsibility:
- Define overall page structure
- Manage navigation and routing
- Handle sidebar configuration
- Coordinate component placement

Layout Functions:
- main_layout(): Two-column layout with sidebar
- dashboard_layout(): Multi-panel dashboard view
- detail_layout(): Single-focus detail view
- conversation_layout(): Chat-style interaction view

Navigation:
- Sidebar menu for page switching
- Query history in sidebar
- Settings panel in sidebar

Page Types:
1. Dashboard: Overview with key metrics and alerts
2. Insights: AI-generated insights with actions
3. Retailers: Retailer list with search/filter
4. Settings: Configuration and debug tools
5. Chat: Conversational query interface

Usage:
    from ui.layouts import main_layout, dashboard_layout
    
    def app():
        page = main_layout()  # Returns selected page
        if page == "Dashboard":
            dashboard_layout()
"""

import streamlit as st
from typing import Callable, Dict


def main_layout() -> str:
    """
    Set up main page structure with sidebar navigation.
    
    Returns:
        Name of selected page
    """
    st.set_page_config(
        page_title="SalesFlow AI",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Sidebar navigation
    with st.sidebar:
        st.title("🎯 SalesFlow AI")
        st.markdown("---")
        
        page = st.radio(
            "Navigation",
            ["Dashboard", "Insights", "Retailers", "Ask AI", "Settings"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.markdown("### Quick Stats")
        # Stats will be populated in Phase 7
        
    return page


def dashboard_layout() -> None:
    """
    Multi-panel dashboard with key metrics and alerts.
    
    Layout:
    ┌─────────────────────────────────────────┐
    │           Key Metrics (4 columns)        │
    ├─────────────────────────────────────────┤
    │    Priority Alerts    │   Top Insights   │
    │    (list)            │   (cards)        │
    ├─────────────────────────────────────────┤
    │         Trend Charts (2 columns)         │
    └─────────────────────────────────────────┘
    """
    # Implementation will be added in Phase 7
    pass


def insights_layout() -> None:
    """
    AI-generated insights with action buttons.
    
    Layout:
    ┌─────────────────────────────────────────┐
    │  Filter: [Type ▼] [Priority ▼] [Search] │
    ├─────────────────────────────────────────┤
    │  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
    │  │ Insight │  │ Insight │  │ Insight │  │
    │  │  Card   │  │  Card   │  │  Card   │  │
    │  └─────────┘  └─────────┘  └─────────┘  │
    │           (Paginated grid)               │
    └─────────────────────────────────────────┘
    """
    # Implementation will be added in Phase 7
    pass


def conversation_layout() -> None:
    """
    Chat-style interface for natural language queries.
    
    Layout:
    ┌─────────────────────────────────────────┐
    │  [User]: Show me churning retailers      │
    │  [AI]: I found 5 retailers at churn risk │
    │  [Insight Card]                          │
    │  [User]: Tell me more about R-001        │
    │  ...                                     │
    ├─────────────────────────────────────────┤
    │  [Type your question...]          [Send] │
    └─────────────────────────────────────────┘
    """
    # Implementation will be added in Phase 7
    pass


def settings_layout() -> None:
    """
    Configuration and debug tools.
    
    Sections:
    - LLM Settings (model, temperature)
    - Data Settings (date range, filters)
    - Debug Mode (show raw SQL, show reasoning)
    - About (version, documentation link)
    """
    # Implementation will be added in Phase 7
    pass


def render_page(page_name: str, page_functions: Dict[str, Callable]) -> None:
    """
    Route to appropriate page layout.
    
    Args:
        page_name: Name of selected page
        page_functions: Dict mapping names to layout functions
    """
    if page_name in page_functions:
        page_functions[page_name]()
    else:
        st.error(f"Unknown page: {page_name}")
