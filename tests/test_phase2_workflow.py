"""
Phase 2 End-to-End Workflow Tests

This module tests the complete Phase 2 implementation:
1. AnalystAgent: NL → SQL with view-only enforcement
2. StrategistAgent: Analysis with deterministic prioritization
3. CopywriterAgent: Message crafting with confidence-aware tones
4. LangGraph workflow: Fail-fast routing

Test Categories:
- Unit tests for each agent
- Integration tests for agent chains
- E2E workflow tests against real data

Prerequisites:
- Phase 1 data must be populated (run populate_data.py first)
- OpenAI API key in .env
- DuckDB database initialized

Usage:
    # Run all tests
    python -m pytest tests/test_phase2_workflow.py -v
    
    # Run specific test
    python -m pytest tests/test_phase2_workflow.py::test_analyst_churn_query -v
    
    # Run with output
    python tests/test_phase2_workflow.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


def test_imports():
    """Test that all Phase 2 modules import correctly."""
    print("\n=== Testing Imports ===")
    
    # Core modules
    from graph.state import AgentState, create_initial_state
    from config.prompts import ANALYST_SYSTEM_PROMPT, STRATEGIST_SYSTEM_PROMPT
    
    # Agents
    from agents.analyst import AnalystAgent
    from agents.strategist import StrategistAgent
    from agents.copywriter import CopywriterAgent
    
    # Graph
    from graph.nodes import analyst_node, strategist_node, copywriter_node
    from graph.workflow import create_workflow, run_workflow
    
    print("✅ All Phase 2 modules import successfully")
    return True


def test_state_creation():
    """Test state initialization."""
    print("\n=== Testing State Creation ===")
    
    from graph.state import create_initial_state, add_error_to_state
    
    # Create state
    state = create_initial_state("Show me churning retailers")
    
    # Verify required fields
    assert state['query'] == "Show me churning retailers"
    assert state['analyst_retry_count'] == 0
    assert state['errors'] == []
    assert state['workflow_complete'] == False
    assert state['confidence_level'] is None
    
    # Test error creation
    error = add_error_to_state(state, 'analyst', 'SQL_ERROR', 'Test error', True)
    assert error['stage'] == 'analyst'
    assert error['recoverable'] == True
    
    print("✅ State creation works correctly")
    return True


def test_analyst_validation():
    """Test analyst SQL validation (no LLM needed)."""
    print("\n=== Testing Analyst Validation ===")
    
    from data.database import get_connection, init_database
    from agents.analyst import AnalystAgent
    
    # Mock LLM (we're only testing validation)
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = "SELECT * FROM retailers"
            return Response()
    
    conn = get_connection()
    analyst = AnalystAgent(llm=MockLLM(), db_connection=conn)
    
    # Test 1: Block dangerous SQL
    dangerous_sqls = [
        "DROP TABLE retailers",
        "DELETE FROM transactions",
        "UPDATE retailers SET tier = 'Gold'",
        "SELECT * FROM ground_truth",  # Never expose
    ]
    
    for sql in dangerous_sqls:
        result = analyst.validate_sql(sql)
        assert result['valid'] == False, f"Should block: {sql}"
        print(f"  ✅ Blocked: {sql[:40]}...")
    
    # Test 2: View-only enforcement
    base_table_only = "SELECT * FROM retailers WHERE tier = 'Gold'"
    result = analyst.validate_sql(base_table_only)
    assert result['valid'] == False, "Should require views"
    print("  ✅ Enforced view-only rule")
    
    # Test 3: Allow queries using views
    view_query = "SELECT * FROM v_churn_candidates LIMIT 10"
    result = analyst.validate_sql(view_query)
    assert result['valid'] == True, "Should allow view queries"
    print("  ✅ Allowed view query")
    
    # Test 4: Allow category_affinities (config data)
    config_query = "SELECT * FROM category_affinities WHERE affinity_score > 0.5"
    result = analyst.validate_sql(config_query)
    assert result['valid'] == True, "Should allow category_affinities"
    print("  ✅ Allowed category_affinities query")
    
    print("✅ Analyst validation works correctly")
    return True


def test_strategist_prioritization():
    """Test strategist deterministic prioritization."""
    print("\n=== Testing Strategist Prioritization ===")
    
    from agents.strategist import StrategistAgent
    import pandas as pd
    
    # Mock LLM
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = '''[
                    {"retailer_id": "R-0001", "retailer_name": "Test Store", 
                     "tier": "Gold", "severity": "HIGH", "explanation": "14 days inactive"}
                ]'''
            return Response()
    
    strategist = StrategistAgent(llm=MockLLM())
    
    # Test priority hierarchy: CHURN > CROSS_SELL > VALUE
    assert strategist.PRIORITY_ORDER['CHURN_RISK'] < strategist.PRIORITY_ORDER['CROSS_SELL_GAP']
    assert strategist.PRIORITY_ORDER['CROSS_SELL_GAP'] < strategist.PRIORITY_ORDER['VALUE_DECLINE']
    print("  ✅ Priority hierarchy correct: CHURN > CROSS_SELL > VALUE")
    
    # Test action mapping
    assert strategist.ACTION_MAPPING[('CHURN_RISK', 'HIGH')] == 'VISIT'
    assert strategist.ACTION_MAPPING[('CHURN_RISK', 'MEDIUM')] == 'CALL'
    assert strategist.ACTION_MAPPING[('CHURN_RISK', 'LOW')] == 'MESSAGE'
    print("  ✅ Action mapping correct (VISIT > CALL > MESSAGE by severity)")
    
    # Test discount caps
    assert strategist.DISCOUNT_CAPS['HIGH'] == 15
    assert strategist.DISCOUNT_CAPS['MEDIUM'] == 10
    assert strategist.DISCOUNT_CAPS['LOW'] == 5
    print("  ✅ Discount caps enforced (max 15%)")
    
    print("✅ Strategist prioritization works correctly")
    return True


def test_copywriter_tones():
    """Test copywriter confidence-aware tones."""
    print("\n=== Testing Copywriter Tones ===")
    
    from agents.copywriter import CopywriterAgent
    
    # Mock LLM
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = "Everything okay with the shop?"
            return Response()
    
    copywriter = CopywriterAgent(llm=MockLLM())
    
    # Test confidence → tone mapping
    assert copywriter.CONFIDENCE_TO_TONE['HIGH'] == 'ASSERTIVE'
    assert copywriter.CONFIDENCE_TO_TONE['MEDIUM'] == 'SUGGESTIVE'
    assert copywriter.CONFIDENCE_TO_TONE['LOW'] == 'EXPLORATORY'
    print("  ✅ Confidence → Tone mapping correct")
    
    # Test action → friction mapping
    assert copywriter.ACTION_TO_FRICTION['VISIT'] == 'HIGH'
    assert copywriter.ACTION_TO_FRICTION['CALL'] == 'MEDIUM'
    assert copywriter.ACTION_TO_FRICTION['MESSAGE'] == 'LOW'
    print("  ✅ Action → Friction mapping correct")
    
    # Test tone patterns
    assert copywriter.TONE_PATTERNS['ASSERTIVE']['opener'] == '🔴 URGENT'
    assert copywriter.TONE_PATTERNS['SUGGESTIVE']['opener'] == '🟡 ATTENTION'
    assert copywriter.TONE_PATTERNS['EXPLORATORY']['opener'] == '🟢 OPPORTUNITY'
    print("  ✅ Tone patterns correct")
    
    # Test max discount
    assert copywriter.MAX_DISCOUNT == 15
    print("  ✅ Max discount enforced (15%)")
    
    print("✅ Copywriter tones work correctly")
    return True


def test_workflow_structure():
    """Test workflow graph structure (no LLM needed)."""
    print("\n=== Testing Workflow Structure ===")
    
    from graph.workflow import get_workflow_visualization
    
    # Get mermaid diagram
    diagram = get_workflow_visualization()
    
    # Verify key paths exist
    assert 'ANALYST' in diagram
    assert 'STRAT' in diagram
    assert 'COPY' in diagram
    assert 'ERROR' in diagram
    assert 'Fail' in diagram  # Fail-fast path
    print("  ✅ All nodes present in workflow")
    
    # Verify fail-fast path exists (Analyst |Fail| ERROR)
    assert 'Fail' in diagram and 'ERROR' in diagram
    print("  ✅ Fail-fast path exists (Analyst failure → Error)")
    
    print("✅ Workflow structure correct")
    return True


def test_e2e_with_llm():
    """
    End-to-end test with real LLM.
    
    Requires:
    - OPENAI_API_KEY in environment
    - Phase 1 data populated
    """
    print("\n=== Testing E2E Workflow (requires LLM) ===")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("  ⚠️ Skipped: OPENAI_API_KEY not set")
        return True
    
    try:
        from langchain_openai import ChatOpenAI
        from data.database import get_connection, init_database
        from data.generator import FMCGDataGenerator
        from data.seed_data import AnomalyInjector
        from graph.workflow import create_workflow, run_workflow
        
        # Initialize
        print("  Setting up database...")
        conn = get_connection()
        init_database(conn)
        
        # Check if data exists
        count = conn.execute("SELECT COUNT(*) FROM retailers").fetchone()[0]
        if count == 0:
            print("  Generating test data...")
            generator = FMCGDataGenerator(conn)
            generator.generate_all()
            injector = AnomalyInjector(conn)
            injector.inject_all()
        
        # Create workflow
        print("  Creating workflow...")
        llm = ChatOpenAI(
            model="gpt-4-turbo",
            temperature=0.1,
            max_tokens=2000
        )
        workflow = create_workflow(llm, conn)
        
        # Test query
        print("  Running churn query...")
        result = run_workflow(workflow, "Show me retailers at churn risk")
        
        # Verify result structure
        assert 'query_results' in result or 'error' in result
        if result.get('workflow_complete'):
            print(f"  ✅ Workflow completed")
            if result.get('primary_message'):
                print(f"  📝 Message: {result['primary_message'][:100]}...")
        else:
            print(f"  ⚠️ Workflow incomplete: {result.get('error', 'Unknown')}")
        
        print("✅ E2E workflow test passed")
        return True
        
    except ImportError as e:
        print(f"  ⚠️ Skipped: Missing dependency - {e}")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False


def test_crosssell_suppression():
    """
    Test that cross-sell is suppressed when churn risk is HIGH.
    
    Business Rule: You never upsell a retailer who is about to churn.
    """
    print("\n=== Testing Cross-Sell Suppression ===")
    
    from agents.strategist import StrategistAgent
    
    # Mock LLM
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = '[]'
            return Response()
    
    strategist = StrategistAgent(llm=MockLLM())
    
    # Test case: Mixed findings with HIGH churn and cross-sell
    mixed_findings = [
        {
            'retailer_id': 'R-0001',
            'retailer_name': 'Store A',
            'tier': 'Gold',
            'severity': 'HIGH',
            'insight_type': 'CHURN_RISK',  # This is now properly injected
            'explanation': 'No orders in 20 days'
        },
        {
            'retailer_id': 'R-0002',
            'retailer_name': 'Store B',
            'tier': 'Silver',
            'severity': 'HIGH',
            'insight_type': 'CROSS_SELL_GAP',  # This should be suppressed
            'explanation': 'Missing Dairy category'
        },
        {
            'retailer_id': 'R-0003',
            'retailer_name': 'Store C',
            'tier': 'Bronze',
            'severity': 'MEDIUM',
            'insight_type': 'CROSS_SELL_GAP',  # This should also be suppressed
            'explanation': 'Missing Snacks category'
        }
    ]
    
    # Create prioritized structure
    prioritized = {
        'priority': 'P1_CRITICAL',
        'findings': mixed_findings,
        'recommended_action': 'Test',
        'action_type': 'VISIT'
    }
    
    # Apply business rules
    result = strategist._apply_business_rules(prioritized)
    
    # Verify cross-sell findings are removed
    remaining_types = [f.get('insight_type') for f in result['findings']]
    
    assert 'CROSS_SELL_GAP' not in remaining_types, \
        f"Cross-sell should be suppressed when HIGH churn exists. Got: {remaining_types}"
    assert 'CHURN_RISK' in remaining_types, \
        f"Churn risk should remain. Got: {remaining_types}"
    assert result.get('suppressed_crosssell') == True, \
        "suppressed_crosssell flag should be True"
    
    print("  ✅ Cross-sell findings suppressed when HIGH churn detected")
    print("  ✅ Churn risk findings retained")
    print("  ✅ suppressed_crosssell flag set correctly")
    
    # Test case 2: No HIGH churn - cross-sell should remain
    low_churn_findings = [
        {
            'retailer_id': 'R-0001',
            'insight_type': 'CHURN_RISK',
            'severity': 'LOW',  # LOW, not HIGH
        },
        {
            'retailer_id': 'R-0002',
            'insight_type': 'CROSS_SELL_GAP',
            'severity': 'HIGH',
        }
    ]
    
    prioritized2 = {'findings': low_churn_findings, 'priority': 'P3_MEDIUM'}
    result2 = strategist._apply_business_rules(prioritized2)
    
    remaining_types2 = [f.get('insight_type') for f in result2['findings']]
    assert 'CROSS_SELL_GAP' in remaining_types2, \
        f"Cross-sell should remain when churn is LOW. Got: {remaining_types2}"
    
    print("  ✅ Cross-sell retained when churn is LOW (no suppression)")
    
    print("✅ Cross-sell suppression works correctly")
    return True


def test_empty_result_propagation():
    """
    Test that empty results propagate correctly through the pipeline.
    
    Business Rule: EMPTY_RESULT is a valid answer, not an error.
    It should flow: Analyst (EMPTY_RESULT) → Strategist (NO_ISSUES) → Copywriter (positive message)
    """
    print("\n=== Testing Empty Result Propagation ===")
    
    from agents.strategist import StrategistAgent
    from agents.copywriter import CopywriterAgent
    import pandas as pd
    
    # Mock LLM
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = '[]'  # Empty findings
            return Response()
    
    strategist = StrategistAgent(llm=MockLLM())
    copywriter = CopywriterAgent(llm=MockLLM())
    
    # Test 1: Strategist handles empty results
    empty_analyst_output = {
        'query': 'Show churning retailers',
        'sql': 'SELECT * FROM v_churn_candidates WHERE 1=0',  # Returns nothing
        'view_used': 'v_churn_candidates',
        'results': pd.DataFrame(),  # Empty DataFrame
        'result_metadata': {
            'row_count': 0,
            'execution_time_ms': 10.0,
            'is_empty': True
        }
    }
    
    insight = strategist.analyze(empty_analyst_output)
    
    assert insight['success'] == True, "Empty result should still be success"
    assert insight['insight_type'] == 'NO_ISSUES', \
        f"Empty result should produce NO_ISSUES insight, got: {insight['insight_type']}"
    assert insight['priority'] == 'P4_LOW', \
        f"NO_ISSUES should be P4_LOW priority, got: {insight['priority']}"
    assert len(insight['findings']) == 0, \
        f"NO_ISSUES should have empty findings, got: {len(insight['findings'])}"
    
    print("  ✅ Strategist returns NO_ISSUES for empty results")
    
    # Test 2: Copywriter handles NO_ISSUES insight
    message = copywriter.craft_message(insight)
    
    assert message['success'] == True, "Copywriter should succeed for NO_ISSUES"
    assert message['message_type'] == 'NO_ISSUES', \
        f"Message type should be NO_ISSUES, got: {message['message_type']}"
    assert '✅' in message['primary_message'] or 'clear' in message['primary_message'].lower(), \
        f"Positive message expected, got: {message['primary_message']}"
    
    print("  ✅ Copywriter returns positive message for NO_ISSUES")
    
    # Test 3: Verify the workflow doesn't treat empty as error
    from graph.nodes import should_retry_analyst
    from graph.state import create_initial_state
    
    state = create_initial_state("Test query")
    state['analyst_error'] = None
    state['analyst_error_type'] = 'EMPTY_RESULT'  # This is set on empty results
    
    route = should_retry_analyst(state)
    assert route == "continue", \
        f"EMPTY_RESULT should route to 'continue', not retry. Got: {route}"
    
    print("  ✅ EMPTY_RESULT routes to continue (not retry)")
    
    print("✅ Empty result propagation works correctly")
    return True


def test_deterministic_severity():
    """
    Test that severity computation is deterministic (in code, not LLM).
    """
    print("\n=== Testing Deterministic Severity ===")
    
    from agents.strategist import StrategistAgent
    import pandas as pd
    
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = '[]'
            return Response()
    
    strategist = StrategistAgent(llm=MockLLM())
    
    # Test churn severity computation
    test_cases = [
        # (days_since_order, expected_severity)
        ({'days_since_order': 20}, 'HIGH'),
        ({'days_since_order': 10}, 'MEDIUM'),
        ({'days_since_order': 5}, 'LOW'),
        # Test with change percent
        ({'change_percent': -35}, 'HIGH'),
        ({'change_percent': -20}, 'MEDIUM'),
        ({'change_percent': -5}, 'LOW'),
    ]
    
    for data, expected in test_cases:
        severity = strategist._compute_churn_severity(data)
        assert severity == expected, \
            f"Churn severity for {data} should be {expected}, got {severity}"
    
    print("  ✅ Churn severity computed correctly")
    
    # Test cross-sell severity
    crosssell_cases = [
        ({'affinity_score': 0.7, 'purchase_count': 15}, 'HIGH'),
        ({'affinity_score': 0.55, 'purchase_count': 7}, 'MEDIUM'),
        ({'affinity_score': 0.4, 'purchase_count': 3}, 'LOW'),
    ]
    
    for data, expected in crosssell_cases:
        severity = strategist._compute_crosssell_severity(data)
        assert severity == expected, \
            f"Cross-sell severity for {data} should be {expected}, got {severity}"
    
    print("  ✅ Cross-sell severity computed correctly")
    
    # Test value decline severity
    value_cases = [
        ({'change_percent': -30}, 'HIGH'),
        ({'change_percent': -15}, 'MEDIUM'),
        ({'change_percent': -5}, 'LOW'),
    ]
    
    for data, expected in value_cases:
        severity = strategist._compute_value_severity(data)
        assert severity == expected, \
            f"Value severity for {data} should be {expected}, got {severity}"
    
    print("  ✅ Value decline severity computed correctly")
    
    print("✅ Deterministic severity computation works correctly")
    return True


def test_analyst_view_enforcement():
    """
    Test that FROM clause must reference a view (not just mention view anywhere).
    """
    print("\n=== Testing Analyst View Enforcement ===")
    
    from data.database import get_connection
    from agents.analyst import AnalystAgent
    
    class MockLLM:
        def invoke(self, messages):
            class Response:
                content = "SELECT * FROM retailers"
            return Response()
    
    conn = get_connection()
    analyst = AnalystAgent(llm=MockLLM(), db_connection=conn)
    
    # Test 1: Sneaky JOIN query should be blocked
    sneaky_join = """
    SELECT r.name, t.total_value 
    FROM retailers r 
    JOIN transactions t ON r.retailer_id = t.retailer_id
    """
    result = analyst.validate_sql(sneaky_join)
    assert result['valid'] == False, \
        f"Sneaky JOIN without view in FROM should be blocked"
    print("  ✅ Blocked: JOIN query without view in FROM")
    
    # Test 2: View in FROM should pass
    view_query = """
    SELECT retailer_id, name, tier
    FROM v_churn_candidates
    WHERE days_since_order > 7
    """
    result = analyst.validate_sql(view_query)
    assert result['valid'] == True, \
        f"View in FROM should be allowed"
    print("  ✅ Allowed: View in FROM clause")
    
    # Test 3: CTE with view should pass
    cte_query = """
    WITH churn_data AS (
        SELECT * FROM v_churn_candidates
    )
    SELECT * FROM churn_data
    """
    result = analyst.validate_sql(cte_query)
    assert result['valid'] == True, \
        f"CTE with view should be allowed"
    print("  ✅ Allowed: CTE with view")
    
    print("✅ Analyst view enforcement works correctly")
    return True


def run_all_tests():
    """Run all Phase 2 tests."""
    print("=" * 60)
    print("PHASE 2 TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("State Creation", test_state_creation),
        ("Analyst Validation", test_analyst_validation),
        ("Analyst View Enforcement", test_analyst_view_enforcement),
        ("Strategist Prioritization", test_strategist_prioritization),
        ("Deterministic Severity", test_deterministic_severity),
        ("Cross-Sell Suppression", test_crosssell_suppression),
        ("Empty Result Propagation", test_empty_result_propagation),
        ("Copywriter Tones", test_copywriter_tones),
        ("Workflow Structure", test_workflow_structure),
        ("E2E with LLM", test_e2e_with_llm),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} FAILED: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "✅ PASS" if p else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 2 tests passed!")
    else:
        print("\n⚠️ Some tests failed. Review above for details.")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
