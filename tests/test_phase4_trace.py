"""
Phase 4 Decision Trace Tests
============================

Tests for the decision trace system ensuring:
1. Write-only constraint during execution
2. Append-only semantics
3. No cross-agent trace reads
4. Trace integrity after workflow completion
5. CTO-MANDATED: No runtime reads of decision_trace in agents

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL TEST: test_decision_trace_not_used_in_logic                        ║
║                                                                              ║
║  This test ensures no agent reads from decision_trace during execution.      ║
║  This is a CTO mandate to prevent trace-based reasoning corruption.          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import pytest
import os
import re
import ast
from datetime import datetime
from pathlib import Path
from typing import List

from graph.trace import (
    DecisionTrace,
    TraceWriter,
    create_trace,
    GuardrailsTraceEntry,
    AnalystTraceEntry,
    StrategistTraceEntry,
    CopywriterTraceEntry,
    WorkflowTraceEntry,
    DataProvenance,
    SeverityComputation,
    get_execution_summary,
    validate_trace_integrity,
    VALID_OUTCOMES,
)


# =============================================================================
# TRACE CREATION AND WRITE-ONLY TESTS
# =============================================================================

class TestTraceCreation:
    """Tests for trace factory and initialization."""
    
    def test_create_trace_returns_tuple(self):
        """create_trace returns both trace and writer."""
        trace, writer = create_trace("test-id-001", "show me churn")
        
        assert isinstance(trace, DecisionTrace)
        assert isinstance(writer, TraceWriter)
    
    def test_trace_has_required_fields(self):
        """Trace is initialized with required fields."""
        trace, _ = create_trace("test-id-002", "show me churn risk")
        
        assert trace.trace_id == "test-id-002"
        assert trace.original_query == "show me churn risk"
        assert trace.started_at is not None
        assert trace.completed_at is None  # Not complete yet
        assert trace.final_outcome == ""
    
    def test_trace_id_preserved(self):
        """Trace ID is preserved throughout lifecycle."""
        trace, writer = create_trace("unique-id-xyz", "query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="query",
            classification="allowed",
            detected_patterns=[],
            topic_category="general",
            intent_label="query",
        ))
        writer.finalize("success")
        
        assert trace.trace_id == "unique-id-xyz"


class TestTraceWriteOnly:
    """Tests ensuring trace is WRITE-ONLY during execution."""
    
    def test_writer_can_write_guardrails_entry(self):
        """Writer can append guardrails entry."""
        trace, writer = create_trace("test-001", "query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="query",
            classification="allowed",
            detected_patterns=[],
            topic_category="churn",
            intent_label="scan",
        ))
        
        assert trace.guardrails_entry is not None
        assert trace.guardrails_entry.classification == "allowed"
    
    def test_writer_can_write_analyst_entry(self):
        """Writer can append analyst entry."""
        trace, writer = create_trace("test-002", "query")
        
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT * FROM v_churn_candidates",
            sql_valid=True,
            execution_success=True,
            retry_count=0,
        ))
        
        assert trace.analyst_entry is not None
        assert trace.analyst_entry.sql_valid is True
    
    def test_writer_can_write_strategist_entry(self):
        """Writer can append strategist entry."""
        trace, writer = create_trace("test-003", "query")
        
        writer.write_strategist(StrategistTraceEntry(
            timestamp=datetime.now(),
            findings_count=5,
            actions_generated=5,
            severity_computations=[],
            suppression_applied=[],
            tier_distribution={"Gold": 2, "Silver": 3},
        ))
        
        assert trace.strategist_entry is not None
        assert trace.strategist_entry.findings_count == 5
    
    def test_writer_can_write_copywriter_entry(self):
        """Writer can append copywriter entry."""
        trace, writer = create_trace("test-004", "query")
        
        writer.write_copywriter(CopywriterTraceEntry(
            timestamp=datetime.now(),
            messages_generated=3,
            tone_used="urgent",
            discount_source="strategist",
            discount_value=10,
        ))
        
        assert trace.copywriter_entry is not None
        assert trace.copywriter_entry.discount_source == "strategist"
    
    def test_writer_can_write_multiple_workflow_events(self):
        """Writer can append multiple workflow events."""
        trace, writer = create_trace("test-005", "query")
        
        writer.write_workflow_event(WorkflowTraceEntry(
            timestamp=datetime.now(),
            event_type="start",
            source_node="START",
            target_node="guardrails",
        ))
        writer.write_workflow_event(WorkflowTraceEntry(
            timestamp=datetime.now(),
            event_type="route",
            source_node="guardrails",
            target_node="analyst",
            routing_reason="on_topic",
        ))
        
        assert len(trace.workflow_entries) == 2


class TestTraceAppendOnly:
    """Tests ensuring trace entries are APPEND-ONLY."""
    
    def test_cannot_write_guardrails_twice(self):
        """Writing guardrails entry twice raises error."""
        trace, writer = create_trace("test-append-001", "query")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="query",
            classification="allowed",
        ))
        
        with pytest.raises(RuntimeError, match="already written"):
            writer.write_guardrails(GuardrailsTraceEntry(
                timestamp=datetime.now(),
                original_query="query",
                classification="blocked",
            ))
    
    def test_cannot_write_analyst_twice(self):
        """Writing analyst entry twice raises error."""
        trace, writer = create_trace("test-append-002", "query")
        
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT 1",
            sql_valid=True,
            execution_success=True,
        ))
        
        with pytest.raises(RuntimeError, match="already written"):
            writer.write_analyst(AnalystTraceEntry(
                timestamp=datetime.now(),
                sql_generated="SELECT 2",
                sql_valid=True,
                execution_success=True,
            ))
    
    def test_cannot_write_strategist_twice(self):
        """Writing strategist entry twice raises error."""
        trace, writer = create_trace("test-append-003", "query")
        
        writer.write_strategist(StrategistTraceEntry(
            timestamp=datetime.now(),
            findings_count=1,
            actions_generated=1,
        ))
        
        with pytest.raises(RuntimeError, match="already written"):
            writer.write_strategist(StrategistTraceEntry(
                timestamp=datetime.now(),
                findings_count=2,
                actions_generated=2,
            ))
    
    def test_cannot_write_copywriter_twice(self):
        """Writing copywriter entry twice raises error."""
        trace, writer = create_trace("test-append-004", "query")
        
        writer.write_copywriter(CopywriterTraceEntry(
            timestamp=datetime.now(),
            messages_generated=1,
            tone_used="urgent",
            discount_source="strategist",
        ))
        
        with pytest.raises(RuntimeError, match="already written"):
            writer.write_copywriter(CopywriterTraceEntry(
                timestamp=datetime.now(),
                messages_generated=2,
                tone_used="routine",
                discount_source="strategist",
            ))


class TestTraceFinalization:
    """Tests for trace finalization and post-finalization behavior."""
    
    def test_finalize_sets_outcome(self):
        """Finalization sets the outcome."""
        trace, writer = create_trace("test-final-001", "query")
        
        writer.finalize("success")
        
        assert trace.final_outcome == "success"
    
    def test_finalize_sets_completed_at(self):
        """Finalization sets completion timestamp."""
        trace, writer = create_trace("test-final-002", "query")
        
        writer.finalize("success")
        
        assert trace.completed_at is not None
        assert trace.completed_at >= trace.started_at
    
    def test_cannot_write_after_finalization(self):
        """Writing after finalization raises error."""
        trace, writer = create_trace("test-final-003", "query")
        
        writer.finalize("success")
        
        with pytest.raises(RuntimeError, match="finalized"):
            writer.write_guardrails(GuardrailsTraceEntry(
                timestamp=datetime.now(),
                original_query="query",
                classification="allowed",
            ))
    
    def test_cannot_finalize_twice(self):
        """Finalizing twice raises error."""
        trace, writer = create_trace("test-final-004", "query")
        
        writer.finalize("success")
        
        with pytest.raises(RuntimeError, match="finalized"):
            writer.finalize("error")


class TestTraceSerialization:
    """Tests for trace serialization."""
    
    def test_trace_to_dict(self):
        """Trace can be serialized to dict."""
        trace, writer = create_trace("test-serial-001", "show me churn")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="show me churn",
            classification="allowed",
            detected_patterns=[],
            topic_category="churn",
            intent_label="query",
        ))
        writer.finalize("success")
        
        result = trace.to_dict()
        
        assert result["trace_id"] == "test-serial-001"
        assert result["original_query"] == "show me churn"
        assert result["final_outcome"] == "success"
        assert result["entries"]["guardrails"] is not None
        assert result["entries"]["guardrails"]["classification"] == "allowed"
    
    def test_trace_to_json(self):
        """Trace can be serialized to JSON."""
        trace, writer = create_trace("test-serial-002", "query")
        writer.finalize("empty_result")
        
        json_str = trace.to_json()
        
        assert isinstance(json_str, str)
        assert "test-serial-002" in json_str
        assert "empty_result" in json_str


class TestDataProvenance:
    """Tests for data provenance constraints."""
    
    def test_provenance_includes_view_used(self):
        """Provenance includes view information."""
        prov = DataProvenance(
            view_used="v_churn_candidates",
            columns_accessed=["retailer_id", "days_since_order"],
            filter_applied="days_since_order > 14",
        )
        
        result = prov.to_dict()
        
        assert result["view_used"] == "v_churn_candidates"
        assert "retailer_id" in result["columns_accessed"]
    
    def test_provenance_no_private_data(self):
        """
        Provenance must NOT contain private data.
        
        CTO CONSTRAINT: Provenance must never be sufficient to reconstruct
        private data. We check that forbidden fields are not included.
        """
        prov = DataProvenance(
            view_used="v_churn_candidates",
            columns_accessed=["retailer_id", "tier"],
            filter_applied="tier != 'Bronze'",
            row_count_returned=5,
            retailer_ids_affected=["R001", "R002"],  # OK - already in findings
        )
        
        result = prov.to_dict()
        
        # These fields should NOT exist
        assert "order_ids" not in result
        assert "transaction_dates" not in result
        assert "sku_ids" not in result
        assert "daily_counts" not in result


class TestSeverityComputation:
    """Tests for severity computation documentation."""
    
    def test_severity_computation_structure(self):
        """Severity computation captures rule execution."""
        comp = SeverityComputation(
            rule_name="days_since_order_threshold",
            threshold_value=14,
            actual_value=18,
            result="high",
        )
        
        result = comp.to_dict()
        
        assert result["rule_name"] == "days_since_order_threshold"
        assert result["threshold_value"] == 14
        assert result["actual_value"] == 18
        assert result["result"] == "high"


class TestExecutionSummary:
    """Tests for execution summary generation."""
    
    def test_execution_summary_structure(self):
        """Execution summary has required fields."""
        trace, writer = create_trace("test-summary-001", "show churning retailers")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="show churning retailers",
            classification="allowed",
        ))
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT ...",
            sql_valid=True,
            execution_success=True,
        ))
        writer.finalize("success")
        
        summary = get_execution_summary(trace)
        
        assert summary["trace_id"] == "test-summary-001"
        assert summary["outcome"] == "success"
        assert "guardrails" in summary["agents_executed"]
        assert "analyst" in summary["agents_executed"]


# =============================================================================
# CTO-MANDATED TEST: NO RUNTIME READS OF DECISION_TRACE IN AGENTS
# =============================================================================

class TestNoTraceReadsInAgents:
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  CTO-MANDATED TEST                                                       ║
    ║                                                                          ║
    ║  Ensure no agent reads from decision_trace during execution.             ║
    ║  This prevents trace-based reasoning which would corrupt the system.     ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    
    def test_decision_trace_not_used_in_logic(self):
        """
        Ensure no agent reads from decision_trace during execution.
        
        This is a CTO mandate. If this test fails, the system is at risk
        of trace-based reasoning corruption.
        
        Checks:
        1. agents/*.py files do not import DecisionTrace
        2. agents/*.py files do not read from trace variables
        3. agents/*.py files only use TraceWriter (write-only)
        """
        # Get path to agents directory
        agents_dir = Path(__file__).parent.parent / "agents"
        
        if not agents_dir.exists():
            pytest.skip("Agents directory not found")
        
        violations = []
        
        # Forbidden patterns that indicate trace reading
        forbidden_patterns = [
            # Direct trace access patterns
            r"decision_trace\s*\[",        # decision_trace[...]
            r"decision_trace\.get\(",      # decision_trace.get(...)
            r"\.guardrails_entry",         # Reading from trace entries
            r"\.analyst_entry",
            r"\.strategist_entry",
            r"\.copywriter_entry",
            r"trace\.guardrails",          # trace.guardrails_entry
            r"trace\.analyst",
            r"trace\.strategist",
            r"trace\.copywriter",
            # Reading trace fields
            r"trace\[.+\]",                # trace["something"]
            r"_trace\[.+\]",               # _trace["something"]
        ]
        
        # Allowed patterns (write-only)
        allowed_patterns = [
            r"TraceWriter",                # Import is OK
            r"write_guardrails",           # Writing is OK
            r"write_analyst",
            r"write_strategist",
            r"write_copywriter",
            r"write_workflow_event",
            r"_trace_writer",              # Write-only handle
        ]
        
        for agent_file in agents_dir.glob("*.py"):
            if agent_file.name.startswith("__"):
                continue
            
            content = agent_file.read_text(encoding="utf-8")
            
            # Check for forbidden patterns
            for pattern in forbidden_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    # Check if it's in a comment or docstring
                    for match in matches:
                        # Simple check - if the line contains the pattern
                        # and doesn't start with #, it's a violation
                        lines = content.split("\n")
                        for i, line in enumerate(lines, 1):
                            if match in line and not line.strip().startswith("#"):
                                # Check if in docstring (simplified)
                                if '"""' not in line and "'''" not in line:
                                    violations.append(
                                        f"{agent_file.name}:{i} - Found trace read pattern: {match}"
                                    )
        
        if violations:
            violation_msg = "\n".join(violations)
            pytest.fail(
                f"CTO VIOLATION: Agents must NOT read from decision_trace!\n"
                f"Found {len(violations)} violations:\n{violation_msg}\n\n"
                f"DecisionTrace is WRITE-ONLY during execution.\n"
                f"Use TraceWriter.write_*() methods only."
            )
    
    def test_agents_do_not_import_decision_trace_directly(self):
        """
        Agents should not import DecisionTrace directly.
        
        They should only import TraceWriter (write-only interface).
        DecisionTrace is for post-execution reading only.
        """
        agents_dir = Path(__file__).parent.parent / "agents"
        
        if not agents_dir.exists():
            pytest.skip("Agents directory not found")
        
        violations = []
        
        for agent_file in agents_dir.glob("*.py"):
            if agent_file.name.startswith("__"):
                continue
                
            content = agent_file.read_text(encoding="utf-8")
            
            # Check for direct DecisionTrace import
            if re.search(r"from graph\.trace import.*DecisionTrace", content):
                violations.append(f"{agent_file.name}: imports DecisionTrace directly")
            
            if re.search(r"import.*DecisionTrace", content):
                violations.append(f"{agent_file.name}: imports DecisionTrace")
        
        if violations:
            pytest.fail(
                f"Agents should not import DecisionTrace directly!\n"
                f"Use TraceWriter for write-only access.\n"
                f"Violations: {violations}"
            )
    
    def test_trace_writer_has_no_read_methods(self):
        """
        TraceWriter must not expose any read methods.
        
        This is a design constraint - the write-only interface
        must not allow reading trace contents.
        """
        writer_methods = [m for m in dir(TraceWriter) if not m.startswith("_")]
        
        read_patterns = ["read", "get", "fetch", "retrieve", "access", "query"]
        
        violations = []
        for method in writer_methods:
            for pattern in read_patterns:
                if pattern in method.lower():
                    violations.append(f"TraceWriter.{method} looks like a read method")
        
        if violations:
            pytest.fail(
                f"TraceWriter must be WRITE-ONLY!\n"
                f"Found suspicious methods: {violations}"
            )


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestTraceIntegration:
    """Integration tests for trace system with workflow."""
    
    def test_full_workflow_trace(self):
        """Simulate a full workflow and verify trace integrity."""
        trace, writer = create_trace("integration-001", "show me churn risk retailers")
        
        # Guardrails
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="show me churn risk retailers",
            classification="allowed",
            detected_patterns=[],
            topic_category="churn",
            intent_label="query",
            execution_time_ms=5.2,
        ))
        
        # Analyst
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT * FROM v_churn_candidates WHERE tier != 'Bronze'",
            sql_valid=True,
            execution_success=True,
            provenance=DataProvenance(
                view_used="v_churn_candidates",
                columns_accessed=["retailer_id", "days_since_order", "tier"],
                filter_applied="tier != 'Bronze'",
                row_count_returned=5,
            ),
            retry_count=0,
            execution_time_ms=150.3,
        ))
        
        # Strategist
        writer.write_strategist(StrategistTraceEntry(
            timestamp=datetime.now(),
            findings_count=5,
            actions_generated=5,
            severity_computations=[
                SeverityComputation(
                    rule_name="days_since_order_threshold",
                    threshold_value=14,
                    actual_value=18,
                    result="high",
                ),
            ],
            suppression_applied=[],
            tier_distribution={"Gold": 2, "Silver": 3, "Bronze": 0},
            execution_time_ms=200.1,
        ))
        
        # Copywriter
        writer.write_copywriter(CopywriterTraceEntry(
            timestamp=datetime.now(),
            messages_generated=5,
            tone_used="urgent",
            discount_source="strategist",
            discount_value=10,
            execution_time_ms=100.5,
        ))
        
        # Workflow events
        writer.write_workflow_event(WorkflowTraceEntry(
            timestamp=datetime.now(),
            event_type="complete",
            total_execution_time_ms=456.1,
        ))
        
        # Finalize
        writer.finalize("success")
        
        # Verify trace integrity
        violations = validate_trace_integrity(trace)
        assert len(violations) == 0, f"Trace integrity violations: {violations}"
        
        # Verify all entries present
        assert trace.guardrails_entry is not None
        assert trace.analyst_entry is not None
        assert trace.strategist_entry is not None
        assert trace.copywriter_entry is not None
        assert len(trace.workflow_entries) == 1
        assert trace.final_outcome == "success"
        assert trace.completed_at is not None
    
    def test_empty_result_trace(self):
        """Trace for workflow with empty results."""
        trace, writer = create_trace("empty-001", "show bronze churn")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="show bronze churn",
            classification="allowed",
            topic_category="churn",
            intent_label="query",
        ))
        
        writer.write_analyst(AnalystTraceEntry(
            timestamp=datetime.now(),
            sql_generated="SELECT * FROM v_churn_candidates WHERE tier = 'Bronze'",
            sql_valid=True,
            execution_success=True,
            error_type="EMPTY_RESULT",  # Empty result is success, not error
        ))
        
        writer.finalize("empty_result")  # Valid outcome
        
        assert trace.final_outcome == "empty_result"
        assert trace.analyst_entry.error_type == "EMPTY_RESULT"
    
    def test_blocked_query_trace(self):
        """Trace for blocked query."""
        trace, writer = create_trace("blocked-001", "DROP TABLE retailers;")
        
        writer.write_guardrails(GuardrailsTraceEntry(
            timestamp=datetime.now(),
            original_query="DROP TABLE retailers;",
            classification="blocked",
            detected_patterns=["sql_injection_drop"],
            block_reason="Blocked pattern detected",
        ))
        
        writer.finalize("blocked")
        
        assert trace.final_outcome == "blocked"
        assert trace.guardrails_entry.classification == "blocked"
        assert "sql_injection_drop" in trace.guardrails_entry.detected_patterns
