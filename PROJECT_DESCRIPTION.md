# SalesFlow AI — Project Description

> *"I don't play the odds. I play the man."*
> This system was built with the same philosophy: don't trust the inference, govern it.

---

## What This Is

SalesFlow AI is a production-grade, **multi-agent AI decision system** engineered for FMCG sales intelligence. It does not generate suggestions that disappear into a chat window. It surfaces prioritized, human-reviewed, audit-traceable actions that drive measurable outcomes for sales teams.

The system identifies three categories of business risk in real time:

- **Churn Risk** — retailers whose purchase frequency is declining before they go silent
- **Cross-Sell Gaps** — active customers who are not buying categories they demonstrably should be
- **Value Decline** — order value erosion that signals wallet-share loss to a competitor

Each identified risk is ranked by severity, routed through a business rule engine, turned into a field-ready sales recommendation, and held for human approval before it becomes an official action — with a full, immutable audit trail from query to decision.

---

## The Architecture

This is not a chatbot with a database lookup bolted on. It is a **governance-first, event-sourced, multi-agent pipeline** designed under adversarial assumptions:

> *Assume the LLM hallucinates. Assume timestamps drift. Assume humans disagree. Assume audits happen months later.*

The system is built to fail safely under all of those conditions.

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  GUARDRAILS LAYER  (deterministic — no LLM)         │
│  SQL injection detection · Prompt injection          │
│  Off-topic classification · Intent labeling          │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  ANALYST AGENT  (LangGraph node)                    │
│  Natural language → SQL (GPT-4 Turbo)               │
│  View-first enforcement · SELECT-only               │
│  Self-corrects up to 2 times · Result capped at 50  │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  STRATEGIST AGENT  (rule-based, not ML confidence)  │
│  Severity classification: HIGH / MEDIUM / LOW       │
│  Priority: Churn > Cross-Sell > Value Decline       │
│  Action mapping: VISIT / CALL / MESSAGE             │
│  Business policy enforcement (15% discount cap)     │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  COPYWRITER AGENT  (LLM-assisted)                   │
│  Tone calibrated to confidence level                │
│  ≤280 characters · WhatsApp-ready · ₹ format        │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  APPROVAL SYSTEM  (event-sourced, append-only)      │
│  Human-in-the-Loop gate before any action issues    │
│  PENDING → APPROVED / REJECTED / SUPERSEDED         │
│  Zero UPDATE statements. Zero DELETE statements.    │
│  Rejection is irreversible. Replay is deterministic.│
└─────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **Language** | Python 3.10+ | Type-safe, ecosystem depth |
| **LLM Provider** | OpenAI GPT-4 Turbo | Best-in-class inference quality |
| **Agent Orchestration** | LangGraph | Stateful graph-based workflow execution |
| **LLM Framework** | LangChain | Prompt management, output parsing |
| **Data Validation** | Pydantic v2 + Pydantic Settings | Schema-enforced inputs end to end |
| **Database** | DuckDB | OLAP-optimized, zero-infrastructure SQL |
| **Data Processing** | Pandas + NumPy | DataFrame operations on query results |
| **Synthetic Data** | Faker + seeded RNG | Deterministic, reproducible test datasets |
| **UI** | Streamlit | Rapid, functional internal tooling |
| **Visualization** | Plotly | Interactive charts for manager dashboard |
| **Containerization** | Docker (Python 3.11-slim) | Clean, minimal deployment image |
| **Testing** | Pytest + pytest-asyncio + pytest-cov | Full async test coverage |
| **Code Quality** | Black + isort + Ruff + MyPy | Zero tolerance for inconsistency |

---

## Core Engineering Decisions

### 1. LLMs Are Untrusted by Default

Every LLM output passes through a governance layer before it touches state. The LLM proposes severity — code determines it. The LLM drafts messages — policy gates them. There is no path from inference to persistence that does not pass through enforcement.

### 2. Event Sourcing as a Non-Negotiable

The approval system contains **zero UPDATE and zero DELETE statements**. Current state is always the projection of an append-only event stream. This means:

- Any approval decision that ever existed can be recovered
- Time-travel queries are possible with no special tooling
- Auditors get the complete chain of custody, always

### 3. Deterministic Replay

A workflow that ran six months ago can be replayed today and produce **byte-identical output**. Replay uses the timestamp of the original execution — not wall-clock time — so temporal rules evaluated then are evaluated now, not the rules in force today.

### 4. Guardrails Without LLMs

The security boundary does not call an LLM. SQL injection, prompt injection, shell command patterns, and off-topic classification all run on deterministic pattern matching first. LLMs are invoked only for the ambiguous edge case — and never for anything that could block execution.

### 5. Priority Is a Business Rule, Not a Model Output

The Strategist agent does not use ML confidence scores to rank findings. Priority follows a hard-coded hierarchy: churn retention beats cross-sell opportunity beats value efficiency. Always. This is not configurable at runtime because human lives (and quarterly numbers) depend on the system being predictable.

---

## What the Codebase Contains

```
18,000+ lines of Python across:

  config/         — Centralized settings, prompts, policies, exception hierarchy
  data/           — DuckDB schema, synthetic FMCG data generator, anomaly injection
  agents/         — Analyst, Strategist, Copywriter, Guardrails (4 specialized agents)
  graph/          — LangGraph workflow, typed state schema, node implementations,
                    write-only trace system (793 lines)
  persistence/    — Event-sourced approval manager (1,770 lines — the core of the system)
  services/       — Thin adapter layer between UI and domain
  ui/             — Streamlit dashboard, component library, charts, layout helpers
  tests/          — 6-phase test suite: workflow, UI, trace, guardrails, approvals, HITL
  docs/           — Architecture decisions, HITL contract, phase lock documentation
```

**Notable design documents bundled in the repo:**

- `docs/PHASE2_DECISION_PHILOSOPHY.md` — Why determinism is the constraint, not the goal
- `docs/PHASE5_COMPLETE_TECHNICAL_DOCUMENTATION.md` (61 KB) — Exhaustive spec for the approval system
- `docs/PHASE5_HITL_CONTRACT.md` — Formal contract governing human-in-the-loop behavior
- `docs/PHASE6_LOCK.md` — Final system lock documentation

---

## Domain: FMCG Sales Intelligence

The system is purpose-built for the Fast-Moving Consumer Goods vertical. The data model reflects real-world FMCG complexity:

- **9 product categories** with tier-appropriate purchase patterns
- **3-tier retailer hierarchy** (Gold / Silver / Bronze) with explicit exclusion rules
- **Beat-based territory management** for field sales teams
- **Churn defined behaviorally** — days since last order, not administrative status
- **Promotion and discount tracking** at transaction level
- **Category affinity pairs** seeded from real cross-sell research (e.g., Carbonated Beverages ↔ Salty Snacks at 0.72 affinity)

Bronze retailers are excluded from churn focus by policy. Closed retailers are excluded from churn candidates. These are not bugs — they are documented, intentional business decisions.

---

## The Approval System in Detail

The most complex component is `persistence/approvals.py` at **1,770 lines**. It implements:

| Capability | Implementation |
|---|---|
| **Append-only writes** | INSERT only, never UPDATE/DELETE |
| **Scoped supersession** | New finding for same (retailer, issue_type) supersedes prior pending |
| **Referential integrity** | trace_id validated before finding creation |
| **Idempotency guards** | DB constraints prevent duplicate approvals |
| **Transactional multi-writes** | Rollback on partial failure |
| **Explicit expiration** | EXPIRED is an event type, not an inferred state |
| **Rejection analytics** | Category-level rejection tracking for process improvement |

Five state transitions exist: `PENDING → APPROVED`, `PENDING → REJECTED`, `PENDING → SUPERSEDED`, `PENDING → EXPIRED`. None of these transitions are reversible. The system is designed so that a human's decision cannot be second-guessed by re-running the workflow.

---

## Human-in-the-Loop Contract

The HITL gate is not a UI feature — it is an **architectural constraint**. The formal contract:

1. No recommendation reaches a sales rep without a human approval event on record
2. A rejected recommendation cannot reappear in a new run for the same (retailer, issue_type) while rejection is active
3. Approval state is computed from events, never stored as mutable fields
4. The manager dashboard shows real rejection analytics by category — enabling process improvement over time

---

## Running the System

```bash
# Install dependencies
pip install -e ".[dev]"

# Validate setup
python validate_setup.py

# Launch the application
streamlit run app.py
```

Runs in **demo mode** by default — fully deterministic, no external API calls required. Real execution activates the inference plane and requires an OpenAI API key. The governance layer is identical in both modes.

```bash
# Run the full test suite
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

---

## What This Demonstrates to a Hiring Team

This is not a tutorial project. It is not a quickstart guide. It is not a "build a chatbot in 30 minutes" demonstration.

It demonstrates:

| Skill | Evidence |
|---|---|
| **Systems design under adversarial assumptions** | Every component designed assuming LLM failure, temporal drift, legal scrutiny |
| **Multi-agent orchestration** | Four specialized agents with typed state, controlled handoffs, and retry logic |
| **Event sourcing in practice** | 1,770-line approval system with zero mutations, full audit trail, time-travel capability |
| **LLM governance** | Inference separated from authority by an enforcement layer that cannot be bypassed |
| **Deterministic replay** | Decisions are reproducible independently of when the replay runs |
| **Production code quality** | Black, isort, Ruff, MyPy enforced across 18,000+ lines |
| **Domain modeling** | FMCG business rules encoded as structural invariants, not configurable settings |
| **Test architecture** | Six-phase test suite with async support and fixture-based isolation |
| **Documentation discipline** | Architecture decisions, contracts, and lock documents alongside the code |

The interesting parts are not in the UI. They are in the parts that guarantee the UI can never lie.

---

## Why This Architecture Matters

Most AI applications treat safety as a layer you add at the end. SalesFlow AI treats safety as the foundation everything else is built on.

When a sales manager approves a recommendation, that approval is permanent. When they reject one, that rejection cannot be overwritten. When an auditor asks why a specific retailer was flagged six months ago, the system can replay the exact execution and produce the exact output — not an approximation, not a reconstruction, the exact output.

This is what enterprise AI actually requires. Most projects skip it because it is hard. This one is built around it.

---

*Built by Vahant Sharma. Designed to be discussed, not skimmed.*
