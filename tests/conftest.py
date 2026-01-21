"""
Pytest Configuration and Shared Fixtures

This file contains fixtures available to all test modules.
"""

import pytest
from typing import Generator, Any


# === Markers ===

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "llm: marks tests that require LLM API")


# === Database Fixtures ===

@pytest.fixture(scope="session")
def duckdb_connection():
    """
    Session-scoped DuckDB connection.
    
    Creates database once for entire test session.
    """
    # Will be implemented in Phase 1
    yield None


@pytest.fixture
def fresh_db():
    """
    Function-scoped DuckDB connection.
    
    Fresh database for each test.
    """
    # Will be implemented in Phase 1
    yield None


# === LLM Fixtures ===

@pytest.fixture
def mock_llm():
    """
    Mock LLM for unit tests.
    
    Returns predictable responses based on input patterns.
    """
    # Will be implemented in Phase 2
    yield None


@pytest.fixture
def real_llm():
    """
    Real LLM connection for integration tests.
    
    Requires OPENAI_API_KEY in environment.
    """
    # Will be implemented in Phase 2
    yield None


# === Data Fixtures ===

@pytest.fixture
def sample_retailers():
    """Small set of test retailers."""
    return [
        {"retailer_id": "R-001", "name": "Test Store 1", "tier": "Gold"},
        {"retailer_id": "R-002", "name": "Test Store 2", "tier": "Silver"},
        {"retailer_id": "R-003", "name": "Test Store 3", "tier": "Bronze"},
    ]


@pytest.fixture
def sample_products():
    """Small set of test products."""
    return [
        {"sku_id": "SKU-001", "name": "Cola 500ml", "category": "Carbonated Beverages"},
        {"sku_id": "SKU-002", "name": "Chips 100g", "category": "Salty Snacks"},
    ]


@pytest.fixture
def sample_transactions(sample_retailers, sample_products):
    """Test transactions linking retailers and products."""
    return [
        {"txn_id": "TXN-001", "retailer_id": "R-001", "sku_id": "SKU-001", "quantity": 10},
        {"txn_id": "TXN-002", "retailer_id": "R-001", "sku_id": "SKU-002", "quantity": 5},
    ]


# === Agent Output Fixtures ===

@pytest.fixture
def analyst_success_output():
    """Successful analyst output."""
    return {
        "success": True,
        "sql": "SELECT retailer_id, name FROM retailers WHERE tier = 'Gold'",
        "results": [],  # Would be DataFrame
        "explanation": "Selecting Gold tier retailers"
    }


@pytest.fixture
def analyst_error_output():
    """Failed analyst output."""
    return {
        "success": False,
        "sql": "SELECT * FROM nonexistent_table",
        "error": "Table 'nonexistent_table' not found"
    }


@pytest.fixture
def strategist_output():
    """Sample strategist insight."""
    return {
        "insight_type": "CHURN_RISK",
        "priority": "P1_CRITICAL",
        "affected_entities": ["R-001", "R-042"],
        "business_impact": "₹47,000 monthly revenue at risk",
        "recommended_action": "Schedule sales rep visit within 48 hours",
        "confidence_score": 0.87,
        "evidence": ["14 days since last order", "3 consecutive volume declines"]
    }


@pytest.fixture
def copywriter_output():
    """Sample copywriter messages."""
    return {
        "primary_message": "Hi Ramesh, we noticed it's been 14 days since your last order. Your regular Cola stock might be running low. Shall we schedule a quick visit this week?",
        "whatsapp_variant": "🎯 Ramesh ji, your Cola stock might need a refill! It's been 14 days. Reply YES for a visit.",
        "internal_notes": "Mention new credit terms if retailer asks about payment"
    }


# === State Fixtures ===

@pytest.fixture
def initial_state():
    """Fresh workflow state."""
    from graph.state import create_initial_state
    return create_initial_state("Show me churning retailers")


# === Utility Functions ===

def assert_valid_sql(sql: str):
    """Assert SQL is syntactically valid (basic check)."""
    dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER"]
    sql_upper = sql.upper()
    for keyword in dangerous:
        assert keyword not in sql_upper, f"Dangerous keyword '{keyword}' found in SQL"


def assert_valid_insight(insight: dict):
    """Assert insight has required fields."""
    required = ["insight_type", "priority", "recommended_action"]
    for field in required:
        assert field in insight, f"Missing required field: {field}"


def assert_valid_message(message: str):
    """Assert message meets quality criteria."""
    assert len(message) <= 500, "Message too long"
    assert message.strip(), "Message is empty"
