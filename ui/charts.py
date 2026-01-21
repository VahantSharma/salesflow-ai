"""
Plotly Chart Wrappers

Responsibility:
- Create consistent, branded visualizations
- Wrap Plotly complexity in simple interfaces
- Ensure accessibility (colors, labels)
- Optimize for Streamlit rendering

Chart Types:
1. Time Series: Trends, forecasts, comparisons
2. Bar Charts: Category comparisons, rankings
3. Maps: Geographic distribution
4. Gauges: KPI indicators
5. Tables: Interactive data tables

Design Principles:
- Consistent color palette across all charts
- Clear labels and titles (no chartjunk)
- Tooltips for detail-on-demand
- Responsive sizing

Color Palette:
- Primary sequence: ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#9c27b0"]
- Categorical: Distinct colors for categories
- Sequential: Blue gradient for intensity
- Diverging: Red-White-Green for good/bad

Usage:
    from ui.charts import churn_trend_chart, retailer_tier_pie
    
    fig = churn_trend_chart(churn_data)
    st.plotly_chart(fig, use_container_width=True)
"""

import plotly.express as px
import plotly.graph_objects as go
from typing import Any, List, Optional


# Color constants
COLORS = {
    "primary": "#1a73e8",
    "success": "#34a853",
    "warning": "#fbbc04",
    "danger": "#ea4335",
    "purple": "#9c27b0",
    "teal": "#00bcd4",
    "orange": "#ff9800",
}

TIER_COLORS = {
    "Gold": "#FFD700",
    "Silver": "#C0C0C0",
    "Bronze": "#CD7F32",
}

PRIORITY_COLORS = {
    "P1_CRITICAL": "#ea4335",
    "P2_HIGH": "#fbbc04",
    "P3_MEDIUM": "#1a73e8",
}


def apply_chart_theme(fig: go.Figure) -> go.Figure:
    """
    Apply consistent theming to a Plotly figure.
    
    Args:
        fig: Plotly figure to style
        
    Returns:
        Styled figure
    """
    fig.update_layout(
        font_family="Inter, sans-serif",
        title_font_size=16,
        title_font_color="#202124",
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=40, t=60, b=40)
    )
    return fig


def churn_trend_chart(
    dates: List[str],
    churn_counts: List[int],
    baseline: List[int] = None
) -> go.Figure:
    """
    Line chart showing churn trends over time.
    
    Args:
        dates: X-axis dates
        churn_counts: Y-axis churn counts
        baseline: Optional baseline for comparison
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)


def retailer_tier_pie(tier_counts: dict) -> go.Figure:
    """
    Pie chart showing retailer distribution by tier.
    
    Args:
        tier_counts: Dict like {"Gold": 50, "Silver": 150, "Bronze": 300}
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)


def revenue_by_category_bar(categories: List[str], revenues: List[float]) -> go.Figure:
    """
    Horizontal bar chart showing revenue by product category.
    
    Args:
        categories: Category names
        revenues: Revenue values
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)


def insight_priority_gauge(priority: str, confidence: float) -> go.Figure:
    """
    Gauge chart showing insight priority and confidence.
    
    Args:
        priority: P1_CRITICAL, P2_HIGH, P3_MEDIUM
        confidence: Confidence score (0-1)
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)


def retailer_map(
    latitudes: List[float],
    longitudes: List[float],
    names: List[str],
    sizes: List[float] = None,
    colors: List[str] = None
) -> go.Figure:
    """
    Scatter map showing retailer locations.
    
    Args:
        latitudes: Lat coordinates
        longitudes: Lon coordinates
        names: Retailer names for tooltips
        sizes: Optional marker sizes
        colors: Optional marker colors
        
    Returns:
        Plotly figure with map
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return fig


def cross_sell_heatmap(
    categories: List[str],
    affinity_matrix: List[List[float]]
) -> go.Figure:
    """
    Heatmap showing category affinity scores.
    
    Args:
        categories: Category names for axes
        affinity_matrix: 2D matrix of affinity scores
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)


def sales_rep_performance_bar(
    rep_names: List[str],
    strike_rates: List[float],
    target: float = 0.5
) -> go.Figure:
    """
    Bar chart showing sales rep strike rates with target line.
    
    Args:
        rep_names: Sales rep names/IDs
        strike_rates: Productivity rates (0-1)
        target: Target strike rate
        
    Returns:
        Plotly figure
    """
    # Implementation will be added in Phase 7
    fig = go.Figure()
    return apply_chart_theme(fig)
