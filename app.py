"""
SalesFlow AI - Main Application Entry Point

Responsibility:
- Initialize Streamlit application
- Configure page settings and styling
- Orchestrate UI layout and components
- Handle user interactions and session state
- Invoke the agent workflow pipeline

Explicitly NOT responsible for:
- Business logic (handled by agents)
- Data processing (handled by data layer)
- Agent orchestration details (handled by graph layer)
- Individual component rendering (handled by ui modules)

Usage:
    streamlit run app.py
"""

import streamlit as st

# Page configuration must be first Streamlit command
st.set_page_config(
    page_title="SalesFlow AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)


def main():
    """Main application entry point."""
    
    # Header
    st.title("📊 SalesFlow AI")
    st.caption("The Agentic Decision Layer for FMCG Sales")
    
    st.divider()
    
    # Placeholder for Phase 1+ implementation
    st.info(
        "🚧 **Phase 0 Complete** - Environment is configured.\n\n"
        "The following components are ready:\n"
        "- ✅ Project structure created\n"
        "- ✅ Dependencies installed\n"
        "- ✅ Configuration system working\n"
        "- ✅ DuckDB ready\n"
        "- ✅ All imports resolving\n\n"
        "**Next:** Phase 1 - Data Reality Construction"
    )
    
    # Quick validation display
    with st.expander("🔧 Environment Validation", expanded=False):
        try:
            from config.settings import Settings
            settings = Settings()
            st.success(f"✅ Settings loaded - Model: {settings.LLM_MODEL}")
        except Exception as e:
            st.error(f"❌ Settings failed: {e}")
        
        try:
            import duckdb
            conn = duckdb.connect()
            conn.execute("SELECT 1").fetchone()
            st.success("✅ DuckDB operational")
        except Exception as e:
            st.error(f"❌ DuckDB failed: {e}")
        
        try:
            from agents import analyst, strategist, copywriter
            from graph import state, nodes, workflow
            st.success("✅ All module imports successful")
        except Exception as e:
            st.error(f"❌ Import failed: {e}")


if __name__ == "__main__":
    main()
