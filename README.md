# SalesFlow AI

## The Agentic Decision Layer for FMCG Sales

SalesFlow AI is a Multi-Agent System that autonomously detects retailer churn risks and cross-sell opportunities, producing specific, safe, explainable action recommendations for sales managers.

---

## Quick Start

### 1. Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
```

### 3. Run the Application

```bash
streamlit run app.py
```

---

## Project Structure

```
salesflow_ai/
├── app.py                    # Streamlit entry point
├── requirements.txt          # Dependencies
├── Dockerfile               # Container definition
├── .env.example             # Environment template
│
├── config/                  # Configuration management
│   ├── settings.py          # Centralized settings (Pydantic)
│   └── prompts.py           # All LLM prompts
│
├── data/                    # Data layer
│   ├── schema.sql           # DuckDB schema
│   ├── generator.py         # Synthetic data generation
│   └── seed_data.py         # Anomaly injection
│
├── agents/                  # AI Agents
│   ├── analyst.py           # SQL generation agent
│   ├── strategist.py        # Risk analysis agent
│   ├── copywriter.py        # Message generation agent
│   └── guardrails.py        # Output safety checks
│
├── graph/                   # LangGraph orchestration
│   ├── state.py             # State schema
│   ├── nodes.py             # Node functions
│   └── workflow.py          # Graph construction
│
├── ui/                      # Streamlit UI
│   ├── components.py        # Reusable components
│   ├── layouts.py           # Page layouts
│   └── charts.py            # Visualizations
│
└── tests/                   # Test suite
    ├── test_data.py
    ├── test_agents.py
    └── test_workflow.py
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER (Streamlit)               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ORCHESTRATION LAYER (LangGraph)                │
│   Router → Analyst → Strategist → Copywriter → Guardrails      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (DuckDB)                        │
│         Retailers │ Products │ Transactions │ Visits           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

- **Churn Detection**: Identifies retailers with declining order frequency
- **Cross-Sell Gaps**: Finds missing category opportunities
- **Safe Recommendations**: Guardrails prevent harmful outputs
- **Human-in-the-Loop**: All actions require manager approval

---

## Tech Stack

| Component     | Technology  |
| ------------- | ----------- |
| LLM           | GPT-4 Turbo |
| Orchestration | LangGraph   |
| Database      | DuckDB      |
| UI            | Streamlit   |
| Visualization | Plotly      |

---

