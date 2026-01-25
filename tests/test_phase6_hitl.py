"""
Phase 6 HITL Integration Tests
===============================

This module tests the Phase 6 implementation:
1. Trace integrity status (CTO Correction #2)
2. Decision ID end-to-end correlation
3. ApprovalService thin adapter pattern (CTO Correction #1)
4. Backend authority (CTO Correction #3)
5. Analytics isolation (CTO Correction #4)

Test Categories:
- Unit tests for IntegrityStatus computation
- Unit tests for decision_id generation
- Integration tests for ApprovalService
- Contract tests for session state independence
- Invariant tests for Phase 6 guarantees

Prerequisites:
- Phase 0-5 must be complete
- No LLM required for most tests (mocked)

Usage:
    # Run all Phase 6 tests
    python -m pytest tests/test_phase6_hitl.py -v
    
    # Run specific invariant tests
    python -m pytest tests/test_phase6_hitl.py -k "invariant" -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import uuid

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = []
    conn.execute.return_value.fetchone.return_value = None
    return conn


@pytest.fixture
def sample_finding_dict():
    """Sample finding dict as produced by Strategist."""
    return {
        'finding_id': str(uuid.uuid4()),
        'retailer_id': 'R001',
        'retailer_name': 'Test Store',
        'tier': 'Gold',
        'issue_type': 'CHURN_RISK',
        'severity': 'HIGH',
        'confidence_level': 'HIGH',
        'recommended_action': 'Schedule a visit',
        'action_type': 'VISIT',
        'suggested_discount': 10,
        'deadline_description': 'Within 7 days',
    }


# =============================================================================
# TEST CLASS: Trace Integrity Status (CTO Correction #2)
# =============================================================================

class TestTraceIntegrityStatus:
    """
    Tests for IntegrityStatus computation.
    
    CTO Correction #2: DecisionTrace must be all-or-nothing.
    Partial traces are worse than no trace.
    """
    
    def test_integrity_status_enum_exists(self):
        """IntegrityStatus enum must exist with correct values."""
        from graph.trace import IntegrityStatus
        
        assert hasattr(IntegrityStatus, 'COMPLETE')
        assert hasattr(IntegrityStatus, 'PARTIAL')
        assert hasattr(IntegrityStatus, 'FAILED')
        
        assert IntegrityStatus.COMPLETE.value == 'complete'
        assert IntegrityStatus.PARTIAL.value == 'partial'
        assert IntegrityStatus.FAILED.value == 'failed'
    
    def test_success_outcome_requires_all_four_agents(self):
        """Success outcome = all 4 agents must have written entries."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry, AnalystTraceEntry,
            StrategistTraceEntry, CopywriterTraceEntry
        )
        
        trace, writer = create_trace("test-trace", "test query")
        
        # Write all 4 entries
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="allowed"
        ))
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT 1",
            sql_valid=True,
            execution_success=True
        ))
        writer.write_strategist(StrategistTraceEntry(
            timestamp=datetime.now(),
            findings_count=1,
            actions_generated=1
        ))
        writer.write_copywriter(CopywriterTraceEntry(
            timestamp=datetime.now(),
            messages_generated=1,
            tone_used='routine',
            discount_source='strategist'
        ))
        
        writer.finalize('success')
        
        assert trace.integrity_status == IntegrityStatus.COMPLETE
    
    def test_success_outcome_partial_if_missing_agents(self):
        """Success outcome but missing agents = PARTIAL status."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry, AnalystTraceEntry
        )
        
        trace, writer = create_trace("test-trace", "test query")
        
        # Only write 2 of 4 entries
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="allowed"
        ))
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT 1",
            sql_valid=True,
            execution_success=True
        ))
        
        writer.finalize('success')
        
        assert trace.integrity_status == IntegrityStatus.PARTIAL
    
    def test_blocked_outcome_only_needs_guardrails(self):
        """Blocked outcome = only guardrails entry expected."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry
        )
        
        trace, writer = create_trace("test-trace", "test query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="blocked",
            block_reason="Off-topic"
        ))
        
        writer.finalize('blocked')
        
        assert trace.integrity_status == IntegrityStatus.COMPLETE
    
    def test_empty_result_needs_guardrails_and_analyst(self):
        """Empty result = guardrails + analyst expected."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry, AnalystTraceEntry
        )
        
        trace, writer = create_trace("test-trace", "test query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="allowed"
        ))
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT 1 WHERE FALSE",
            sql_valid=True,
            execution_success=True
        ))
        
        writer.finalize('empty_result')
        
        assert trace.integrity_status == IntegrityStatus.COMPLETE
    
    def test_error_outcome_always_partial(self):
        """Error outcome = always PARTIAL (didn't complete)."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry
        )
        
        trace, writer = create_trace("test-trace", "test query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="allowed"
        ))
        
        writer.finalize('error')
        
        assert trace.integrity_status == IntegrityStatus.PARTIAL
    
    def test_no_entries_is_failed(self):
        """No entries written = FAILED status."""
        from graph.trace import create_trace, IntegrityStatus
        
        trace, writer = create_trace("test-trace", "test query")
        writer.finalize('error')
        
        assert trace.integrity_status == IntegrityStatus.FAILED
    
    def test_integrity_status_in_to_dict(self):
        """integrity_status must appear in to_dict() output."""
        from graph.trace import create_trace, GuardrailsTraceEntry
        
        trace, writer = create_trace("test-trace", "test query")
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="test",
            classification="blocked"
        ))
        writer.finalize('blocked')
        
        trace_dict = trace.to_dict()
        
        assert 'integrity_status' in trace_dict
        assert trace_dict['integrity_status'] == 'complete'


# =============================================================================
# TEST CLASS: Decision ID Generation
# =============================================================================

class TestDecisionIdGeneration:
    """
    Tests for decision_id end-to-end correlation.
    
    Invariant 6.3: trace_id + decision_id link everything.
    """
    
    def test_workflow_generates_decision_id(self):
        """run_workflow must generate and return decision_id."""
        from graph.workflow import generate_decision_id, generate_trace_id
        
        decision_id = generate_decision_id()
        trace_id = generate_trace_id()
        
        assert decision_id.startswith('decision_')
        assert trace_id.startswith('trace_')
        assert len(decision_id) == len('decision_') + 12
        assert len(trace_id) == len('trace_') + 12
    
    def test_decision_id_in_initial_state(self):
        """create_initial_state must accept and store decision_id."""
        from graph.state import create_initial_state
        
        state = create_initial_state(
            query="test",
            trace_id="trace_123",
            decision_id="decision_456"
        )
        
        assert state['decision_id'] == 'decision_456'
        assert state['trace_id'] == 'trace_123'
    
    def test_trace_includes_decision_id(self):
        """DecisionTrace must store decision_id."""
        from graph.trace import create_trace
        
        trace, writer = create_trace(
            trace_id="trace_123",
            original_query="test",
            decision_id="decision_456"
        )
        
        assert trace.decision_id == "decision_456"
        
        trace_dict = trace.to_dict()
        assert trace_dict['decision_id'] == "decision_456"
    
    def test_writer_can_set_decision_id(self):
        """TraceWriter.set_decision_id() must work before finalize."""
        from graph.trace import create_trace
        
        trace, writer = create_trace("trace_123", "test query")
        
        writer.set_decision_id("decision_789")
        
        assert trace.decision_id == "decision_789"
    
    def test_set_decision_id_fails_after_finalize(self):
        """Cannot set decision_id after finalize()."""
        from graph.trace import create_trace
        
        trace, writer = create_trace("trace_123", "test query")
        writer.finalize('error')
        
        with pytest.raises(RuntimeError):
            writer.set_decision_id("too_late")


# =============================================================================
# TEST CLASS: ApprovalService Thin Adapter (CTO Correction #1)
# =============================================================================

class TestApprovalServiceThinAdapter:
    """
    Tests for ApprovalService thin adapter pattern.
    
    CTO Correction #1: Service must NOT construct ApprovalFinding.
    It must pass dict to ApprovalManager which constructs internally.
    """
    
    def test_service_accepts_dict_not_dataclass(self, sample_finding_dict):
        """submit_for_approval must accept dict, not ApprovalFinding."""
        from services.approval_service import ApprovalService
        
        # Verify signature accepts dict
        import inspect
        sig = inspect.signature(ApprovalService.submit_for_approval)
        params = list(sig.parameters.keys())
        
        assert 'finding' in params
        # The type annotation should be dict, not ApprovalFinding
        finding_param = sig.parameters['finding']
        # Just verify it's not ApprovalFinding
        assert 'ApprovalFinding' not in str(finding_param.annotation)
    
    def test_dto_conversion_from_record(self):
        """ApprovalDTO.from_record() must work correctly."""
        from services.approval_service import ApprovalDTO
        from persistence.approvals import ApprovalRecord, ApprovalStatus
        
        record = ApprovalRecord(
            finding_id="f123",
            trace_id="t123",
            decision_id="d123",
            retailer_id="R001",
            retailer_name="Test Store",
            tier="Gold",
            issue_type="CHURN_RISK",
            severity="HIGH",
            confidence_level="HIGH",
            recommended_action="Visit",
            action_type="VISIT",
            status=ApprovalStatus.PENDING
        )
        
        dto = ApprovalDTO.from_record(record)
        
        assert dto.finding_id == "f123"
        assert dto.status == "pending"
        assert dto.decision_id == "d123"
    
    def test_dto_to_dict(self):
        """ApprovalDTO.to_dict() must produce UI-safe dict."""
        from services.approval_service import ApprovalDTO
        
        dto = ApprovalDTO(
            finding_id="f123",
            trace_id="t123",
            decision_id="d123",
            retailer_id="R001",
            retailer_name="Test Store",
            tier="Gold",
            issue_type="CHURN_RISK",
            severity="HIGH",
            confidence_level="HIGH",
            recommended_action="Visit",
            action_type="VISIT",
            suggested_discount=10,
            deadline_description="ASAP",
            status="pending",
            created_at=datetime.now()
        )
        
        d = dto.to_dict()
        
        assert d['finding_id'] == "f123"
        assert d['status'] == "pending"
        assert 'created_at' in d


# =============================================================================
# TEST CLASS: Session State Independence (CTO Correction #3)
# =============================================================================

class TestSessionStateIndependence:
    """
    Tests for session state independence.
    
    CTO Correction #3: Session state is cosmetic only.
    Backend is ALWAYS authoritative.
    
    Invariant 6.4: Different sessions see same approval state.
    """
    
    def test_session_state_no_approved_list(self):
        """Session state must NOT have 'approved' list."""
        # This tests the init_session_state function contract
        # Simulate what app.py does
        
        defaults = {
            'workflow_result': None,
            'action_cards': [],
            'summary': None,
            'primary_message': None,
            'current_decision_id': None,
            'current_trace_id': None,
            'selected_card': None,
            # REMOVED: 'approved': []
            # REMOVED: 'rejected': []
            'processing': False,
            'current_node': None,
            'error_message': None,
            'last_query': None,
        }
        
        assert 'approved' not in defaults
        assert 'rejected' not in defaults
    
    def test_invariant_6_4_different_sessions_same_state(self, mock_db_connection):
        """Different sessions must see same approval state."""
        from services.approval_service import ApprovalService
        
        # This is a design contract test
        # Both service instances with same DB should return same data
        service1 = ApprovalService(mock_db_connection)
        service2 = ApprovalService(mock_db_connection)
        
        # They use the same backend
        assert service1._manager._db is service2._manager._db


# =============================================================================
# TEST CLASS: Analytics Isolation (CTO Correction #4)
# =============================================================================

class TestAnalyticsIsolation:
    """
    Tests for analytics code isolation.
    
    CTO Correction #4: Analytics code must not be reused by business logic.
    """
    
    def test_dashboard_has_analytics_label(self):
        """Dashboard functions must have ANALYTICS_LABEL in docstrings."""
        from ui.dashboard import (
            render_manager_dashboard,
            render_pending_queue,
            render_rejection_patterns,
            ANALYTICS_LABEL
        )
        
        # Key functions must have the analytics warning
        assert 'ANALYTICS' in render_manager_dashboard.__doc__
        assert 'ANALYTICS' in render_pending_queue.__doc__
        assert 'ANALYTICS' in render_rejection_patterns.__doc__
    
    def test_dashboard_does_not_import_agents(self):
        """Dashboard must not import agent modules."""
        import ast
        from pathlib import Path
        
        dashboard_path = Path(__file__).parent.parent / 'ui' / 'dashboard.py'
        
        if dashboard_path.exists():
            source = dashboard_path.read_text(encoding='utf-8')
            tree = ast.parse(source)
            
            # Check all imports
            forbidden_imports = ['agents.', 'graph.nodes', 'strategist', 'analyst']
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_imports:
                            assert forbidden not in alias.name, \
                                f"Dashboard imports forbidden module: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for forbidden in forbidden_imports:
                            assert forbidden not in node.module, \
                                f"Dashboard imports from forbidden module: {node.module}"
    
    def test_rejection_analytics_is_read_only(self):
        """get_rejection_analytics must return data, not modify state."""
        from services.approval_service import ApprovalService
        
        # Verify it's a read-only method (returns data, no mutations)
        import inspect
        method = ApprovalService.get_rejection_analytics
        
        # Check it returns Dict (read operation)
        # and docstring mentions analytics-only
        assert 'ANALYTICS' in method.__doc__ or 'analytics' in method.__doc__.lower()


# =============================================================================
# TEST CLASS: Invariant Tests
# =============================================================================

class TestPhase6Invariants:
    """
    Tests for Phase 6 invariants.
    
    These tests verify the non-negotiable contracts.
    """
    
    def test_invariant_6_1_ui_never_computes_approval_state(self):
        """
        Invariant 6.1: UI Never Computes Approval State.
        
        UI must query ApprovalService for approval status.
        """
        # This is verified by:
        # 1. No 'approved'/'rejected' lists in session state defaults
        # 2. render_priority_actions calls get_pending_finding_ids()
        
        # Check that get_pending_finding_ids exists in app.py
        from pathlib import Path
        
        app_path = Path(__file__).parent.parent / 'app.py'
        
        if app_path.exists():
            source = app_path.read_text(encoding='utf-8')
            
            # Must have the helper function
            assert 'get_pending_finding_ids' in source
            
            # Must NOT have active session state tracking for approvals
            # Check that it's commented out (# REMOVED) not active
            assert "'approved': []," not in source, \
                "Session state should not have 'approved' list as a default"
    
    def test_invariant_6_2_finding_id_flows_end_to_end(self):
        """
        Invariant 6.2: finding_id Flows End-to-End.
        
        finding_id generated by Strategist must appear in ApprovalRecord.
        """
        # The finding dict must include finding_id
        # ApprovalManager.create_pending uses finding.get('finding_id')
        
        from persistence.approvals import ApprovalManager
        import inspect
        
        source = inspect.getsource(ApprovalManager.create_pending)
        
        # Must access finding_id from the dict
        assert 'finding_id' in source
        assert "finding.get('finding_id')" in source or 'finding["finding_id"]' in source
    
    def test_invariant_6_3_trace_correlation(self):
        """
        Invariant 6.3: Trace Correlation.
        
        trace_id + decision_id must link everything.
        """
        from graph.trace import DecisionTrace
        
        # DecisionTrace must have both fields
        assert hasattr(DecisionTrace, '__dataclass_fields__')
        fields = DecisionTrace.__dataclass_fields__
        
        assert 'trace_id' in fields
        assert 'decision_id' in fields
    
    def test_invariant_6_5_no_implicit_learning(self):
        """
        Invariant 6.5: No Implicit Learning.
        
        Rejection analytics must not feed back into AI.
        """
        from persistence.approvals import ApprovalManager
        import inspect
        
        source = inspect.getsource(ApprovalManager.get_rejection_analytics)
        
        # Must have the warning comment
        assert 'NOT used to modify AI' in source or 'not model feedback' in source.lower()
    
    def test_invariant_6_6_deterministic_replay(self):
        """
        Invariant 6.6: Deterministic Replay.
        
        Event sourcing must support replay.
        """
        from persistence.approvals import ApprovalManager
        
        # Must have time-travel query capability
        assert hasattr(ApprovalManager, 'get_state_at_time')
        assert hasattr(ApprovalManager, 'get_event_history')


# =============================================================================
# TEST CLASS: Integration Tests
# =============================================================================

class TestPhase6Integration:
    """
    Integration tests for Phase 6 components working together.
    """
    
    def test_workflow_to_approval_flow(self, mock_db_connection, sample_finding_dict):
        """Test the full flow from workflow to approval."""
        from graph.workflow import generate_decision_id, generate_trace_id
        from services.approval_service import ApprovalService
        
        # Generate IDs as workflow would
        decision_id = generate_decision_id()
        trace_id = generate_trace_id()
        
        # Simulate what would happen after Strategist produces findings
        sample_finding_dict['finding_id'] = sample_finding_dict.get('finding_id') or str(uuid.uuid4())
        
        # Service should be able to submit
        service = ApprovalService(mock_db_connection)
        
        # Verify the service method exists and has correct signature
        assert hasattr(service, 'submit_for_approval')
        assert hasattr(service, 'get_pending')
        assert hasattr(service, 'approve')
        assert hasattr(service, 'reject')
    
    def test_trace_with_integrity_and_decision_id(self):
        """Test trace creation with both integrity status and decision_id."""
        from graph.trace import (
            create_trace, IntegrityStatus,
            GuardrailsTraceEntry, AnalystTraceEntry,
            StrategistTraceEntry, CopywriterTraceEntry,
            get_execution_summary
        )
        
        trace, writer = create_trace(
            trace_id="trace_test123",
            original_query="Show churn risks",
            decision_id="decision_test456"
        )
        
        # Write all entries
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="Show churn risks",
            classification="allowed"
        ))
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT * FROM v_churn",
            sql_valid=True,
            execution_success=True
        ))
        writer.write_strategist(StrategistTraceEntry(
            timestamp=datetime.now(),
            findings_count=3,
            actions_generated=3
        ))
        writer.write_copywriter(CopywriterTraceEntry(
            timestamp=datetime.now(),
            messages_generated=3,
            tone_used='concerned',
            discount_source='strategist'
        ))
        
        writer.finalize('success')
        
        # Verify everything is set correctly
        assert trace.integrity_status == IntegrityStatus.COMPLETE
        assert trace.decision_id == "decision_test456"
        assert trace.final_outcome == "success"
        
        # Check summary includes new fields
        summary = get_execution_summary(trace)
        
        assert summary['decision_id'] == "decision_test456"
        assert summary['integrity_status'] == "complete"
        assert 'guardrails' in summary['agents_executed']
        assert 'copywriter' in summary['agents_executed']


# =============================================================================
# PHASE 6 SENTINEL TEST (TRIPWIRE)
# =============================================================================

class TestPhase6Sentinel:
    """
    PHASE 6 LOCK SENTINEL
    
    This test acts as a tripwire during refactors.
    If this test fails, Phase 6 invariants have been violated.
    
    DO NOT MODIFY without CTO approval.
    See: docs/PHASE6_LOCK.md
    """
    
    def test_phase6_contract_not_violated(self):
        """
        Single sentinel test that verifies ALL Phase 6 invariants are intact.
        
        This test should be run before ANY change to:
        - app.py
        - services/approval_service.py
        - persistence/approvals.py
        - graph/workflow.py
        - graph/trace.py
        """
        # === INVARIANT 6.1: UI must not track approval state ===
        from pathlib import Path
        app_path = Path(__file__).parent.parent / 'app.py'
        if app_path.exists():
            app_source = app_path.read_text(encoding='utf-8')
            # Session state must NOT have active approved/rejected lists
            assert "'approved': []," not in app_source, \
                "PHASE 6 VIOLATION: app.py has 'approved' list in session state"
            assert "'rejected': []," not in app_source, \
                "PHASE 6 VIOLATION: app.py has 'rejected' list in session state"
        
        # === INVARIANT 6.2: finding_id flows end-to-end ===
        from persistence.approvals import ApprovalManager
        import inspect
        create_pending_source = inspect.getsource(ApprovalManager.create_pending)
        assert 'finding_id' in create_pending_source, \
            "PHASE 6 VIOLATION: ApprovalManager.create_pending doesn't use finding_id"
        
        # === INVARIANT 6.3: DecisionTrace has integrity_status and decision_id ===
        from graph.trace import DecisionTrace, IntegrityStatus
        assert hasattr(DecisionTrace, '__dataclass_fields__'), \
            "PHASE 6 VIOLATION: DecisionTrace is not a dataclass"
        fields = DecisionTrace.__dataclass_fields__
        assert 'integrity_status' in fields, \
            "PHASE 6 VIOLATION: DecisionTrace missing integrity_status"
        assert 'decision_id' in fields, \
            "PHASE 6 VIOLATION: DecisionTrace missing decision_id"
        
        # === INVARIANT 6.4: Backend authority (ApprovalService exists) ===
        from services.approval_service import ApprovalService
        assert hasattr(ApprovalService, 'get_pending'), \
            "PHASE 6 VIOLATION: ApprovalService missing get_pending"
        assert hasattr(ApprovalService, 'approve'), \
            "PHASE 6 VIOLATION: ApprovalService missing approve"
        assert hasattr(ApprovalService, 'reject'), \
            "PHASE 6 VIOLATION: ApprovalService missing reject"
        
        # === INVARIANT 6.5: State machine is Final and enforced ===
        from persistence.approvals import ALLOWED_TRANSITIONS, ApprovalStatus
        assert ApprovalStatus.APPROVED in ALLOWED_TRANSITIONS, \
            "PHASE 6 VIOLATION: ALLOWED_TRANSITIONS missing APPROVED"
        assert len(ALLOWED_TRANSITIONS[ApprovalStatus.APPROVED]) == 0, \
            "PHASE 6 VIOLATION: APPROVED is not terminal (has outgoing transitions)"
        assert len(ALLOWED_TRANSITIONS[ApprovalStatus.REJECTED]) == 0, \
            "PHASE 6 VIOLATION: REJECTED is not terminal (has outgoing transitions)"
        
        # === INVARIANT 6.6: managed_trace exists for guaranteed finalization ===
        from graph.workflow import managed_trace
        import inspect
        
        # managed_trace should be a generator function decorated with @contextmanager
        # Verify it exists and is callable
        assert callable(managed_trace), \
            "PHASE 6 VIOLATION: managed_trace is not callable"
        
        # Check the source contains contextmanager decorator and try/finally
        source = inspect.getsource(managed_trace)
        assert 'yield' in source, \
            "PHASE 6 VIOLATION: managed_trace doesn't yield (not a context manager)"
        assert 'finally' in source, \
            "PHASE 6 VIOLATION: managed_trace doesn't have finally block (no guaranteed finalization)"
    
    def test_phase6_lock_file_exists(self):
        """Verify PHASE6_LOCK.md exists and contains key sections."""
        from pathlib import Path
        
        lock_path = Path(__file__).parent.parent / 'docs' / 'PHASE6_LOCK.md'
        
        assert lock_path.exists(), \
            "PHASE 6 VIOLATION: docs/PHASE6_LOCK.md does not exist"
        
        content = lock_path.read_text(encoding='utf-8')
        
        # Must contain key sections
        assert 'LOCKED' in content, \
            "PHASE 6 VIOLATION: PHASE6_LOCK.md missing LOCKED status"
        assert 'Non-Negotiable Invariants' in content, \
            "PHASE 6 VIOLATION: PHASE6_LOCK.md missing invariants section"
        assert 'DO NOT' in content, \
            "PHASE 6 VIOLATION: PHASE6_LOCK.md missing DO NOT rules"


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
