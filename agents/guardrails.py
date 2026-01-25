"""
Guardrails Agent - CONTROL BOUNDARY
====================================

╔══════════════════════════════════════════════════════════════════════════════╗
║  CRITICAL ARCHITECTURAL INVARIANT:                                           ║
║                                                                              ║
║  Guardrails is a CONTROL BOUNDARY, not a reasoning agent.                    ║
║                                                                              ║
║  It CLASSIFIES, BLOCKS, or ALLOWS queries.                                   ║
║  It does NOT:                                                                ║
║    - Rewrite or "improve" queries                                            ║
║    - Interpret business intent                                               ║
║    - Add context or clarification                                            ║
║    - Make decisions about data selection                                     ║
║                                                                              ║
║  The original query passes through UNCHANGED if allowed.                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Three-Layer Classification:
---------------------------
1. PATTERN DETECTION (Fast, deterministic)
   - Regex-based detection of blocked patterns
   - SQL injection attempts
   - Prompt injection attempts
   - No LLM required

2. TOPIC CLASSIFICATION (Determines if query is about sales/retailers)
   - Keyword-based first (fast path)
   - LLM fallback only for ambiguous cases
   - Binary: on-topic or off-topic

3. INTENT LABELING (For logging/UX, NOT for logic)
   - scan: Quick overview request
   - query: Specific question
   - explain: Detailed analysis request
   
   CRITICAL: Intent NEVER affects:
   - Which views are queried
   - Which rules are applied
   - Which thresholds are used
   Intent affects PRESENTATION only.

Output Contract:
----------------
{
    "classification": "allowed" | "blocked" | "offtopic",
    "original_query": str,  # UNCHANGED - we do NOT rewrite
    "detected_patterns": List[str],
    "topic_category": "churn" | "performance" | "crosssell" | "general" | None,
    "intent": "scan" | "query" | "explain",
    "block_reason": Optional[str],
}
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Final, Set
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from config.errors import (
    BlockedPatternError,
    OffTopicQueryError,
    MaliciousIntentError,
    EmptyQueryError,
)


# =============================================================================
# BLOCKED PATTERNS (Layer 1 - Deterministic, No LLM)
# =============================================================================

BLOCKED_PATTERNS: Final[List[tuple[str, str]]] = [
    # SQL Injection patterns
    (r";\s*DROP\s+", "sql_injection_drop"),
    (r";\s*DELETE\s+", "sql_injection_delete"),
    (r";\s*UPDATE\s+", "sql_injection_update"),
    (r";\s*INSERT\s+", "sql_injection_insert"),
    (r";\s*TRUNCATE\s+", "sql_injection_truncate"),
    (r";\s*ALTER\s+", "sql_injection_alter"),
    (r";\s*CREATE\s+", "sql_injection_create"),
    (r"--\s*$", "sql_comment_injection"),
    (r"UNION\s+SELECT", "sql_union_injection"),
    (r"'\s*OR\s+'1'\s*=\s*'1", "sql_tautology"),
    (r"'\s*OR\s+1\s*=\s*1", "sql_tautology_numeric"),
    
    # Prompt Injection patterns
    (r"ignore\s+(all\s+)?previous\s+instructions", "prompt_injection_ignore"),
    (r"disregard\s+(all\s+)?prior", "prompt_injection_disregard"),
    (r"forget\s+(everything|all)", "prompt_injection_forget"),
    (r"you\s+are\s+now\s+", "prompt_injection_roleplay"),
    (r"pretend\s+you\s+are", "prompt_injection_roleplay"),
    (r"act\s+as\s+(if|a|an)", "prompt_injection_roleplay"),
    (r"new\s+instructions:", "prompt_injection_override"),
    (r"system\s*:\s*", "prompt_injection_system"),
    (r"\[INST\]", "prompt_injection_llama"),
    (r"<\|im_start\|>", "prompt_injection_chatml"),
    
    # Jailbreak patterns
    (r"DAN\s+mode", "jailbreak_dan"),
    (r"developer\s+mode", "jailbreak_developer"),
    (r"bypass\s+(safety|filter|restriction)", "jailbreak_bypass"),
    (r"unlock\s+(your|full)\s+potential", "jailbreak_unlock"),
]

# Compile patterns for efficiency
COMPILED_BLOCKED_PATTERNS: Final[List[tuple[re.Pattern, str]]] = [
    (re.compile(pattern, re.IGNORECASE), name)
    for pattern, name in BLOCKED_PATTERNS
]


# =============================================================================
# TOPIC KEYWORDS (Layer 2 - Fast Path)
# =============================================================================

# Keywords that indicate on-topic queries (sales/retailer analysis)
ON_TOPIC_KEYWORDS: Final[Set[str]] = {
    # Entities
    "retailer", "retailers", "customer", "customers", "client", "clients",
    "store", "stores", "shop", "shops", "outlet", "outlets",
    # Actions/Metrics
    "churn", "churning", "churned", "attrition", "retention",
    "order", "orders", "ordering", "purchase", "purchases", "purchasing",
    "sale", "sales", "selling", "revenue", "transaction", "transactions",
    "visit", "visits", "visiting", "visited",
    "cross-sell", "crosssell", "upsell", "up-sell", "cross", "sell",  # Added cross/sell for hyphenated splitting
    "opportunity", "opportunities",  # Added for cross-sell context
    "performance", "performing", "underperforming",
    # Tiers
    "gold", "silver", "bronze", "tier", "tiers",
    # Risk/Status
    "risk", "risky", "at-risk", "declining", "decline", "inactive",
    "active", "engagement", "engaged",
    # Products
    "product", "products", "category", "categories", "sku",
    "beverage", "snacks", "dairy", "personal care",
    # Business
    "fmcg", "distribution", "wholesale", "supply",
}

# Keywords that strongly indicate off-topic
OFF_TOPIC_KEYWORDS: Final[Set[str]] = {
    "weather", "recipe", "movie", "music", "sport", "game",
    "joke", "story", "poem", "song", "code", "programming",
    "python", "javascript", "html", "css",
    "capital", "president", "history", "geography",
    "math", "calculate", "equation",
}

# Topic categories for classification
TOPIC_CATEGORIES: Final[Dict[str, Set[str]]] = {
    "churn": {"churn", "churning", "churned", "attrition", "retention", "risk", "at-risk", "inactive", "declining"},
    "performance": {"performance", "performing", "underperforming", "revenue", "sales", "order", "orders"},
    "crosssell": {"cross-sell", "crosssell", "upsell", "up-sell", "category", "categories", "opportunity", "opportunities", "cross", "sell"},
}


# =============================================================================
# INTENT PATTERNS (Layer 3 - UX Only, NOT Logic)
# =============================================================================

INTENT_PATTERNS: Final[Dict[str, List[str]]] = {
    "scan": [
        r"quick\s+(look|scan|overview|check)",
        r"show\s+me",
        r"what('s|s)\s+(the|my)",
        r"any\s+(issues|problems|concerns)",
        r"how\s+(are|is)\s+",
        r"brief\s+",
        r"summary\s+of",
    ],
    "query": [
        r"which\s+retailers",
        r"who\s+(has|is|are)",
        r"list\s+(all|the)",
        r"find\s+",
        r"get\s+(me|all)",
        r"how\s+many",
        r"what\s+percentage",
    ],
    "explain": [
        r"why\s+(is|are|do|does)",
        r"explain\s+",
        r"detail(s|ed)",
        r"analyze\s+",
        r"breakdown\s+of",
        r"deep\s+dive",
        r"in\s+depth",
    ],
}

COMPILED_INTENT_PATTERNS: Final[Dict[str, List[re.Pattern]]] = {
    intent: [re.compile(p, re.IGNORECASE) for p in patterns]
    for intent, patterns in INTENT_PATTERNS.items()
}


# =============================================================================
# CLASSIFICATION RESULT
# =============================================================================

@dataclass
class GuardrailsResult:
    """
    Immutable result from guardrails classification.
    
    Note: original_query is NEVER modified. Guardrails classifies, not rewrites.
    """
    classification: str  # "allowed" | "blocked" | "offtopic"
    original_query: str  # UNCHANGED from input
    detected_patterns: List[str]
    topic_category: Optional[str]  # "churn" | "performance" | "crosssell" | "general" | None
    intent: str  # "scan" | "query" | "explain"
    block_reason: Optional[str]
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification,
            "original_query": self.original_query,
            "detected_patterns": self.detected_patterns,
            "topic_category": self.topic_category,
            "intent": self.intent,
            "block_reason": self.block_reason,
            "execution_time_ms": self.execution_time_ms,
        }
    
    @property
    def is_allowed(self) -> bool:
        return self.classification == "allowed"
    
    @property
    def is_blocked(self) -> bool:
        return self.classification == "blocked"
    
    @property
    def is_offtopic(self) -> bool:
        return self.classification == "offtopic"


# =============================================================================
# GUARDRAILS AGENT
# =============================================================================

class GuardrailsAgent:
    """
    Control boundary for input validation.
    
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  THIS IS NOT A REASONING AGENT.                                          ║
    ║                                                                          ║
    ║  Guardrails performs CLASSIFICATION only:                                ║
    ║    1. Pattern detection (deterministic, fast)                            ║
    ║    2. Topic classification (keyword + optional LLM)                      ║
    ║    3. Intent labeling (for UX only)                                      ║
    ║                                                                          ║
    ║  It does NOT rewrite, improve, or interpret queries.                     ║
    ║  The original query passes through UNCHANGED.                            ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    
    def __init__(self, llm: Optional[BaseChatModel] = None, use_llm_fallback: bool = True):
        """
        Initialize the Guardrails Agent.
        
        Args:
            llm: Optional LangChain chat model for ambiguous topic classification.
                 If None, only keyword-based classification is used.
            use_llm_fallback: Whether to use LLM for ambiguous cases.
                              Set False for faster, deterministic-only mode.
        """
        self.llm = llm
        self.use_llm_fallback = use_llm_fallback and (llm is not None)
    
    def validate(self, user_input: str) -> GuardrailsResult:
        """
        Validate and classify user input.
        
        This is the main entry point. It runs all three layers:
        1. Pattern detection (blocked patterns)
        2. Topic classification (on-topic / off-topic)
        3. Intent labeling (scan / query / explain)
        
        Args:
            user_input: Raw user query (NEVER modified)
            
        Returns:
            GuardrailsResult with classification and metadata
        """
        start_time = time.time()
        
        # Normalize whitespace but preserve original
        query = user_input.strip()
        
        # Empty query check
        if not query:
            return GuardrailsResult(
                classification="blocked",
                original_query=user_input,
                detected_patterns=["empty_query"],
                topic_category=None,
                intent="query",
                block_reason="Empty query",
                execution_time_ms=(time.time() - start_time) * 1000,
            )
        
        # Layer 1: Pattern Detection
        detected = self._detect_blocked_patterns(query)
        if detected:
            return GuardrailsResult(
                classification="blocked",
                original_query=user_input,
                detected_patterns=detected,
                topic_category=None,
                intent="query",
                block_reason=f"Blocked pattern detected: {detected[0]}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )
        
        # Layer 2: Topic Classification
        is_on_topic, topic_category = self._classify_topic(query)
        if not is_on_topic:
            return GuardrailsResult(
                classification="offtopic",
                original_query=user_input,
                detected_patterns=[],
                topic_category=None,
                intent="query",
                block_reason="Query not related to sales/retailer analysis",
                execution_time_ms=(time.time() - start_time) * 1000,
            )
        
        # Layer 3: Intent Labeling (UX only, does NOT affect logic)
        intent = self._classify_intent(query)
        
        return GuardrailsResult(
            classification="allowed",
            original_query=user_input,  # UNCHANGED
            detected_patterns=[],
            topic_category=topic_category,
            intent=intent,
            block_reason=None,
            execution_time_ms=(time.time() - start_time) * 1000,
        )
    
    def _detect_blocked_patterns(self, query: str) -> List[str]:
        """
        Layer 1: Detect blocked patterns using regex.
        Deterministic, no LLM, very fast.
        
        Args:
            query: User query to check
            
        Returns:
            List of detected pattern names (empty if none)
        """
        detected = []
        for pattern, name in COMPILED_BLOCKED_PATTERNS:
            if pattern.search(query):
                detected.append(name)
        return detected
    
    def _classify_topic(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Layer 2: Classify whether query is on-topic.
        Uses keyword matching first, LLM fallback for ambiguous cases.
        
        Args:
            query: User query to classify
            
        Returns:
            tuple: (is_on_topic: bool, topic_category: Optional[str])
        """
        query_lower = query.lower()
        words = set(re.findall(r'\b\w+\b', query_lower))
        
        # Check for strong off-topic signals first
        off_topic_matches = words & OFF_TOPIC_KEYWORDS
        if off_topic_matches and not (words & ON_TOPIC_KEYWORDS):
            return False, None
        
        # Check for on-topic keywords
        on_topic_matches = words & ON_TOPIC_KEYWORDS
        if on_topic_matches:
            # Determine specific topic category
            category = self._determine_topic_category(words)
            return True, category
        
        # Ambiguous case - use LLM if available
        if self.use_llm_fallback:
            return self._llm_topic_classification(query)
        
        # Default: allow ambiguous queries (better UX)
        return True, "general"
    
    def _determine_topic_category(self, words: Set[str]) -> str:
        """
        Determine the specific topic category based on keywords.
        
        Args:
            words: Set of words from the query
            
        Returns:
            Topic category: "churn" | "performance" | "crosssell" | "general"
        """
        for category, keywords in TOPIC_CATEGORIES.items():
            if words & keywords:
                return category
        return "general"
    
    def _classify_intent(self, query: str) -> str:
        """
        Layer 3: Classify user intent for UX purposes.
        
        ╔══════════════════════════════════════════════════════════════════════╗
        ║  CRITICAL CTO CONSTRAINT:                                            ║
        ║                                                                      ║
        ║  Intent affects UX flow ONLY. It NEVER affects:                      ║
        ║    - Data selection                                                  ║
        ║    - Rule application                                                ║
        ║    - Thresholds                                                      ║
        ║    - Prioritization                                                  ║
        ║                                                                      ║
        ║  A "scan" and a "query" produce IDENTICAL business outputs.          ║
        ║  Only the PRESENTATION may differ.                                   ║
        ╚══════════════════════════════════════════════════════════════════════╝
        
        Args:
            query: User query to classify
            
        Returns:
            Intent: "scan" | "query" | "explain"
        """
        # Check each intent pattern
        for intent, patterns in COMPILED_INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(query):
                    return intent
        
        # Default to "query" if no clear intent
        return "query"
    
    def _llm_topic_classification(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Use LLM to classify ambiguous queries.
        Only called when keyword matching is inconclusive.
        
        Args:
            query: User query to classify
            
        Returns:
            tuple: (is_on_topic: bool, topic_category: Optional[str])
        """
        if not self.llm:
            return True, "general"  # Default to allow
        
        system_prompt = """You are a classifier. Determine if the query is about:
- Retailers, customers, or stores
- Sales, orders, or transactions
- Churn risk or customer retention
- Cross-sell or upsell opportunities
- Performance metrics in FMCG/retail

Respond with ONLY one word:
- "CHURN" if about churn/retention/at-risk
- "PERFORMANCE" if about sales/orders/revenue
- "CROSSSELL" if about cross-sell/upsell/categories
- "GENERAL" if about retailers/sales but no specific category
- "OFFTOPIC" if not related to sales/retail at all"""
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Query: {query}")
            ])
            
            result = response.content.strip().upper()
            
            if result == "OFFTOPIC":
                return False, None
            elif result in ("CHURN", "PERFORMANCE", "CROSSSELL", "GENERAL"):
                return True, result.lower()
            else:
                # Unexpected response, default to allow
                return True, "general"
                
        except Exception:
            # LLM failed, default to allow
            return True, "general"
    
    # =========================================================================
    # ERROR RAISING METHODS (For workflow integration)
    # =========================================================================
    
    def validate_or_raise(self, user_input: str) -> GuardrailsResult:
        """
        Validate input and raise appropriate error if blocked/offtopic.
        
        Use this when you want exceptions instead of checking result.classification.
        
        Args:
            user_input: Raw user query
            
        Returns:
            GuardrailsResult (only if allowed)
            
        Raises:
            EmptyQueryError: If query is empty
            BlockedPatternError: If blocked pattern detected
            OffTopicQueryError: If query is off-topic
        """
        result = self.validate(user_input)
        
        if result.is_allowed:
            return result
        
        if "empty_query" in result.detected_patterns:
            raise EmptyQueryError(
                message="Empty query submitted",
                details={"patterns": result.detected_patterns}
            )
        
        if result.is_blocked:
            raise BlockedPatternError(
                message=f"Blocked pattern detected: {result.detected_patterns}",
                blocked_pattern=result.detected_patterns[0] if result.detected_patterns else None,
                details={"all_patterns": result.detected_patterns}
            )
        
        if result.is_offtopic:
            raise OffTopicQueryError(
                message="Query is not related to sales/retailer analysis",
                details={"query": user_input}
            )
        
        # Shouldn't reach here, but just in case
        return result
