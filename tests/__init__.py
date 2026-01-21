"""
Tests Package

This package contains all test modules for SalesFlow AI.

Test Categories:
- test_data: Data generation and schema tests
- test_agents: Individual agent tests
- test_workflow: End-to-end workflow tests

Testing Philosophy:
- Unit tests for individual components
- Integration tests for agent chains
- End-to-end tests for complete workflows
- Golden tests for LLM output stability

Running Tests:
    # All tests
    pytest tests/
    
    # Specific module
    pytest tests/test_agents.py
    
    # With coverage
    pytest tests/ --cov=.
    
    # Verbose output
    pytest tests/ -v

Fixtures:
- sample_retailers: Pre-generated test retailers
- sample_transactions: Test transaction data
- mock_llm: LLM that returns predictable outputs
- test_db: In-memory DuckDB for testing

Usage:
    from tests.fixtures import sample_retailers, mock_llm
    
    def test_analyst_generates_valid_sql(mock_llm, test_db):
        analyst = AnalystAgent(mock_llm, test_db)
        result = analyst.generate_query("Show Gold retailers")
        assert "Gold" in result["sql"]
"""

__all__ = ["test_data", "test_agents", "test_workflow"]
