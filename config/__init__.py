"""
Config Package

This package contains all configuration-related modules for SalesFlow AI.

Modules:
- settings: Centralized application configuration (Pydantic-based)
- prompts: All LLM prompts for agents

Usage:
    from config.settings import settings  # Singleton instance
    from config.settings import Settings  # Class (for testing)
    from config.prompts import ANALYST_SYSTEM_PROMPT
"""

from config.settings import Settings, settings

__all__ = ["Settings", "settings"]
