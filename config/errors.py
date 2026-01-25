"""
SalesFlow AI Error Taxonomy
===========================

This file defines a typed error hierarchy for the system.
Errors are categorized by source, recoverability, and user impact.

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL CTO CONSTRAINT:                                                    ║
║  EmptyResultError is NOT an error. It is a TERMINAL SUCCESS STATE.           ║
║  It has a code for logging, but does NOT go through error handling paths.    ║
║  This matters for: Metrics, Monitoring, Alerting, SLA reporting.             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Error Philosophy:
-----------------
1. Errors should be typed, not stringly-typed
2. Every error has a code for programmatic handling
3. Every error has a user-friendly message (no stack traces to users)
4. Errors are categorized by WHO should handle them:
   - USER_ERROR: User can fix by changing their query
   - SYSTEM_ERROR: Requires operator/developer intervention
   - TRANSIENT_ERROR: Retry may succeed
   
Non-Error Outcomes:
-------------------
- EMPTY_RESULT: The query was valid, execution succeeded, no data matched.
  This is a SUCCESS, not an error. "No churn risk found" is good news.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Final
from datetime import datetime


class ErrorCategory(Enum):
    """
    Categorizes errors by who is responsible for resolution.
    This affects UI presentation and alerting behavior.
    """
    USER_ERROR = "user_error"         # User can fix by changing their input
    SYSTEM_ERROR = "system_error"     # Requires developer/operator intervention
    TRANSIENT_ERROR = "transient"     # Retry may succeed without changes


class ErrorCode(Enum):
    """
    Unique codes for each error type.
    Format: CATEGORY_COMPONENT_SPECIFIC
    
    These codes are:
    - Logged for debugging
    - Returned to UI for programmatic handling
    - Used in monitoring dashboards
    """
    # Guardrails errors (1xxx)
    GUARDRAILS_BLOCKED_PATTERN = "E1001"
    GUARDRAILS_OFFTOPIC_QUERY = "E1002"
    GUARDRAILS_MALICIOUS_INTENT = "E1003"
    GUARDRAILS_EMPTY_QUERY = "E1004"
    
    # Analyst errors (2xxx)
    ANALYST_SQL_GENERATION_FAILED = "E2001"
    ANALYST_SQL_VALIDATION_FAILED = "E2002"
    ANALYST_SQL_BLOCKED_PATTERN = "E2003"
    ANALYST_SQL_EXECUTION_FAILED = "E2004"
    ANALYST_VIEW_NOT_ALLOWED = "E2005"
    ANALYST_MAX_RETRIES_EXCEEDED = "E2006"
    
    # Strategist errors (3xxx)
    STRATEGIST_NO_DATA_PROVIDED = "E3001"
    STRATEGIST_INVALID_DATA_FORMAT = "E3002"
    STRATEGIST_PROCESSING_FAILED = "E3003"
    
    # Copywriter errors (4xxx)
    COPYWRITER_NO_FINDINGS = "E4001"
    COPYWRITER_GENERATION_FAILED = "E4002"
    
    # LLM/Infrastructure errors (5xxx)
    LLM_API_ERROR = "E5001"
    LLM_RATE_LIMITED = "E5002"
    LLM_CONTEXT_TOO_LONG = "E5003"
    LLM_INVALID_RESPONSE = "E5004"
    
    # Database errors (6xxx)
    DB_CONNECTION_FAILED = "E6001"
    DB_QUERY_TIMEOUT = "E6002"
    DB_INTEGRITY_ERROR = "E6003"
    
    # Workflow errors (7xxx)
    WORKFLOW_STATE_INVALID = "E7001"
    WORKFLOW_NODE_FAILED = "E7002"
    WORKFLOW_TIMEOUT = "E7003"


# =============================================================================
# BASE ERROR CLASS
# =============================================================================

@dataclass
class SalesFlowError(Exception):
    """
    Base class for all SalesFlow errors.
    
    All errors have:
    - code: Unique identifier for programmatic handling
    - message: Technical description for logs
    - user_message: Friendly message safe to show users
    - category: Who should handle this error
    - recoverable: Can the operation be retried?
    - timestamp: When the error occurred
    """
    code: ErrorCode
    message: str
    user_message: str
    category: ErrorCategory
    recoverable: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    details: Optional[dict] = None
    
    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"
    
    def to_dict(self) -> dict:
        """Serialize for logging/API responses."""
        return {
            "code": self.code.value,
            "message": self.message,
            "user_message": self.user_message,
            "category": self.category.value,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


# =============================================================================
# GUARDRAILS ERRORS
# =============================================================================

@dataclass
class GuardrailsError(SalesFlowError):
    """Base class for guardrails-related errors."""
    code: ErrorCode = field(default=ErrorCode.GUARDRAILS_BLOCKED_PATTERN)
    message: str = field(default="Guardrails error")
    user_message: str = field(default="There was an issue processing your query.")
    category: ErrorCategory = field(default=ErrorCategory.USER_ERROR)


@dataclass
class BlockedPatternError(GuardrailsError):
    """Query contains a blocked pattern (SQL injection, etc.)."""
    code: ErrorCode = field(default=ErrorCode.GUARDRAILS_BLOCKED_PATTERN)
    message: str = field(default="Blocked pattern detected")
    user_message: str = field(
        default="Your query contains patterns that aren't allowed. Please rephrase."
    )
    blocked_pattern: Optional[str] = None


@dataclass
class OffTopicQueryError(GuardrailsError):
    """Query is not related to sales/retailer analysis."""
    code: ErrorCode = field(default=ErrorCode.GUARDRAILS_OFFTOPIC_QUERY)
    message: str = field(default="Off-topic query")
    user_message: str = field(
        default="I can only help with sales and retailer analysis. Please ask about "
                "churn risk, retailer performance, or cross-sell opportunities."
    )


@dataclass
class MaliciousIntentError(GuardrailsError):
    """Query appears to have malicious intent."""
    code: ErrorCode = field(default=ErrorCode.GUARDRAILS_MALICIOUS_INTENT)
    message: str = field(default="Malicious intent detected")
    user_message: str = field(
        default="I couldn't process that query. Please try a different approach."
    )
    # Note: Don't reveal WHY it was flagged - that helps attackers


@dataclass
class EmptyQueryError(GuardrailsError):
    """User submitted empty or whitespace-only query."""
    code: ErrorCode = field(default=ErrorCode.GUARDRAILS_EMPTY_QUERY)
    message: str = field(default="Empty query submitted")
    user_message: str = field(
        default="Please enter a question about your retailers or sales data."
    )


# =============================================================================
# ANALYST ERRORS
# =============================================================================

@dataclass
class AnalystError(SalesFlowError):
    """Base class for analyst-related errors."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_SQL_GENERATION_FAILED)
    message: str = field(default="Analyst error")
    user_message: str = field(default="There was an issue with the analysis.")
    category: ErrorCategory = field(default=ErrorCategory.SYSTEM_ERROR)


@dataclass
class SQLGenerationError(AnalystError):
    """LLM failed to generate valid SQL."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_SQL_GENERATION_FAILED)
    message: str = field(default="SQL generation failed")
    user_message: str = field(
        default="I had trouble understanding that request. Could you rephrase it?"
    )
    recoverable: bool = True  # Retry with clarification may help


@dataclass
class SQLValidationError(AnalystError):
    """Generated SQL failed validation (syntax, blocked patterns)."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_SQL_VALIDATION_FAILED)
    message: str = field(default="SQL validation failed")
    user_message: str = field(
        default="I generated an invalid query. Let me try again..."
    )
    recoverable: bool = True
    sql_attempted: Optional[str] = None
    validation_error: Optional[str] = None


@dataclass
class SQLBlockedPatternError(AnalystError):
    """Generated SQL contains blocked patterns (UPDATE, DELETE, etc.)."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_SQL_BLOCKED_PATTERN)
    message: str = field(default="SQL blocked pattern detected")
    user_message: str = field(
        default="I can only read data, not modify it. Let me try a different approach."
    )
    blocked_pattern: Optional[str] = None


@dataclass
class SQLExecutionError(AnalystError):
    """SQL execution failed at database level."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_SQL_EXECUTION_FAILED)
    message: str = field(default="SQL execution failed")
    user_message: str = field(
        default="There was a problem running the analysis. Please try again."
    )
    sql_executed: Optional[str] = None
    db_error: Optional[str] = None


@dataclass  
class ViewNotAllowedError(AnalystError):
    """Query attempted to access a view/table not in ALLOWED_VIEWS."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_VIEW_NOT_ALLOWED)
    message: str = field(default="View not allowed")
    user_message: str = field(
        default="I can only analyze certain types of data. Let me adjust my approach."
    )
    requested_view: Optional[str] = None


@dataclass
class MaxRetriesExceededError(AnalystError):
    """Analyst exceeded maximum retry attempts."""
    code: ErrorCode = field(default=ErrorCode.ANALYST_MAX_RETRIES_EXCEEDED)
    message: str = field(default="Max retries exceeded")
    user_message: str = field(
        default="I wasn't able to complete that analysis. Please try simplifying your question."
    )
    attempts: int = 0


# =============================================================================
# STRATEGIST ERRORS
# =============================================================================

@dataclass
class StrategistError(SalesFlowError):
    """Base class for strategist-related errors."""
    code: ErrorCode = field(default=ErrorCode.STRATEGIST_NO_DATA_PROVIDED)
    message: str = field(default="Strategist error")
    user_message: str = field(default="There was an issue generating insights.")
    category: ErrorCategory = field(default=ErrorCategory.SYSTEM_ERROR)


@dataclass
class NoDataProvidedError(StrategistError):
    """Strategist received no data from Analyst."""
    code: ErrorCode = field(default=ErrorCode.STRATEGIST_NO_DATA_PROVIDED)
    message: str = field(default="No data provided to strategist")
    user_message: str = field(
        default="No data was available for analysis. This may indicate a system issue."
    )


@dataclass
class InvalidDataFormatError(StrategistError):
    """Data format doesn't match expected schema."""
    code: ErrorCode = field(default=ErrorCode.STRATEGIST_INVALID_DATA_FORMAT)
    message: str = field(default="Invalid data format")
    user_message: str = field(
        default="There was an issue processing the analysis results."
    )
    expected_columns: Optional[list] = None
    received_columns: Optional[list] = None


# =============================================================================
# LLM/INFRASTRUCTURE ERRORS
# =============================================================================

@dataclass
class LLMError(SalesFlowError):
    """Base class for LLM-related errors."""
    code: ErrorCode = field(default=ErrorCode.LLM_API_ERROR)
    message: str = field(default="LLM error")
    user_message: str = field(default="The AI service encountered an issue.")
    category: ErrorCategory = field(default=ErrorCategory.TRANSIENT_ERROR)
    recoverable: bool = True


@dataclass
class LLMAPIError(LLMError):
    """LLM API call failed."""
    code: ErrorCode = field(default=ErrorCode.LLM_API_ERROR)
    message: str = field(default="LLM API error")
    user_message: str = field(
        default="The AI service is temporarily unavailable. Please try again."
    )
    status_code: Optional[int] = None


@dataclass
class LLMRateLimitedError(LLMError):
    """LLM API rate limited."""
    code: ErrorCode = field(default=ErrorCode.LLM_RATE_LIMITED)
    message: str = field(default="LLM rate limited")
    user_message: str = field(
        default="The system is busy. Please wait a moment and try again."
    )
    retry_after: Optional[int] = None  # seconds


# =============================================================================
# NON-ERROR OUTCOMES
# =============================================================================
# These are NOT errors. They are terminal success states.
# They have codes for logging but do NOT inherit from SalesFlowError.

@dataclass
class EmptyResultOutcome:
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  THIS IS NOT AN ERROR.                                                   ║
    ║  Empty result means: query valid, execution succeeded, no data matched.  ║
    ║  "No churn risk found" is GOOD NEWS, not a failure.                      ║
    ║                                                                          ║
    ║  This class exists for:                                                  ║
    ║  - Consistent logging format                                             ║
    ║  - UI can distinguish "no results" from "error"                          ║
    ║  - Metrics track outcomes without polluting error counts                 ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    code: str = "S0001"  # S for Success, not E for Error
    message: str = "Query executed successfully with no matching results"
    user_message: str = "No issues found matching your criteria. This is good news!"
    timestamp: datetime = field(default_factory=datetime.now)
    query_context: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "status": "success",  # Explicitly NOT "error"
            "message": self.message,
            "user_message": self.user_message,
            "timestamp": self.timestamp.isoformat(),
            "query_context": self.query_context,
        }


# =============================================================================
# OUTCOME CODES (Non-Error Terminal States)
# =============================================================================

class OutcomeCode(Enum):
    """
    Codes for successful terminal states.
    These are NOT errors - they're logged for metrics but don't trigger alerts.
    """
    EMPTY_RESULT = "S0001"          # Valid query, no data matched
    ANALYSIS_COMPLETE = "S0002"     # Full pipeline completed successfully
    PARTIAL_RESULT = "S0003"        # Some findings, but data was limited
    

# =============================================================================
# ERROR UTILITY FUNCTIONS
# =============================================================================

def is_user_recoverable(error: SalesFlowError) -> bool:
    """
    Determine if user action can resolve the error.
    Used for UI guidance (show "try again" vs "contact support").
    """
    if error.category == ErrorCategory.USER_ERROR:
        return True
    if error.recoverable:
        return True
    return False


def is_retriable(error: SalesFlowError) -> bool:
    """
    Determine if the operation should be automatically retried.
    Used for internal retry logic.
    """
    if error.category == ErrorCategory.TRANSIENT_ERROR:
        return True
    if error.recoverable and error.category != ErrorCategory.USER_ERROR:
        return True
    return False


def format_for_user(error: SalesFlowError) -> str:
    """
    Get the user-safe message for an error.
    Never expose technical details, stack traces, or SQL.
    """
    return error.user_message


def format_for_log(error: SalesFlowError) -> dict:
    """
    Get the full error details for logging.
    Includes technical details for debugging.
    """
    return error.to_dict()


# =============================================================================
# ERROR CODE REGISTRY
# =============================================================================
# Maps error codes to their classes for deserialization/handling.

ERROR_REGISTRY: Final[dict] = {
    ErrorCode.GUARDRAILS_BLOCKED_PATTERN: BlockedPatternError,
    ErrorCode.GUARDRAILS_OFFTOPIC_QUERY: OffTopicQueryError,
    ErrorCode.GUARDRAILS_MALICIOUS_INTENT: MaliciousIntentError,
    ErrorCode.GUARDRAILS_EMPTY_QUERY: EmptyQueryError,
    ErrorCode.ANALYST_SQL_GENERATION_FAILED: SQLGenerationError,
    ErrorCode.ANALYST_SQL_VALIDATION_FAILED: SQLValidationError,
    ErrorCode.ANALYST_SQL_BLOCKED_PATTERN: SQLBlockedPatternError,
    ErrorCode.ANALYST_SQL_EXECUTION_FAILED: SQLExecutionError,
    ErrorCode.ANALYST_VIEW_NOT_ALLOWED: ViewNotAllowedError,
    ErrorCode.ANALYST_MAX_RETRIES_EXCEEDED: MaxRetriesExceededError,
    ErrorCode.STRATEGIST_NO_DATA_PROVIDED: NoDataProvidedError,
    ErrorCode.STRATEGIST_INVALID_DATA_FORMAT: InvalidDataFormatError,
    ErrorCode.LLM_API_ERROR: LLMAPIError,
    ErrorCode.LLM_RATE_LIMITED: LLMRateLimitedError,
}
