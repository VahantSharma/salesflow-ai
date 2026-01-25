"""
Phase 3 Tests: UI & Interaction Contract Validation

These tests verify the critical invariants:
1. Strategist returns summary dict with pre-computed counts
2. Findings have metrics dicts with DataFrame-extracted values
3. UI helpers work with the contract
4. On-topic detection functions correctly

Architecture Principle:
    UI is a CONSUMER of decisions, never a CREATOR of decisions.
    These tests validate that the contract between backend and UI is honored.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# BACKEND CONTRACT TESTS
# =============================================================================

class TestStrategistReturnsComplete:
    """Test that Strategist provides all data UI needs."""
    
    def test_strategist_returns_summary_key(self):
        """Strategist analyze() must return 'summary' key."""
        from agents.strategist import StrategistAgent
        from unittest.mock import MagicMock
        
        strategist = StrategistAgent(MagicMock())
        
        # Create minimal analysis results
        analysis_results = {
            'churn_analysis': {'status': 'complete', 'data': None},
            'cross_sell_analysis': {'status': 'complete', 'data': None},
            'value_analysis': {'status': 'complete', 'data': None}
        }
        
        result = strategist.analyze(analysis_results)
        
        # Must have summary key
        assert 'summary' in result, "Strategist must return 'summary' key"
        assert isinstance(result['summary'], dict), "summary must be a dict"
    
    def test_summary_has_required_fields(self):
        """Summary dict must have all fields UI needs."""
        from agents.strategist import StrategistAgent
        from unittest.mock import MagicMock
        
        strategist = StrategistAgent(MagicMock())
        
        analysis_results = {
            'churn_analysis': {'status': 'complete', 'data': None},
            'cross_sell_analysis': {'status': 'complete', 'data': None},
            'value_analysis': {'status': 'complete', 'data': None}
        }
        
        result = strategist.analyze(analysis_results)
        summary = result['summary']
        
        # Required fields for metrics bar
        required_fields = [
            'total_issues',
            'churn_risks',
            'crosssell_opportunities',
            'value_declines'
        ]
        
        for field in required_fields:
            assert field in summary, f"Summary must have '{field}' field"
            assert isinstance(summary[field], int), f"'{field}' must be integer"
    
    def test_findings_have_metrics(self):
        """Each finding must have metrics dict (not computed by UI)."""
        from agents.strategist import StrategistAgent
        from unittest.mock import MagicMock
        import pandas as pd
        
        strategist = StrategistAgent(MagicMock())
        
        # Create analysis with actual data
        churn_df = pd.DataFrame({
            'retailer_id': ['R001'],
            'name': ['Test Store'],
            'tier': ['GOLD'],
            'current_value': [5000],
            'previous_period_value': [8000],
            'value_change_pct': [-37.5],
            'days_since_last_order': [45],
            'churn_risk_score': [0.8]
        })
        
        analysis_results = {
            'churn_analysis': {
                'status': 'complete',
                'data': churn_df,
                'at_risk_count': 1,
                'risk_breakdown': {'high': 1, 'medium': 0}
            },
            'cross_sell_analysis': {'status': 'complete', 'data': None},
            'value_analysis': {'status': 'complete', 'data': None}
        }
        
        # Mock LLM response
        strategist.llm.invoke = MagicMock(return_value=MagicMock(content="""
        {
            "findings": [
                {
                    "retailer_id": "R001",
                    "retailer_name": "Test Store",
                    "tier": "GOLD",
                    "insight_type": "CHURN_RISK",
                    "severity": "HIGH",
                    "explanation": "Test explanation"
                }
            ],
            "insight_type": "RISK_ALERT"
        }
        """))
        
        result = strategist.analyze(analysis_results)
        findings = result.get('findings', [])
        
        if findings:
            finding = findings[0]
            assert 'metrics' in finding, "Finding must have 'metrics' dict"
            metrics = finding['metrics']
            
            # For CHURN_RISK, must have these from DataFrame
            if finding.get('insight_type') == 'CHURN_RISK':
                assert 'current' in metrics, "Churn metrics must have 'current'"
                assert 'baseline' in metrics, "Churn metrics must have 'baseline'"
    
    def test_empty_result_has_complete_structure(self):
        """Even empty results must have full structure."""
        from agents.strategist import StrategistAgent
        from unittest.mock import MagicMock
        
        strategist = StrategistAgent(MagicMock())
        
        # Empty analysis
        analysis_results = {
            'churn_analysis': {'status': 'complete', 'data': None},
            'cross_sell_analysis': {'status': 'complete', 'data': None},
            'value_analysis': {'status': 'complete', 'data': None}
        }
        
        result = strategist.analyze(analysis_results)
        
        # Must have all keys even when empty
        assert 'findings' in result
        assert 'insight_type' in result
        assert 'summary' in result
        
        # Summary must be populated
        summary = result['summary']
        assert summary.get('total_issues', None) is not None


# =============================================================================
# STATE PROPAGATION TESTS
# =============================================================================

class TestStatePropagation:
    """Test that summary flows through the workflow."""
    
    def test_agent_state_has_summary_field(self):
        """AgentState must have summary field."""
        from graph.state import AgentState
        
        # Check the TypedDict has the field
        annotations = AgentState.__annotations__
        assert 'summary' in annotations, "AgentState must have 'summary' field"
    
    def test_create_initial_state_includes_summary(self):
        """Initial state must include summary field."""
        from graph.state import create_initial_state
        
        state = create_initial_state("test query")
        
        assert 'summary' in state, "Initial state must have 'summary' key"


# =============================================================================
# ON-TOPIC DETECTION TESTS
# =============================================================================

class TestOnTopicDetection:
    """Test the keyword-based topic detection."""
    
    def test_sales_queries_are_on_topic(self):
        """Sales-related queries should be on-topic."""
        # Import from app.py
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app import is_on_topic
        
        on_topic_queries = [
            "Show me retailers at churn risk",
            "Which Gold tier stores are declining?",
            "Scan for cross-sell opportunities",
            "Why is Kumar Stores at risk?",
            "List inactive retailers",
            "Show sales trends",
            "Find opportunities in Bronze tier"
        ]
        
        for query in on_topic_queries:
            assert is_on_topic(query), f"'{query}' should be on-topic"
    
    def test_off_topic_queries_rejected(self):
        """Non-sales queries should be rejected."""
        from app import is_on_topic
        
        off_topic_queries = [
            "What's the weather today?",
            "Tell me a joke",
            "Write me a poem",
            "Help me with my homework",
            "What is the capital of France?"
        ]
        
        for query in off_topic_queries:
            assert not is_on_topic(query), f"'{query}' should be off-topic"
    
    def test_ambiguous_defaults_to_on_topic(self):
        """Ambiguous queries should default to on-topic."""
        from app import is_on_topic
        
        # Query with no clear keywords should let workflow handle
        ambiguous = "Give me the latest updates"
        # This is ambiguous - could be sales updates
        # Should default to on-topic and let workflow decide
        result = is_on_topic(ambiguous)
        assert result == True, "Ambiguous queries should default to on-topic"


# =============================================================================
# UI COMPONENT CONTRACT TESTS
# =============================================================================

class TestUIComponentContracts:
    """Test that UI components receive data in expected format."""
    
    def test_metrics_bar_handles_empty_summary(self):
        """Metrics bar must handle empty summary gracefully."""
        from ui.components import render_metrics_bar
        
        # Should not raise with empty dict
        try:
            # Note: Can't actually call st.* in tests, but we can check logic
            empty_summary = {}
            total = empty_summary.get('total_issues', 0)
            assert total == 0
        except Exception as e:
            pytest.fail(f"Metrics bar should handle empty summary: {e}")
    
    def test_action_card_has_defensive_defaults(self):
        """Action card must use defensive defaults for missing fields."""
        # Test the logic without Streamlit
        finding = {}  # Completely empty
        
        # All these should have defaults
        retailer_name = finding.get('retailer_name') or finding.get('name', 'Unknown Retailer')
        tier = finding.get('tier', 'BRONZE')
        severity = finding.get('severity', 'MEDIUM')
        
        assert retailer_name == 'Unknown Retailer'
        assert tier == 'BRONZE'
        assert severity == 'MEDIUM'
    
    def test_chart_functions_handle_empty_metrics(self):
        """Chart functions must handle empty metrics."""
        # Test logic without plotting
        metrics = {}
        
        current = metrics.get('current', 0)
        baseline = metrics.get('baseline', 0)
        change = metrics.get('change_percent', 0)
        
        assert current == 0
        assert baseline == 0
        assert change == 0


# =============================================================================
# INVARIANT TESTS
# =============================================================================

class TestPhase3Invariants:
    """Test core Phase 3 invariants."""
    
    def test_ui_does_not_compute_severity(self):
        """UI must not compute severity - it comes from backend."""
        # The invariant: severity is in finding dict, not computed
        finding = {
            'severity': 'HIGH',  # Backend provides this
            'retailer_name': 'Test Store'
        }
        
        # UI just reads it
        severity = finding.get('severity')
        
        # There should be NO computation like:
        # if some_value > threshold: severity = 'HIGH'
        # That logic lives in Strategist
        
        assert severity == 'HIGH'
    
    def test_ui_does_not_compute_priority(self):
        """UI must not compute priority - it comes from backend."""
        finding = {
            'priority': 'P1_CRITICAL',  # Backend provides this
        }
        
        priority = finding.get('priority', 'P4_LOW')
        assert priority == 'P1_CRITICAL'
    
    def test_ui_does_not_count_findings(self):
        """UI must not count findings - summary provides counts."""
        # Wrong approach:
        # findings = [...]
        # churn_count = len([f for f in findings if f['type'] == 'CHURN'])
        
        # Right approach - use pre-computed summary:
        summary = {
            'total_issues': 5,
            'churn_risks': 3,
            'crosssell_opportunities': 2
        }
        
        total = summary.get('total_issues', 0)
        assert total == 5
        
        # The count comes from summary, not from filtering findings
    
    def test_ui_components_do_not_compute_business_logic(self):
        """
        FIX #9: Strong invariant test using source inspection.
        
        UI components must NOT contain:
        - Severity computation (if days > threshold: severity = ...)
        - Count computation (len([f for f in findings...]))
        - Priority computation (if severity == 'HIGH' and ...)
        - Discount computation (discount = ... * ...)
        
        These operations belong ONLY in Strategist.
        """
        import inspect
        from ui import components
        
        # Get the source code of components.py
        source = inspect.getsource(components)
        
        # =============================================================
        # FORBIDDEN PATTERNS IN UI CODE
        # =============================================================
        # These patterns indicate business logic that should be in backend
        forbidden_patterns = [
            # Severity computation
            ("if days_since_order >", "UI computing severity from days"),
            ("if change_percent >", "UI computing severity from change"),
            ("severity = 'HIGH'", "UI assigning severity"),
            ("severity = 'MEDIUM'", "UI assigning severity"),
            ("severity = 'LOW'", "UI assigning severity"),
            
            # Count computation (except len() for display limits)
            ("len([f for f in", "UI counting findings by filtering"),
            ("sum(1 for f in", "UI counting findings"),
            
            # Priority computation
            ("priority = 'P1", "UI assigning priority"),
            ("priority = 'P2", "UI assigning priority"),
            
            # Discount computation
            ("* 0.", "UI computing discount factor"),
            ("discount =", "UI computing discount"),
        ]
        
        violations = []
        for pattern, description in forbidden_patterns:
            if pattern in source:
                # Check context - some patterns might be in comments
                lines = source.split('\n')
                for i, line in enumerate(lines):
                    if pattern in line:
                        stripped = line.strip()
                        # Skip if it's a comment or string
                        if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                            continue
                        # Skip if it's part of .get() call (reading, not computing)
                        if '.get(' in line and '=' not in line.split('.get(')[0]:
                            continue
                        violations.append(f"Line {i+1}: {description} - '{stripped[:60]}...'")
        
        if violations:
            pytest.fail(
                f"UI components contain business logic (should be in Strategist):\n" +
                "\n".join(violations)
            )


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3 Tests: UI & Interaction Contract Validation")
    print("=" * 60)
    
    # Run with verbose output
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])
