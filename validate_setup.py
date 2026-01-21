"""
Phase 0 Validation Script

Run this to verify the SalesFlow AI setup is complete and working.
"""

def main():
    print("=" * 60)
    print("PHASE 0 VALIDATION - SalesFlow AI Setup")
    print("=" * 60)

    # Test 1: Settings
    print("\n[1/6] Testing Settings...")
    from config.settings import settings
    assert settings.LLM_MODEL == "gpt-4-turbo", "Model mismatch"
    assert settings.NUM_RETAILERS == 500, "Retailer count mismatch"
    print(f"  ✓ Settings loaded (Model: {settings.LLM_MODEL})")

    # Test 2: Prompts
    print("\n[2/6] Testing Prompts...")
    from config.prompts import ANALYST_SYSTEM_PROMPT, SCHEMA_CONTEXT
    assert "SELECT" in ANALYST_SYSTEM_PROMPT, "Analyst prompt missing SQL guidance"
    assert "retailers" in SCHEMA_CONTEXT.lower(), "Schema context missing retailers"
    print(f"  ✓ Prompts loaded ({len(ANALYST_SYSTEM_PROMPT)} chars)")

    # Test 3: Graph State
    print("\n[3/6] Testing Graph State...")
    from graph.state import AgentState, create_initial_state
    state = create_initial_state("test query")
    assert state["query"] == "test query", "State init failed"
    print("  ✓ AgentState works")

    # Test 4: DuckDB
    print("\n[4/6] Testing DuckDB...")
    import duckdb
    conn = duckdb.connect(":memory:")
    result = conn.execute("SELECT 1+1 as sum").fetchone()[0]
    assert result == 2, "DuckDB math failed"
    print("  ✓ DuckDB operational")

    # Test 5: LangChain
    print("\n[5/6] Testing LangChain imports...")
    from langchain_core.messages import HumanMessage, AIMessage
    from langgraph.graph import StateGraph
    print("  ✓ LangChain/LangGraph imports work")

    # Test 6: Data packages
    print("\n[6/6] Testing data science stack...")
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go
    from faker import Faker
    print("  ✓ Pandas, NumPy, Plotly, Faker all available")

    print("\n" + "=" * 60)
    print("✅ ALL VALIDATION TESTS PASSED!")
    print("=" * 60)
    print("\nNext: Phase 1 - Data Reality Construction")
    print("Remember: Add your OPENAI_API_KEY to .env file!")


if __name__ == "__main__":
    main()
