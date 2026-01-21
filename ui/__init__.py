"""
UI Package (Streamlit Components)

This package contains all UI components for the SalesFlow AI dashboard.

Modules:
- components: Reusable UI widgets (cards, buttons, metrics)
- layouts: Page structure and navigation
- charts: Plotly visualization wrappers

Design Philosophy:
- Components are pure functions (no side effects)
- Each component accepts data and returns Streamlit elements
- Consistent styling through theme configuration
- Mobile-responsive where possible

Color Scheme (Salescode.ai inspired):
- Primary: #1a73e8 (Trust blue)
- Success: #34a853 (Green)
- Warning: #fbbc04 (Yellow)
- Danger: #ea4335 (Red)
- Background: #f8f9fa (Light gray)

Component Types:
1. Cards: Insight cards, retailer cards, action cards
2. Metrics: KPI displays, sparklines
3. Tables: Data tables with sorting/filtering
4. Forms: Query input, approval forms
5. Modals: Confirmation dialogs, detail views

Usage:
    from ui.components import insight_card, metric_badge
    from ui.layouts import main_layout, sidebar_layout
    from ui.charts import churn_trend_chart, retailer_map
"""

__all__ = ["components", "layouts", "charts"]
