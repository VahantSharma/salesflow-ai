"""
Approval Service - Thin Adapter for UI Integration
===================================================

This service provides a clean API for UI to interact with ApprovalManager.
It is a THIN ADAPTER - it does NOT construct domain objects or contain business logic.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CTO CORRECTION #1: Service is THIN ADAPTER                                  ║
║                                                                              ║
║  ApprovalService:                                                            ║
║  - Accepts dict (NOT ApprovalFinding)                                        ║
║  - Passes dict directly to ApprovalManager                                   ║
║  - ApprovalManager constructs ApprovalFinding internally                     ║
║                                                                              ║
║  This prevents:                                                              ║
║  - Domain object construction outside Manager                                ║
║  - UI having knowledge of domain internals                                   ║
║  - Inconsistent validation paths                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  CTO CORRECTION #3: Backend is AUTHORITATIVE                                 ║
║                                                                              ║
║  Session state is COSMETIC:                                                  ║
║  - UI may cache for responsiveness                                           ║
║  - Backend is ALWAYS the source of truth                                     ║
║  - get_pending() ALWAYS queries ApprovalManager                              ║
║  - approve()/reject() ALWAYS write to ApprovalManager                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    from services.approval_service import ApprovalService
    
    service = ApprovalService()
    
    # Submit finding for approval (finding is a dict, NOT ApprovalFinding)
    finding_id = service.submit_for_approval(finding_dict, trace_id, decision_id)
    
    # Get pending approvals
    pending = service.get_pending()
    
    # Approve/Reject
    service.approve(finding_id, manager_id="manager")
    service.reject(finding_id, manager_id="manager", category="WRONG_PRIORITY")
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from persistence.approvals import (
    ApprovalManager,
    ApprovalRecord,
    ApprovalStatus,
    RejectionCategory,
)


@dataclass
class ApprovalDTO:
    """
    Data Transfer Object for UI consumption.
    
    This is the ONLY approval structure UI should use.
    It mirrors ApprovalRecord but is explicitly for UI.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  UI Contract: All fields here are safe for direct rendering.             ║
    ║  No business logic, no computed values, just data.                       ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    finding_id: str
    trace_id: str
    decision_id: str
    retailer_id: str
    retailer_name: str
    tier: str
    issue_type: str
    severity: str
    confidence_level: str
    recommended_action: str
    action_type: str
    suggested_discount: Optional[int]
    deadline_description: str
    status: str  # 'pending' | 'approved' | 'rejected' | 'superseded' | 'expired'
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    rejection_category: Optional[str] = None
    manager_context: Optional[str] = None
    
    @classmethod
    def from_record(cls, record: ApprovalRecord) -> 'ApprovalDTO':
        """Convert ApprovalRecord to DTO."""
        return cls(
            finding_id=record.finding_id,
            trace_id=record.trace_id,
            decision_id=record.decision_id,
            retailer_id=record.retailer_id,
            retailer_name=record.retailer_name,
            tier=record.tier,
            issue_type=record.issue_type,
            severity=record.severity,
            confidence_level=record.confidence_level,
            recommended_action=record.recommended_action,
            action_type=record.action_type,
            suggested_discount=record.suggested_discount,
            deadline_description=record.deadline_description,
            status=record.status.value if isinstance(record.status, ApprovalStatus) else str(record.status),
            created_at=record.created_at,
            decided_at=record.decided_at,
            decided_by=record.decided_by,
            rejection_category=record.rejection_category.value if record.rejection_category else None,
            manager_context=record.manager_context,
        )
    
    def to_dict(self) -> dict:
        """Convert to dict for UI consumption."""
        return {
            'finding_id': self.finding_id,
            'trace_id': self.trace_id,
            'decision_id': self.decision_id,
            'retailer_id': self.retailer_id,
            'retailer_name': self.retailer_name,
            'tier': self.tier,
            'issue_type': self.issue_type,
            'severity': self.severity,
            'confidence_level': self.confidence_level,
            'recommended_action': self.recommended_action,
            'action_type': self.action_type,
            'suggested_discount': self.suggested_discount,
            'deadline_description': self.deadline_description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None,
            'decided_by': self.decided_by,
            'rejection_category': self.rejection_category,
            'manager_context': self.manager_context,
        }


class ApprovalService:
    """
    Thin adapter between UI and ApprovalManager.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  THIS SERVICE IS INTENTIONALLY THIN                                       ║
    ║                                                                          ║
    ║  Every method is a simple delegation to ApprovalManager.                 ║
    ║  If you find yourself adding logic here, STOP and reconsider.            ║
    ║  Logic belongs in ApprovalManager or Strategist.                         ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    
    def __init__(self, db_connection: Any = None):
        """
        Initialize service with optional database connection.
        
        Args:
            db_connection: DuckDB connection (optional, uses default if None)
        """
        self._manager = ApprovalManager(db_connection)
    
    # =========================================================================
    # SUBMISSION (Strategist → ApprovalManager)
    # =========================================================================
    
    def submit_for_approval(
        self,
        finding: dict,
        trace_id: str,
        decision_id: str
    ) -> str:
        """
        Submit a finding for human approval.
        
        ╔══════════════════════════════════════════════════════════════════════╗
        ║  CTO CORRECTION #1: This accepts dict, NOT ApprovalFinding           ║
        ║                                                                      ║
        ║  ApprovalFinding is constructed INSIDE ApprovalManager.create_pending()║
        ║  We NEVER construct domain objects in the service layer.             ║
        ╚══════════════════════════════════════════════════════════════════════╝
        
        Args:
            finding: Dict with finding data (from Strategist)
            trace_id: Trace ID for audit correlation
            decision_id: Decision ID for workflow correlation
            
        Returns:
            finding_id: The ID of the created approval
        """
        # THIN ADAPTER: Just delegate to manager
        # Manager handles: validation, ApprovalFinding construction, event creation
        return self._manager.create_pending(
            finding=finding,
            trace_id=trace_id,
            decision_id=decision_id
        )
    
    # =========================================================================
    # DECISIONS (Manager UI → ApprovalManager)
    # =========================================================================
    
    def approve(
        self,
        finding_id: str,
        manager_id: str = "manager"
    ) -> ApprovalDTO:
        """
        Approve a pending finding.
        
        Args:
            finding_id: The finding to approve
            manager_id: Who is approving (for audit)
            
        Returns:
            Updated approval as DTO
        """
        record = self._manager.approve(finding_id, manager_id)
        return ApprovalDTO.from_record(record)
    
    def reject(
        self,
        finding_id: str,
        manager_id: str = "manager",
        category: str = "OTHER",
        context: Optional[str] = None
    ) -> ApprovalDTO:
        """
        Reject a pending finding.
        
        Args:
            finding_id: The finding to reject
            manager_id: Who is rejecting (for audit)
            category: Rejection category (maps to RejectionCategory)
            context: Optional free-form context
            
        Returns:
            Updated approval as DTO
        """
        # Map string to enum
        try:
            rejection_cat = RejectionCategory(category.lower())
        except ValueError:
            rejection_cat = RejectionCategory.OTHER
        
        record = self._manager.reject(
            finding_id=finding_id,
            manager_id=manager_id,
            rejection_category=rejection_cat,
            manager_context=context
        )
        return ApprovalDTO.from_record(record)
    
    # =========================================================================
    # QUERIES (UI reads)
    # =========================================================================
    
    def get_pending(self) -> List[ApprovalDTO]:
        """
        Get all pending approvals.
        
        ╔══════════════════════════════════════════════════════════════════════╗
        ║  CTO CORRECTION #3: This is the ONLY source of truth for pending     ║
        ║                                                                      ║
        ║  UI MUST call this method to get current pending list.               ║
        ║  UI MUST NOT rely on session state for approval status.              ║
        ╚══════════════════════════════════════════════════════════════════════╝
        
        Returns:
            List of pending approvals as DTOs
        """
        records = self._manager.get_pending()
        return [ApprovalDTO.from_record(r) for r in records]
    
    def get_by_finding_id(self, finding_id: str) -> Optional[ApprovalDTO]:
        """
        Get a specific approval by finding_id.
        
        Args:
            finding_id: The finding ID to look up
            
        Returns:
            Approval DTO if found, None otherwise
        """
        record = self._manager.get_by_finding_id(finding_id)
        if record:
            return ApprovalDTO.from_record(record)
        return None
    
    def get_by_retailer(self, retailer_id: str) -> List[ApprovalDTO]:
        """
        Get all approvals for a retailer.
        
        Args:
            retailer_id: The retailer ID
            
        Returns:
            List of approvals as DTOs
        """
        records = self._manager.get_by_retailer(retailer_id)
        return [ApprovalDTO.from_record(r) for r in records]
    
    def get_by_decision_id(self, decision_id: str) -> List[ApprovalDTO]:
        """
        Get all approvals from a single workflow run.
        
        Phase 6: Enables "show all findings from this decision" queries.
        
        v4 CTO Fix: Query ALL statuses, not just pending.
        This supports the use case of reviewing all findings from a past run,
        regardless of their current status (approved, rejected, superseded, etc.).
        
        Args:
            decision_id: The decision ID from workflow
            
        Returns:
            List of approvals as DTOs (ALL statuses, not just pending)
        """
        # v4 CTO Fix: Use audit log to get ALL records, then filter by decision_id
        # This ensures we include approved, rejected, superseded, expired - not just pending
        all_records = self._manager.get_audit_log()  # Gets all records regardless of status
        return [
            ApprovalDTO.from_record(r) 
            for r in all_records 
            if r.decision_id == decision_id
        ]
    
    # =========================================================================
    # ANALYTICS (Read-only, for dashboard)
    # =========================================================================
    
    def get_rejection_analytics(self) -> Dict[str, Any]:
        """
        Get rejection analytics for operational review.
        
        ╔══════════════════════════════════════════════════════════════════════╗
        ║  CTO CORRECTION #4: This data is ANALYTICS-ONLY                      ║
        ║                                                                      ║
        ║  This data is for HUMAN analysis of rejection patterns.              ║
        ║  It is NOT used to modify AI decision-making behavior.               ║
        ║                                                                      ║
        ║  LABEL ALL CONSUMERS of this data as analytics-only.                 ║
        ╚══════════════════════════════════════════════════════════════════════╝
        
        Returns:
            Dict with rejection statistics (analytics-only)
        """
        return self._manager.get_rejection_analytics()
    
    def get_audit_log(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status_filter: Optional[str] = None
    ) -> List[ApprovalDTO]:
        """
        Get audit log of approvals.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            status_filter: Optional status filter ('pending', 'approved', etc.)
            
        Returns:
            List of approvals as DTOs
        """
        status_enum = None
        if status_filter:
            try:
                status_enum = ApprovalStatus(status_filter.lower())
            except ValueError:
                pass
        
        records = self._manager.get_audit_log(
            start_date=start_date,
            end_date=end_date,
            status_filter=status_enum
        )
        return [ApprovalDTO.from_record(r) for r in records]
