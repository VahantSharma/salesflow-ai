"""
Persistence Layer

Responsibility:
- Manage durable state that survives restarts
- Handle approval records and audit trails
- Provide clean interfaces for UI/workflow

This layer is SEPARATE from graph/ because:
- Graph is pure computation (ephemeral)
- Persistence is durable state (survives restarts)
- Mixing them creates coupling and testing complexity

╔══════════════════════════════════════════════════════════════════════════════╗
║                   SYSTEM INVARIANT (NON-NEGOTIABLE)                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ONCE A HUMAN DECISION EXISTS, THE SYSTEM MAY ONLY APPEND KNOWLEDGE —        ║
║  NEVER REINTERPRET IT.                                                       ║
║                                                                              ║
║  Human approval decisions are IRREVERSIBLE.                                  ║
║  System state may be reconstructed from events but NEVER MUTATED.            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  v4 PRODUCTION-GRADE ARCHITECTURE                                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  AUTHORITATIVE:                                                              ║
║  • approval_findings - Immutable finding snapshots (INSERT only)             ║
║  • approval_events   - Append-only event stream (INSERT only)                ║
║                                                                              ║
║  PROJECTION:                                                                 ║
║  • Current state computed from events (not stored mutably)                   ║
║                                                                              ║
║  KEY GUARANTEES:                                                             ║
║  • Constraint-driven idempotency (DB is source of truth)                     ║
║  • Transactional writes (all-or-nothing)                                     ║
║  • decision_id REQUIRED and IMMUTABLE                                        ║
║  • EXPIRED is explicit event (not inferred)                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Components:
- approvals.py: Human-in-the-loop approval lifecycle (event-sourced, v4)
"""

from persistence.approvals import (
    # Core data classes
    ApprovalRecord,
    ApprovalFinding,
    ApprovalEvent,
    
    # Manager
    ApprovalManager,
    
    # Enums
    RejectionCategory,
    ApprovalStatus,
    EventType,
    
    # Exceptions
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    InvalidTraceError,
    InvalidApprovalState,
    InvalidApprovalPayload,
    DuplicateApprovalError,
    TransactionError,
    DecisionIdRequiredError,
    
    # Utilities
    generate_finding_id,
)

__all__ = [
    # Core data classes
    'ApprovalRecord',
    'ApprovalFinding',
    'ApprovalEvent',
    
    # Manager
    'ApprovalManager',
    
    # Enums  
    'RejectionCategory',
    'ApprovalStatus',
    'EventType',
    
    # Exceptions
    'ApprovalAlreadyDecidedError',
    'ApprovalNotFoundError',
    'InvalidTraceError',
    'InvalidApprovalState',
    'InvalidApprovalPayload',
    'DuplicateApprovalError',
    'TransactionError',
    'DecisionIdRequiredError',
    
    # Utilities
    'generate_finding_id',
]
