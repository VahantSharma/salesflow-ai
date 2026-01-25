"""
SalesFlow AI Services Layer
============================

This module provides service-layer abstractions for UI consumption.
Services are THIN ADAPTERS - they do NOT contain business logic.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CTO MANDATE: Services are THIN ADAPTERS                                     ║
║                                                                              ║
║  Services:                                                                   ║
║  - Translate between UI contracts and domain objects                         ║
║  - Handle connection management                                              ║
║  - Provide simplified APIs for UI consumption                                ║
║                                                                              ║
║  Services do NOT:                                                            ║
║  - Construct domain objects (Manager's job)                                  ║
║  - Contain business logic (Agents' job)                                      ║
║  - Make decisions (Strategist's job)                                         ║
║  - Compute summaries (Backend's job)                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from services.approval_service import ApprovalService

__all__ = ['ApprovalService']
