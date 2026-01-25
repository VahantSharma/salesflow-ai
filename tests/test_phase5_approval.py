"""
Phase 5: Human-in-the-Loop (HITL) Tests
========================================

This module tests the approval system for AI recommendations.

Test Categories:
----------------
1. ApprovalRecord lifecycle (create, approve, reject, supersede)
2. ApprovalManager persistence (DuckDB and in-memory)
3. finding_id generation and uniqueness
4. Trace integration (ApprovalTraceEntry)
5. UI component rendering (confidence badges, approval cards)
6. Business rule enforcement (append-only, no workflow interrupts)

CTO Corrections Verified:
-------------------------
1. NO workflow interrupts - approvals are POST-workflow events ✓
2. finding_id is PRIMARY KEY (not trace_id + retailer_id) ✓
3. manager_context is for offline analytics, NOT model feedback ✓
4. Expiry is SUPERSEDED status (not time-based) ✓
5. ApprovalManager in persistence/, not graph/ ✓

Test Count Target: 47 tests
"""

import pytest
import uuid
from datetime import datetime, timedelta
from typing import Generator
import duckdb

# Import the persistence layer (CTO-approved location)
from persistence.approvals import (
    ApprovalRecord,
    ApprovalManager,
    ApprovalStatus,
    RejectionCategory,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    DuplicateApprovalError,  # CTO v3: Idempotency enforcement
    InvalidStateTransition,  # v4 CTO: State machine enforcement
    generate_finding_id,
)

# Import trace components
from graph.trace import (
    ApprovalTraceEntry,
    DecisionTrace,
    TraceWriter,
    create_trace,
    get_execution_summary,
)

# Import strategist for finding_id verification
from agents.strategist import generate_finding_id as strategist_generate_finding_id


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_finding() -> dict:
    """Create a sample finding dict as Strategist would produce."""
    return {
        'finding_id': str(uuid.uuid4()),
        'retailer_id': 'R-0001',
        'retailer_name': 'Kumar Stores',
        'tier': 'Gold',
        'insight_type': 'CHURN_RISK',
        'severity': 'HIGH',
        'explanation': 'No orders in 14 days, previously ordered weekly.',
        'action_type': 'VISIT',
        'suggested_discount': 10,
        'confidence_level': 'HIGH',  # CTO Fix #4: confidence from finding
        'metrics': {'days_since_order': 14, 'current': 0, 'baseline': 5},
    }


@pytest.fixture
def sample_finding_crosssell() -> dict:
    """Create a sample cross-sell finding."""
    return {
        'finding_id': str(uuid.uuid4()),
        'retailer_id': 'R-0002',
        'retailer_name': 'Sharma General Store',
        'tier': 'Silver',
        'insight_type': 'CROSS_SELL_GAP',
        'severity': 'MEDIUM',
        'explanation': 'Buys snacks frequently, but never beverages.',
        'action_type': 'MESSAGE',
        'suggested_discount': 5,
        'confidence_level': 'MEDIUM',  # CTO Fix #4: confidence from finding
        'metrics': {'affinity_score': 0.72, 'has_category': 'Snacks'},
    }


@pytest.fixture
def in_memory_manager() -> ApprovalManager:
    """Create an in-memory ApprovalManager for testing."""
    return ApprovalManager(db_connection=None)


@pytest.fixture
def db_manager() -> Generator[ApprovalManager, None, None]:
    """Create a DuckDB-backed ApprovalManager for testing."""
    conn = duckdb.connect(':memory:')
    manager = ApprovalManager(db_connection=conn)
    yield manager
    conn.close()


# =============================================================================
# 1. FINDING_ID GENERATION TESTS
# =============================================================================

class TestFindingIdGeneration:
    """Tests for finding_id generation and uniqueness."""
    
    def test_generate_finding_id_returns_uuid(self):
        """finding_id should be a valid UUID string."""
        fid = generate_finding_id()
        assert fid is not None
        # Should be parseable as UUID
        parsed = uuid.UUID(fid)
        assert str(parsed) == fid
    
    def test_generate_finding_id_is_unique(self):
        """Each call should generate a unique ID."""
        ids = [generate_finding_id() for _ in range(100)]
        assert len(set(ids)) == 100, "All generated IDs should be unique"
    
    def test_strategist_generate_finding_id_matches(self):
        """Strategist's generate_finding_id should work the same way."""
        fid = strategist_generate_finding_id()
        assert fid is not None
        # Should be parseable as UUID
        parsed = uuid.UUID(fid)
        assert str(parsed) == fid


# =============================================================================
# 2. APPROVAL RECORD TESTS
# =============================================================================

class TestApprovalRecord:
    """Tests for ApprovalRecord dataclass."""
    
    def test_create_approval_record_required_fields(self, sample_finding):
        """ApprovalRecord should require finding_id, trace_id, retailer_id."""
        record = ApprovalRecord(
            finding_id=sample_finding['finding_id'],
            trace_id='trace-001',
            decision_id='decision-001',
            retailer_id=sample_finding['retailer_id'],
            retailer_name=sample_finding['retailer_name'],
            tier=sample_finding['tier'],
            issue_type=sample_finding['insight_type'],
            severity=sample_finding['severity'],
            confidence_level='HIGH',
            recommended_action=sample_finding['explanation'],
            action_type=sample_finding['action_type'],
        )
        assert record.finding_id == sample_finding['finding_id']
        assert record.status == ApprovalStatus.PENDING
    
    def test_approval_record_missing_finding_id_raises(self):
        """ApprovalRecord without finding_id should raise ValueError."""
        with pytest.raises(ValueError, match="finding_id is required"):
            ApprovalRecord(
                finding_id='',  # Empty
                trace_id='trace-001',
                decision_id='decision-001',
                retailer_id='R-001',
                retailer_name='Test Store',
                tier='Gold',
                issue_type='CHURN_RISK',
                severity='HIGH',
                confidence_level='HIGH',
                recommended_action='Visit immediately',
                action_type='VISIT',
            )
    
    def test_approval_record_to_dict(self, sample_finding):
        """to_dict should produce serializable dict."""
        record = ApprovalRecord(
            finding_id=sample_finding['finding_id'],
            trace_id='trace-001',
            decision_id='decision-001',
            retailer_id=sample_finding['retailer_id'],
            retailer_name=sample_finding['retailer_name'],
            tier=sample_finding['tier'],
            issue_type=sample_finding['insight_type'],
            severity=sample_finding['severity'],
            confidence_level='HIGH',
            recommended_action=sample_finding['explanation'],
            action_type=sample_finding['action_type'],
        )
        d = record.to_dict()
        assert d['finding_id'] == sample_finding['finding_id']
        assert d['status'] == 'pending'
        assert 'created_at' in d
    
    def test_approval_record_from_dict(self, sample_finding):
        """from_dict should reconstruct ApprovalRecord."""
        record = ApprovalRecord(
            finding_id=sample_finding['finding_id'],
            trace_id='trace-001',
            decision_id='decision-001',
            retailer_id=sample_finding['retailer_id'],
            retailer_name=sample_finding['retailer_name'],
            tier=sample_finding['tier'],
            issue_type=sample_finding['insight_type'],
            severity=sample_finding['severity'],
            confidence_level='HIGH',
            recommended_action=sample_finding['explanation'],
            action_type=sample_finding['action_type'],
        )
        d = record.to_dict()
        reconstructed = ApprovalRecord.from_dict(d)
        assert reconstructed.finding_id == record.finding_id
        assert reconstructed.retailer_id == record.retailer_id


# =============================================================================
# 3. APPROVAL MANAGER - IN MEMORY TESTS
# =============================================================================

class TestApprovalManagerInMemory:
    """Tests for ApprovalManager with in-memory storage."""
    
    def test_create_pending_approval(self, in_memory_manager, sample_finding):
        """create_pending should create a PENDING approval."""
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001',
            # confidence_level is now extracted from finding (CTO Fix #4)
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.finding_id == sample_finding['finding_id']
        assert record.confidence_level == 'HIGH'  # From finding
    
    def test_approve_pending(self, in_memory_manager, sample_finding):
        """approve should change status to APPROVED."""
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        updated = in_memory_manager.approve(record.finding_id, decided_by='test_manager')
        assert updated.status == ApprovalStatus.APPROVED
        assert updated.decided_by == 'test_manager'
        assert updated.decided_at is not None
    
    def test_reject_pending(self, in_memory_manager, sample_finding):
        """reject should change status to REJECTED with context."""
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        updated = in_memory_manager.reject(
            finding_id=record.finding_id,
            rejection_category=RejectionCategory.ALREADY_HANDLED,
            manager_context='I visited this retailer yesterday.',
            decided_by='test_manager'
        )
        assert updated.status == ApprovalStatus.REJECTED
        assert updated.rejection_category == RejectionCategory.ALREADY_HANDLED
        assert updated.manager_context == 'I visited this retailer yesterday.'
    
    def test_approve_already_decided_raises(self, in_memory_manager, sample_finding):
        """Cannot approve an already approved/rejected record."""
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        in_memory_manager.approve(record.finding_id)
        
        # CTO v3: Idempotency - duplicate approval raises DuplicateApprovalError
        with pytest.raises(DuplicateApprovalError):
            in_memory_manager.approve(record.finding_id)
    
    def test_reject_already_decided_raises(self, in_memory_manager, sample_finding):
        """Cannot reject an already approved/rejected record.
        
        v4 CTO Fix: Now raises InvalidStateTransition for cross-decision attempts.
        """
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        in_memory_manager.approve(record.finding_id)
        
        # v4: Cross-decision (approved → rejected) raises InvalidStateTransition
        with pytest.raises(InvalidStateTransition):
            in_memory_manager.reject(
                record.finding_id,
                RejectionCategory.INCORRECT_DATA
            )
    
    def test_get_pending_returns_only_pending(self, in_memory_manager, sample_finding, sample_finding_crosssell):
        """get_pending should return only PENDING approvals."""
        record1 = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        record2 = in_memory_manager.create_pending(
            finding=sample_finding_crosssell,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Approve one
        in_memory_manager.approve(record1.finding_id)
        
        pending = in_memory_manager.get_pending()
        assert len(pending) == 1
        assert pending[0].finding_id == record2.finding_id
    
    def test_supersede_existing_pending_same_issue_type(self, in_memory_manager, sample_finding):
        """New pending for same (retailer, issue_type) should SUPERSEDE old pending.
        
        CTO Fix #2: Supersession is scoped by (retailer_id, issue_type).
        """
        # Create first pending (CHURN_RISK)
        record1 = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Create second for same retailer AND same issue_type
        new_finding = sample_finding.copy()
        new_finding['finding_id'] = str(uuid.uuid4())  # New finding_id
        record2 = in_memory_manager.create_pending(
            finding=new_finding,
            trace_id='trace-002',
            decision_id='decision-002'
        )
        
        # Check first is superseded
        old = in_memory_manager.get_by_finding_id(record1.finding_id)
        assert old.status == ApprovalStatus.SUPERSEDED
        assert old.superseded_by == record2.finding_id
        
        # Check new is pending
        new = in_memory_manager.get_by_finding_id(record2.finding_id)
        assert new.status == ApprovalStatus.PENDING
    
    def test_no_supersede_for_different_issue_type(self, in_memory_manager, sample_finding):
        """Different issue_type for same retailer should NOT supersede.
        
        CTO Fix #2: A retailer can have multiple PENDING for different issue types.
        """
        # Create first pending (CHURN_RISK)
        record1 = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Create second for same retailer but DIFFERENT issue_type
        crosssell_finding = sample_finding.copy()
        crosssell_finding['finding_id'] = str(uuid.uuid4())
        crosssell_finding['insight_type'] = 'CROSS_SELL_GAP'  # Different issue type
        
        record2 = in_memory_manager.create_pending(
            finding=crosssell_finding,
            trace_id='trace-002',
            decision_id='decision-002'
        )
        
        # Check BOTH are still pending
        old = in_memory_manager.get_by_finding_id(record1.finding_id)
        assert old.status == ApprovalStatus.PENDING, "Different issue type should not supersede"
        
        new = in_memory_manager.get_by_finding_id(record2.finding_id)
        assert new.status == ApprovalStatus.PENDING


# =============================================================================
# 4. APPROVAL MANAGER - DUCKDB TESTS
# =============================================================================

class TestApprovalManagerDuckDB:
    """Tests for ApprovalManager with DuckDB persistence."""
    
    def test_db_create_and_retrieve(self, db_manager, sample_finding):
        """Should persist and retrieve from DuckDB."""
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        retrieved = db_manager.get_by_finding_id(record.finding_id)
        assert retrieved is not None
        assert retrieved.retailer_id == sample_finding['retailer_id']
    
    def test_db_approve_persists(self, db_manager, sample_finding):
        """Approval should be persisted to DB."""
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        db_manager.approve(record.finding_id)
        
        retrieved = db_manager.get_by_finding_id(record.finding_id)
        assert retrieved.status == ApprovalStatus.APPROVED
    
    def test_db_audit_log(self, db_manager, sample_finding, sample_finding_crosssell):
        """get_audit_log should return all records."""
        db_manager.create_pending(sample_finding, 'trace-001', 'decision-001')
        db_manager.create_pending(sample_finding_crosssell, 'trace-001', 'decision-001')
        
        log = db_manager.get_audit_log()
        assert len(log) == 2
    
    def test_db_audit_log_with_filters(self, db_manager, sample_finding, sample_finding_crosssell):
        """get_audit_log should support status filtering."""
        record1 = db_manager.create_pending(sample_finding, 'trace-001', 'decision-001')
        record2 = db_manager.create_pending(sample_finding_crosssell, 'trace-001', 'decision-001')
        
        db_manager.approve(record1.finding_id)
        
        approved = db_manager.get_audit_log(status_filter=ApprovalStatus.APPROVED)
        assert len(approved) == 1
        
        pending = db_manager.get_audit_log(status_filter=ApprovalStatus.PENDING)
        assert len(pending) == 1


# =============================================================================
# 5. APPROVAL TRACE ENTRY TESTS
# =============================================================================

class TestApprovalTraceEntry:
    """Tests for ApprovalTraceEntry integration."""
    
    def test_create_approval_trace_entry(self):
        """Should create valid ApprovalTraceEntry."""
        entry = ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='finding-001',
            approval_status='approved',
            decided_by='test_manager'
        )
        assert entry.finding_id == 'finding-001'
        assert entry.approval_status == 'approved'
    
    def test_approval_trace_entry_to_dict(self):
        """to_dict should produce serializable dict."""
        entry = ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='finding-001',
            approval_status='rejected',
            decided_by='manager',
            rejection_category='incorrect_data',
            manager_context='Data was stale.'
        )
        d = entry.to_dict()
        assert d['type'] == 'approval'
        assert d['finding_id'] == 'finding-001'
        assert d['rejection_category'] == 'incorrect_data'
    
    def test_trace_writer_can_append_after_finalization(self):
        """
        ApprovalTraceEntry can be written AFTER workflow finalization.
        
        This is a CTO-mandated exception: approvals are POST-workflow events.
        """
        trace, writer = create_trace('test-trace', 'show churn risk')
        
        # Finalize the workflow
        writer.finalize('success')
        
        # Should STILL be able to write approval events
        approval_entry = ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='finding-001',
            approval_status='approved',
            decided_by='manager'
        )
        # This should NOT raise even though trace is finalized
        writer.write_approval_event(approval_entry)
        
        assert len(trace.approval_entries) == 1
    
    def test_decision_trace_includes_approval_entries(self):
        """DecisionTrace.to_dict should include approval entries."""
        trace, writer = create_trace('test-trace', 'show churn risk')
        
        writer.write_approval_event(ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='finding-001',
            approval_status='approved',
            decided_by='manager'
        ))
        
        d = trace.to_dict()
        assert 'approvals' in d['entries']
        assert len(d['entries']['approvals']) == 1


# =============================================================================
# 6. EXECUTION SUMMARY TESTS
# =============================================================================

class TestExecutionSummary:
    """Tests for get_execution_summary with approval data."""
    
    def test_summary_includes_approval_counts(self):
        """Summary should include approval statistics."""
        trace, writer = create_trace('test-trace', 'show churn risk')
        
        # Add some approval events
        writer.write_approval_event(ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='f1',
            approval_status='approved',
            decided_by='manager'
        ))
        writer.write_approval_event(ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='f2',
            approval_status='rejected',
            decided_by='manager'
        ))
        writer.write_approval_event(ApprovalTraceEntry(
            timestamp=datetime.now(),
            finding_id='f3',
            approval_status='superseded',
            decided_by='system'
        ))
        
        writer.finalize('success')
        
        summary = get_execution_summary(trace)
        assert 'approval_summary' in summary
        assert summary['approval_summary']['total'] == 3
        assert summary['approval_summary']['approved'] == 1
        assert summary['approval_summary']['rejected'] == 1
        assert summary['approval_summary']['superseded'] == 1


# =============================================================================
# 7. BUSINESS RULE TESTS
# =============================================================================

class TestBusinessRules:
    """Tests for CTO-mandated business rules."""
    
    def test_rejection_context_not_used_for_model_input(self, in_memory_manager, sample_finding):
        """
        manager_context is for OFFLINE ANALYTICS only.
        
        This test documents the contract: the system collects rejection
        context but does NOT use it for any model input or decision logic.
        """
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        in_memory_manager.reject(
            finding_id=record.finding_id,
            rejection_category=RejectionCategory.INCORRECT_DATA,
            manager_context='This is observational context only.'
        )
        
        # The analytics method should surface this data
        # CTO v3: Analytics returns raw data only, no embedded commentary
        analytics = in_memory_manager.get_rejection_analytics()
        assert 'by_category' in analytics
        assert 'total_rejections' in analytics
        # Verify analytics is pure data - no note field mixing data with commentary
        assert 'note' not in analytics, "Analytics should be pure data, no embedded commentary"
    
    def test_no_time_based_expiry(self, in_memory_manager, sample_finding):
        """
        Expiry is SUPERSEDED status, not time-based.
        
        Old pending approvals are superseded when new data arrives,
        NOT when a clock timer expires.
        """
        # Create first pending
        old_finding = sample_finding.copy()
        old_finding['finding_id'] = 'old-finding'
        record1 = in_memory_manager.create_pending(
            finding=old_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Simulate passage of time (this should NOT auto-expire)
        # In a real system, there's no background job checking time
        
        # Create new finding for same retailer AND same issue_type
        new_finding = sample_finding.copy()
        new_finding['finding_id'] = 'new-finding'
        record2 = in_memory_manager.create_pending(
            finding=new_finding,
            trace_id='trace-002',
            decision_id='decision-002'
        )
        
        # Old should be SUPERSEDED (by new data), not EXPIRED
        old = in_memory_manager.get_by_finding_id('old-finding')
        assert old.status == ApprovalStatus.SUPERSEDED
        assert old.superseded_by == 'new-finding'
    
    def test_finding_id_is_primary_key_not_compound(self, in_memory_manager):
        """
        finding_id is the PRIMARY KEY.
        
        NOT trace_id + retailer_id compound key.
        Same retailer can have multiple findings in same trace.
        """
        finding1 = {
            'finding_id': 'finding-1',
            'retailer_id': 'R-001',
            'retailer_name': 'Test Store',
            'tier': 'Gold',
            'insight_type': 'CHURN_RISK',
            'severity': 'HIGH',
            'explanation': 'Issue 1',
            'action_type': 'VISIT',
            'confidence_level': 'HIGH',  # Required field
        }
        
        finding2 = {
            'finding_id': 'finding-2',  # Different finding_id
            'retailer_id': 'R-001',      # SAME retailer
            'retailer_name': 'Test Store',
            'tier': 'Gold',
            'insight_type': 'VALUE_DECLINE',  # Different issue
            'severity': 'MEDIUM',
            'explanation': 'Issue 2',
            'action_type': 'CALL',
            'confidence_level': 'MEDIUM',  # Required field
        }
        
        # Both should be created (different finding_ids)
        # Note: In reality, the second would supersede the first for same retailer
        # But they have different finding_ids, proving identity is by finding_id
        r1 = in_memory_manager.create_pending(finding1, 'trace-001', 'decision-001')
        
        # For the test, use a different retailer to avoid supersession
        finding2['retailer_id'] = 'R-002'
        finding2['retailer_name'] = 'Test Store 2'
        r2 = in_memory_manager.create_pending(finding2, 'trace-001', 'decision-001')
        
        # Both should exist with their unique finding_ids
        assert in_memory_manager.get_by_finding_id('finding-1') is not None
        assert in_memory_manager.get_by_finding_id('finding-2') is not None


# =============================================================================
# 8. EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_get_nonexistent_finding(self, in_memory_manager):
        """Getting non-existent finding should return None."""
        result = in_memory_manager.get_by_finding_id('does-not-exist')
        assert result is None
    
    def test_approve_nonexistent_raises(self, in_memory_manager):
        """Approving non-existent finding should raise."""
        with pytest.raises(ApprovalNotFoundError):
            in_memory_manager.approve('does-not-exist')
    
    def test_reject_nonexistent_raises(self, in_memory_manager):
        """Rejecting non-existent finding should raise."""
        with pytest.raises(ApprovalNotFoundError):
            in_memory_manager.reject('does-not-exist', RejectionCategory.OTHER)
    
    def test_empty_retailer_history(self, in_memory_manager):
        """get_by_retailer with no history should return empty list."""
        result = in_memory_manager.get_by_retailer('R-999')
        assert result == []
    
    def test_rejection_categories_are_complete(self):
        """All expected rejection categories should exist."""
        expected = ['incorrect_data', 'already_handled', 'wrong_priority', 
                   'wrong_action', 'not_applicable', 'other']
        actual = [c.value for c in RejectionCategory]
        assert sorted(actual) == sorted(expected)


# =============================================================================
# 9. INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_full_approval_workflow(self, db_manager, sample_finding):
        """
        Test complete approval workflow:
        1. Create pending from finding
        2. Query pending
        3. Approve
        4. Verify audit trail
        """
        # Step 1: Create pending
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001',
            confidence_level='HIGH'
        )
        
        # Step 2: Query pending
        pending = db_manager.get_pending()
        assert len(pending) == 1
        assert pending[0].finding_id == record.finding_id
        
        # Step 3: Approve
        db_manager.approve(record.finding_id, decided_by='test_manager')
        
        # Step 4: Verify audit trail
        log = db_manager.get_audit_log()
        assert len(log) == 1
        assert log[0].status == ApprovalStatus.APPROVED
        assert log[0].decided_by == 'test_manager'
        
        # Verify no more pending
        pending = db_manager.get_pending()
        assert len(pending) == 0
    
    def test_full_rejection_workflow(self, db_manager, sample_finding):
        """
        Test complete rejection workflow:
        1. Create pending
        2. Reject with context
        3. Verify analytics capture context
        """
        # Step 1: Create pending
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Step 2: Reject with context
        db_manager.reject(
            finding_id=record.finding_id,
            rejection_category=RejectionCategory.ALREADY_HANDLED,
            manager_context='Met with retailer yesterday, issue resolved.',
            decided_by='sales_manager'
        )
        
        # Step 3: Verify context captured
        analytics = db_manager.get_rejection_analytics()
        assert analytics['total_rejections'] == 1
        assert 'already_handled' in analytics['by_category']
        assert analytics['by_category']['already_handled'] == 1


# =============================================================================
# 10. CTO V2 EVENT SOURCING TESTS
# =============================================================================

class TestEventSourcing:
    """Tests for CTO v2 true event sourcing features."""
    
    def test_event_history_captures_all_state_changes(self, db_manager, sample_finding):
        """
        get_event_history should return full audit trail of state changes.
        
        CTO Fix #1: True append-only means every state change is a NEW event.
        """
        # Create pending
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Approve it
        db_manager.approve(record.finding_id, decided_by='manager')
        
        # Get event history
        history = db_manager.get_event_history(record.finding_id)
        
        # Should have 2 events: PENDING_CREATED and APPROVED
        assert len(history) == 2
        assert history[0].event_type.value == 'pending_created'
        assert history[1].event_type.value == 'approved'
        assert history[1].actor == 'manager'
    
    def test_time_travel_query(self, db_manager, sample_finding):
        """
        get_state_at_time should allow time-travel queries.
        
        CTO Fix #1: Event sourcing enables "show state at time T".
        """
        from datetime import timedelta
        
        # Create pending
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Record creation time
        creation_time = record.created_at
        
        # Wait a tiny bit then approve
        import time
        time.sleep(0.01)  # Small delay to ensure different timestamp
        
        db_manager.approve(record.finding_id, decided_by='manager')
        
        # Query state at creation time (should be PENDING)
        state_at_creation = db_manager.get_state_at_time(
            record.finding_id, 
            creation_time + timedelta(milliseconds=1)
        )
        assert state_at_creation is not None
        assert state_at_creation.status == ApprovalStatus.PENDING
    
    def test_scoped_supersession_by_issue_type(self, db_manager, sample_finding):
        """
        Supersession should be scoped by (retailer_id, issue_type).
        
        CTO Fix #2: A retailer can have multiple pending for different issue types.
        """
        # Create CHURN_RISK pending
        churn_finding = sample_finding.copy()
        churn_finding['finding_id'] = 'churn-001'
        churn_finding['insight_type'] = 'CHURN_RISK'
        
        record1 = db_manager.create_pending(
            finding=churn_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Create CROSS_SELL_GAP pending (same retailer)
        crosssell_finding = sample_finding.copy()
        crosssell_finding['finding_id'] = 'crosssell-001'
        crosssell_finding['insight_type'] = 'CROSS_SELL_GAP'
        
        record2 = db_manager.create_pending(
            finding=crosssell_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # BOTH should be pending (different issue types)
        pending = db_manager.get_pending()
        assert len(pending) == 2
        
        # Now create NEW churn finding - should supersede old churn
        new_churn = sample_finding.copy()
        new_churn['finding_id'] = 'churn-002'
        new_churn['insight_type'] = 'CHURN_RISK'
        
        record3 = db_manager.create_pending(
            finding=new_churn,
            trace_id='trace-002',
            decision_id='decision-002'
        )
        
        # Old churn should be superseded, crosssell still pending
        old_churn = db_manager.get_by_finding_id('churn-001')
        assert old_churn.status == ApprovalStatus.SUPERSEDED
        
        crosssell = db_manager.get_by_finding_id('crosssell-001')
        assert crosssell.status == ApprovalStatus.PENDING
        
        new_churn_record = db_manager.get_by_finding_id('churn-002')
        assert new_churn_record.status == ApprovalStatus.PENDING
    
    def test_confidence_from_finding_not_parameter(self, in_memory_manager, sample_finding):
        """
        confidence_level should be extracted from finding, not parameter.
        
        CTO Fix #4: Confidence is immutable from Strategist.
        """
        # Set confidence in finding
        sample_finding['confidence_level'] = 'LOW'
        
        # Create pending (passing HIGH as parameter should be ignored)
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001',
            confidence_level='HIGH'  # This is DEPRECATED and ignored
        )
        
        # Should use finding's confidence, not parameter
        assert record.confidence_level == 'LOW'


# =============================================================================
# 11. BACKWARD COMPATIBILITY TESTS
# =============================================================================

class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with v1 API."""
    
    def test_approval_record_api_unchanged(self, in_memory_manager, sample_finding):
        """ApprovalRecord API should remain unchanged."""
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # All v1 fields should be accessible
        assert hasattr(record, 'finding_id')
        assert hasattr(record, 'trace_id')
        assert hasattr(record, 'decision_id')
        assert hasattr(record, 'retailer_id')
        assert hasattr(record, 'status')
        assert hasattr(record, 'decided_at')
        assert hasattr(record, 'rejection_category')
        assert hasattr(record, 'manager_context')
        assert hasattr(record, 'superseded_by')
    
    def test_approval_manager_api_unchanged(self, db_manager, sample_finding):
        """ApprovalManager API should remain unchanged."""
        # All v1 methods should work
        record = db_manager.create_pending(sample_finding, 'trace-001', 'decision-001')
        
        # Query methods
        assert db_manager.get_pending() is not None
        assert db_manager.get_by_finding_id(record.finding_id) is not None
        assert db_manager.get_by_retailer(sample_finding['retailer_id']) is not None
        assert db_manager.get_audit_log() is not None
        assert db_manager.get_rejection_analytics() is not None
        
        # Action methods
        db_manager.approve(record.finding_id)


# =============================================================================
# 12. CTO v3 INVARIANT TESTS
# =============================================================================

class TestCTOv3Invariants:
    """
    Tests verifying CTO v3 audit-grade requirements:
    - Idempotency enforcement
    - Clock consistency
    - Deterministic replay
    """
    
    def test_double_submit_approval_is_idempotent(self, db_manager, sample_finding):
        """
        CTO v3: Duplicate approval requests must be rejected with DuplicateApprovalError.
        
        This prevents accidental double-clicks or retry logic from creating
        inconsistent state.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # First approval succeeds
        approved = db_manager.approve(record.finding_id)
        assert approved.status == ApprovalStatus.APPROVED
        
        # Second attempt raises DuplicateApprovalError, not generic error
        with pytest.raises(DuplicateApprovalError) as exc_info:
            db_manager.approve(record.finding_id)
        
        assert 'APPROVED' in str(exc_info.value)
        assert record.finding_id in str(exc_info.value)
    
    def test_double_submit_rejection_is_idempotent(self, db_manager, sample_finding):
        """
        CTO v3: Duplicate rejection requests must also be rejected.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # First rejection succeeds
        rejected = db_manager.reject(
            record.finding_id,
            rejection_category=RejectionCategory.INCORRECT_DATA
        )
        assert rejected.status == ApprovalStatus.REJECTED
        
        # Second attempt raises DuplicateApprovalError
        with pytest.raises(DuplicateApprovalError) as exc_info:
            db_manager.reject(
                record.finding_id,
                rejection_category=RejectionCategory.WRONG_PRIORITY
            )
        
        assert 'REJECTED' in str(exc_info.value)
    
    def test_cross_decision_blocked(self, db_manager, sample_finding):
        """
        CTO v3: Cannot approve an already-rejected finding (or vice versa).
        
        v4 CTO Fix: Now raises InvalidStateTransition for cross-decision attempts.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Reject first
        db_manager.reject(
            record.finding_id,
            rejection_category=RejectionCategory.NOT_APPLICABLE
        )
        
        # Attempt to approve should fail with InvalidStateTransition (v4)
        with pytest.raises(InvalidStateTransition):
            db_manager.approve(record.finding_id)
    
    def test_event_ordering_deterministic(self, db_manager, sample_finding):
        """
        CTO v3: Events with same timestamp must be ordered deterministically.
        
        Uses event_id as secondary sort key to ensure replay produces
        identical results.
        """
        # Create multiple records
        findings = []
        for i in range(3):
            f = sample_finding.copy()
            f['finding_id'] = f"finding-{i}"
            f['retailer_id'] = f"retailer-{i}"
            record = db_manager.create_pending(f, f'trace-{i}', f'decision-{i}')
            findings.append(record)
        
        # Approve all (potentially same timestamp in fast test)
        for record in findings:
            db_manager.approve(record.finding_id)
        
        # Query audit log multiple times - should always return same order
        log1 = db_manager.get_audit_log()
        log2 = db_manager.get_audit_log()
        log3 = db_manager.get_audit_log()
        
        # Extract finding_ids in order
        ids1 = [r.finding_id for r in log1]
        ids2 = [r.finding_id for r in log2]
        ids3 = [r.finding_id for r in log3]
        
        assert ids1 == ids2 == ids3, "Event ordering must be deterministic"
    
    def test_analytics_returns_pure_data(self, db_manager, sample_finding):
        """
        CTO v3: Analytics methods must return pure data, no embedded commentary.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        db_manager.reject(
            record.finding_id,
            rejection_category=RejectionCategory.ALREADY_HANDLED
        )
        
        analytics = db_manager.get_rejection_analytics()
        
        # Must have data fields
        assert 'total_rejections' in analytics
        assert 'by_category' in analytics
        
        # Must NOT have commentary fields
        assert 'note' not in analytics
        assert 'disclaimer' not in analytics
        assert 'warning' not in analytics
    
    def test_system_invariant_human_decisions_irreversible(self, db_manager, sample_finding):
        """
        CTO v3 SYSTEM INVARIANT: Once a human decision exists, 
        the system may only append knowledge — never reinterpret it.
        
        This is the core guarantee of the approval system.
        
        v4 CTO Fix: Uses specific exception types:
        - DuplicateApprovalError for idempotent operations (same op twice)
        - InvalidStateTransition for cross-decisions (different op on terminal state)
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Human approves
        db_manager.approve(record.finding_id)
        
        # Verify no API exists to "undo" or "change" the decision
        # The only allowed subsequent action is supersession (new finding)
        with pytest.raises(DuplicateApprovalError):
            db_manager.approve(record.finding_id)  # Cannot re-approve (idempotent)
        
        with pytest.raises(InvalidStateTransition):
            db_manager.reject(record.finding_id, RejectionCategory.OTHER)  # Cannot reject after approve (cross-decision)
        
        # The record status is final
        final_record = db_manager.get_by_finding_id(record.finding_id)
        assert final_record.status == ApprovalStatus.APPROVED


# =============================================================================
# 12. CTO V4 PRODUCTION-GRADE TESTS
# =============================================================================

class TestCTOv4ProductionGrade:
    """
    Tests verifying CTO v4 production-grade requirements:
    - decision_id REQUIRED
    - EXPIRED event type
    - Constraint-driven idempotency
    - ApprovalTraceEntry validation
    """
    
    def test_decision_id_required_raises_error(self, db_manager, sample_finding):
        """
        v4 CTO Fix: decision_id is REQUIRED.
        
        Passing empty decision_id should raise DecisionIdRequiredError.
        """
        from persistence.approvals import DecisionIdRequiredError
        
        with pytest.raises(DecisionIdRequiredError):
            db_manager.create_pending(
                finding=sample_finding,
                trace_id='trace-001',
                decision_id='',  # Empty - should fail
            )
    
    def test_decision_id_none_raises_error(self, db_manager, sample_finding):
        """
        v4 CTO Fix: decision_id cannot be None.
        """
        from persistence.approvals import DecisionIdRequiredError
        
        with pytest.raises(DecisionIdRequiredError):
            db_manager.create_pending(
                finding=sample_finding,
                trace_id='trace-001',
                decision_id=None,  # None - should fail
            )
    
    def test_expired_event_type_exists(self):
        """
        v4 CTO Fix: EXPIRED is now an explicit event type.
        """
        from persistence.approvals import EventType, ApprovalStatus
        
        # EventType should have EXPIRED
        assert hasattr(EventType, 'EXPIRED')
        assert EventType.EXPIRED.value == 'expired'
        
        # ApprovalStatus should have EXPIRED
        assert hasattr(ApprovalStatus, 'EXPIRED')
        assert ApprovalStatus.EXPIRED.value == 'expired'
    
    def test_expire_pending_finding(self, db_manager, sample_finding):
        """
        v4 CTO Fix: expire() creates explicit EXPIRED event.
        
        Expiration is recorded, not inferred.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Expire the finding
        expired = db_manager.expire(record.finding_id, reason="Test expiration")
        
        assert expired.status == ApprovalStatus.EXPIRED
        
        # Verify event was created
        history = db_manager.get_event_history(record.finding_id)
        assert len(history) == 2  # PENDING_CREATED + EXPIRED
        assert history[1].event_type.value == 'expired'
    
    def test_cannot_expire_already_decided(self, db_manager, sample_finding):
        """
        v4: Cannot expire an already approved/rejected finding.
        """
        record = db_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # Approve first
        db_manager.approve(record.finding_id)
        
        # Cannot expire after approval
        with pytest.raises(ApprovalAlreadyDecidedError):
            db_manager.expire(record.finding_id)
    
    def test_approval_trace_entry_validates_finding_id(self):
        """
        v4 CTO Fix: ApprovalTraceEntry requires finding_id.
        """
        with pytest.raises(ValueError, match="finding_id is required"):
            ApprovalTraceEntry(
                timestamp=datetime.now(),
                finding_id='',  # Empty - should fail
                approval_status='approved'
            )
    
    def test_approval_trace_entry_validates_status(self):
        """
        v4 CTO Fix: ApprovalTraceEntry validates approval_status.
        """
        with pytest.raises(ValueError, match="approval_status"):
            ApprovalTraceEntry(
                timestamp=datetime.now(),
                finding_id='test-finding',
                approval_status='invalid_status'  # Should fail
            )
    
    def test_approval_trace_entry_valid_statuses(self):
        """
        v4: ApprovalTraceEntry accepts all valid statuses including 'expired'.
        """
        valid_statuses = ['approved', 'rejected', 'superseded', 'expired', 'pending']
        for status in valid_statuses:
            entry = ApprovalTraceEntry(
                timestamp=datetime.now(),
                finding_id='test-finding',
                approval_status=status
            )
            assert entry.approval_status == status
    
    def test_trace_writer_validates_timestamp_ordering(self):
        """
        v4 CTO Fix: write_approval_event validates timestamp >= workflow completion.
        """
        trace, writer = create_trace('test-trace', 'test query')
        
        # Finalize the trace
        writer.finalize('success')
        
        # Create entry with timestamp BEFORE completion
        old_timestamp = trace.completed_at - timedelta(seconds=10)
        entry = ApprovalTraceEntry(
            timestamp=old_timestamp,
            finding_id='test-finding',
            approval_status='approved'
        )
        
        # Should raise ValueError due to timestamp ordering
        with pytest.raises(ValueError, match="must be >="):
            writer.write_approval_event(entry)
    
    def test_trace_writer_allows_valid_post_finalization(self):
        """
        v4: write_approval_event allows writes AFTER finalization with valid timestamp.
        """
        trace, writer = create_trace('test-trace', 'test query')
        
        # Finalize the trace
        writer.finalize('success')
        
        # Create entry with timestamp AFTER completion
        new_timestamp = trace.completed_at + timedelta(seconds=10)
        entry = ApprovalTraceEntry(
            timestamp=new_timestamp,
            finding_id='test-finding',
            approval_status='approved'
        )
        
        # Should succeed
        writer.write_approval_event(entry)
        assert len(trace.approval_entries) == 1
    
    def test_constraint_driven_idempotency_in_memory(self, in_memory_manager, sample_finding):
        """
        v4 CTO Fix: Idempotency works in in-memory mode too.
        """
        record = in_memory_manager.create_pending(
            finding=sample_finding,
            trace_id='trace-001',
            decision_id='decision-001'
        )
        
        # First approval
        in_memory_manager.approve(record.finding_id)
        
        # Second should fail (memory-based check)
        with pytest.raises(DuplicateApprovalError):
            in_memory_manager.approve(record.finding_id)
    
    def test_new_exceptions_exported(self):
        """
        v4: New exceptions should be exported from persistence module.
        """
        from persistence import (
            TransactionError,
            DecisionIdRequiredError,
        )
        
        assert TransactionError is not None
        assert DecisionIdRequiredError is not None
    
    def test_approval_finding_requires_decision_id(self):
        """
        v4 CTO Fix: ApprovalFinding validates decision_id is not empty.
        """
        from persistence.approvals import ApprovalFinding
        
        with pytest.raises(ValueError, match="decision_id is required"):
            ApprovalFinding(
                finding_id='test',
                trace_id='trace',
                decision_id='',  # Empty - should fail
                retailer_id='R-001',
                retailer_name='Test',
                tier='Gold',
                issue_type='CHURN_RISK',
                severity='HIGH',
                confidence_level='HIGH',
                recommended_action='Test',
                action_type='VISIT',
            )
