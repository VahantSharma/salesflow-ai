"""
Plotly Chart Wrappers

Responsibility:
- Create consistent, branded visualizations
- Wrap Plotly complexity in simple interfaces
- Ensure accessibility (colors, labels)
- Optimize for Streamlit rendering

Architecture Principle:
    Charts VISUALIZE data, they do NOT compute it.
    All values (current, baseline, affinity) come from backend.
    Chart functions receive ready-to-plot numbers.

Phase 3 Charts:
- render_trend_chart(): Current vs Baseline comparison
- render_crosssell_chart(): Affinity score visualization

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
    from ui.charts import render_trend_chart, render_crosssell_chart
    
    render_trend_chart(metrics, retailer_name)
    render_crosssell_chart(finding)
"""

import streamlit as st
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
    "P4_LOW": "#34a853",
}

SEVERITY_COLORS = {
    "CRITICAL": "#ea4335",
    "HIGH": "#fbbc04",
    "MEDIUM": "#1a73e8",
    "LOW": "#34a853",
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


# =============================================================================
# PHASE 3 CHARTS - RENDER FUNCTIONS FOR UI
# =============================================================================

def render_trend_chart(metrics: dict, retailer_name: str = "") -> None:
    """
    Render a comparison chart showing current vs baseline value.
    
    Uses PRE-COMPUTED metrics from backend:
    - current: Current period value
    - baseline: Previous period value
    - change_percent: Pre-computed delta
    
    UI does NOT compute - just visualizes what backend provides.
    
    Args:
        metrics: Dict with current, baseline, change_percent (from Strategist)
        retailer_name: Retailer name for title
    """
    current = metrics.get('current', 0)
    baseline = metrics.get('baseline', 0)
    change_percent = metrics.get('change_percent', 0)
    
    # =======================================================================
    # VISUAL THRESHOLD ONLY - NOT BUSINESS LOGIC
    # =======================================================================
    # These thresholds determine chart COLOR, not severity.
    # Severity is computed by Strategist using SEVERITY_THRESHOLDS.
    # UI only visualizes what backend decided.
    # =======================================================================
    if change_percent < -20:
        color = COLORS['danger']
        status = "Declining"
    elif change_percent < 0:
        color = COLORS['warning']
        status = "Down"
    else:
        color = COLORS['success']
        status = "Stable"
    
    # Create simple comparison bar chart
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=['Baseline', 'Current'],
        y=[baseline, current],
        marker_color=[COLORS['primary'], color],
        text=[f"₹{baseline:,.0f}", f"₹{current:,.0f}"],
        textposition='outside',
        hovertemplate="<b>%{x}</b><br>Value: ₹%{y:,.0f}<extra></extra>"
    ))
    
    # Add annotation for change
    fig.add_annotation(
        x=1,
        y=current,
        text=f"{change_percent:+.1f}%",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowcolor=color,
        font=dict(size=14, color=color)
    )
    
    fig.update_layout(
        title=f"Value Trend{f' - {retailer_name}' if retailer_name else ''}",
        yaxis_title="Value (₹)",
        showlegend=False,
        height=300,
    )
    
    fig = apply_chart_theme(fig)
    st.plotly_chart(fig, use_container_width=True)
    
    # Status caption
    st.caption(f"📊 {status} | Change: {change_percent:+.1f}%")


def render_crosssell_chart(finding: dict) -> None:
    """
    Render a visualization for cross-sell opportunity.
    
    Uses PRE-COMPUTED metrics from backend:
    - affinity_score: How likely customer will buy
    - has_category: Category they already purchase
    - missing_category: Category gap to target
    
    UI does NOT compute - just visualizes what backend provides.
    
    Args:
        finding: Finding dict with metrics (from Strategist)
    """
    metrics = finding.get('metrics', {})
    
    affinity = metrics.get('affinity_score', 0)
    has_category = metrics.get('has_category', 'Current Category')
    missing_category = metrics.get('missing_category', 'Target Category')
    purchase_count = metrics.get('purchase_count', 0)
    
    # Affinity gauge chart
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=affinity * 100,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "Cross-Sell Affinity", 'font': {'size': 16}},
        delta={'reference': 50, 'increasing': {'color': COLORS['success']}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': COLORS['primary']},
            'bgcolor': "white",
            'steps': [
                {'range': [0, 33], 'color': '#ffebee'},
                {'range': [33, 66], 'color': '#fff3e0'},
                {'range': [66, 100], 'color': '#e8f5e9'}
            ],
            'threshold': {
                'line': {'color': COLORS['success'], 'width': 4},
                'thickness': 0.75,
                'value': 70
            }
        },
        number={'suffix': '%', 'font': {'size': 24}}
    ))
    
    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Category flow visualization
    col1, col2, col3 = st.columns([2, 1, 2])
    
    with col1:
        st.markdown(f"**Has:** {has_category}")
        if purchase_count:
            st.caption(f"{purchase_count} purchases")
    
    with col2:
        st.markdown("**→**")
    
    with col3:
        st.markdown(f"**Gap:** {missing_category}")
        st.caption("Opportunity")
    
    # Confidence indicator
    if affinity >= 0.7:
        st.success(f"✅ High affinity ({affinity:.0%}) - Strong opportunity")
    elif affinity >= 0.5:
        st.info(f"ℹ️ Moderate affinity ({affinity:.0%}) - Worth considering")
    else:
        st.warning(f"⚠️ Low affinity ({affinity:.0%}) - May need nurturing")


# =============================================================================
# LEGACY CHART FUNCTIONS (For future phases)
# =============================================================================

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
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=churn_counts,
        mode='lines+markers',
        name='Churn Count',
        line=dict(color=COLORS['danger'], width=2),
        marker=dict(size=8)
    ))
    
    if baseline:
        fig.add_trace(go.Scatter(
            x=dates,
            y=baseline,
            mode='lines',
            name='Baseline',
            line=dict(color=COLORS['primary'], width=2, dash='dash')
        ))
    
    fig.update_layout(
        title="Churn Trend",
        xaxis_title="Date",
        yaxis_title="Count",
        hovermode='x unified'
    )
    
    return apply_chart_theme(fig)


def retailer_tier_pie(tier_counts: dict) -> go.Figure:
    """
    Pie chart showing retailer distribution by tier.
    
    Args:
        tier_counts: Dict like {"Gold": 50, "Silver": 150, "Bronze": 300}
        
    Returns:
        Plotly figure
    """
    labels = list(tier_counts.keys())
    values = list(tier_counts.values())
    colors = [TIER_COLORS.get(tier, COLORS['primary']) for tier in labels]
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=colors,
        textposition='inside',
        textinfo='percent+label'
    )])
    
    fig.update_layout(title="Retailer Distribution by Tier")
    
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
    fig = go.Figure(go.Bar(
        x=revenues,
        y=categories,
        orientation='h',
        marker_color=COLORS['primary'],
        text=[f"₹{r:,.0f}" for r in revenues],
        textposition='auto'
    ))
    
    fig.update_layout(
        title="Revenue by Category",
        xaxis_title="Revenue (₹)",
        yaxis_title="Category"
    )
    
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
    color = PRIORITY_COLORS.get(priority, COLORS['primary'])
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=confidence * 100,
        title={'text': f"Priority: {priority}"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 50], 'color': '#ffebee'},
                {'range': [50, 75], 'color': '#fff3e0'},
                {'range': [75, 100], 'color': '#e8f5e9'}
            ]
        },
        number={'suffix': '%'}
    ))
    
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
    fig = go.Figure(go.Scattermapbox(
        lat=latitudes,
        lon=longitudes,
        mode='markers',
        marker=dict(
            size=sizes if sizes else [10] * len(names),
            color=colors if colors else COLORS['primary']
        ),
        text=names,
        hoverinfo='text'
    ))
    
    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(
                lat=sum(latitudes) / len(latitudes) if latitudes else 0,
                lon=sum(longitudes) / len(longitudes) if longitudes else 0
            ),
            zoom=10
        ),
        margin=dict(l=0, r=0, t=0, b=0)
    )
    
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
    fig = go.Figure(data=go.Heatmap(
        z=affinity_matrix,
        x=categories,
        y=categories,
        colorscale='Blues',
        hoverongaps=False,
        text=[[f"{val:.0%}" for val in row] for row in affinity_matrix],
        texttemplate="%{text}",
        textfont={"size": 10}
    ))
    
    fig.update_layout(
        title="Category Affinity Matrix",
        xaxis_title="Missing Category",
        yaxis_title="Has Category"
    )
    
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
    colors = [
        COLORS['success'] if rate >= target else COLORS['danger']
        for rate in strike_rates
    ]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=rep_names,
        y=[r * 100 for r in strike_rates],
        marker_color=colors,
        text=[f"{r:.0%}" for r in strike_rates],
        textposition='outside'
    ))
    
    fig.add_hline(
        y=target * 100,
        line_dash="dash",
        line_color=COLORS['primary'],
        annotation_text=f"Target: {target:.0%}"
    )
    
    fig.update_layout(
        title="Sales Rep Performance",
        xaxis_title="Sales Rep",
        yaxis_title="Strike Rate (%)",
        yaxis_range=[0, 100]
    )
    
    return apply_chart_theme(fig)
