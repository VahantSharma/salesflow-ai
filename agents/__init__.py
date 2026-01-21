"""
Agents Package

This package contains all AI agents for SalesFlow AI.

Agents:
- analyst: Natural language to SQL translation (data retrieval)
- strategist: Data analysis and recommendation generation
- copywriter: Sales message crafting with human touches
- guardrails: Topic validation and safety checks

Design Philosophy:
- Each agent has ONE clear responsibility (SRP)
- Agents communicate through structured state, not free-form text
- All agents use the same LLM model but different prompts
- Guardrails wrap every external input

Agent Communication Flow:
    User Query → Guardrails → Analyst → Strategist → Copywriter → Output

Usage:
    from agents.analyst import AnalystAgent
    from agents.strategist import StrategistAgent
    from agents.copywriter import CopywriterAgent
    from agents.guardrails import GuardrailsAgent
"""

__all__ = ["analyst", "strategist", "copywriter", "guardrails"]
