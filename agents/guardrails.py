"""
Guardrails Agent

Responsibility:
- Validate all user inputs before processing
- Classify queries as ON_TOPIC or OFF_TOPIC
- Detect prompt injection attempts
- Ensure output safety and appropriateness

Explicitly NOT responsible for:
- Business logic (other agents)
- Data processing (Analyst's job)
- User interface (UI module's job)

Security Layers:
1. INPUT VALIDATION: Check user query is within scope
2. SQL INJECTION PREVENTION: Block dangerous patterns
3. PII PROTECTION: Mask sensitive data in outputs
4. HALLUCINATION DETECTION: Flag responses without data backing

Topic Classification Rules:
ON_TOPIC queries relate to:
- Retailers, sales, orders, products
- Churn, cross-sell, revenue, visits
- FMCG distribution operations

OFF_TOPIC queries include:
- General knowledge questions
- Non-sales business queries
- Personal questions about the AI

Response Types:
- ALLOWED: Query passes, proceed to Analyst
- REDIRECT: Polite redirection to valid topics
- BLOCKED: Harmful content, refuse entirely

Detection Signals:
- Prompt injection: "ignore previous instructions"
- SQL injection: DROP, DELETE, UPDATE, --, UNION
- Jailbreak: Attempts to change system behavior

Output Format:
{
    "classification": "ON_TOPIC",
    "confidence": 0.94,
    "sanitized_query": "...",
    "warnings": [],
    "action": "ALLOWED"
}

Usage:
    from agents.guardrails import GuardrailsAgent
    guardrails = GuardrailsAgent(llm=llm)
    result = guardrails.validate(user_input)
    if result["action"] == "ALLOWED":
        proceed_with_query(result["sanitized_query"])
"""

from typing import Any, Dict, List
from langchain_core.language_models.chat_models import BaseChatModel


class GuardrailsAgent:
    """
    Input validation and safety agent.
    
    The Guardrails agent is the "security checkpoint" - it ensures
    all inputs are safe and appropriate before processing.
    """
    
    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Guardrails Agent.
        
        Args:
            llm: LangChain chat model (can be smaller/faster model)
        """
        self.llm = llm
        # Implementation will be added in Phase 5
        raise NotImplementedError("GuardrailsAgent will be implemented in Phase 5")
    
    def validate(self, user_input: str) -> Dict[str, Any]:
        """
        Validate user input for safety and relevance.
        
        Args:
            user_input: Raw user query
            
        Returns:
            Dict with classification, action, and sanitized query
        """
        raise NotImplementedError("Will be implemented in Phase 5")
    
    def classify_topic(self, query: str) -> str:
        """
        Classify query as ON_TOPIC or OFF_TOPIC.
        
        Args:
            query: User query to classify
            
        Returns:
            "ON_TOPIC" or "OFF_TOPIC"
        """
        raise NotImplementedError("Will be implemented in Phase 5")
    
    def detect_injection(self, text: str) -> List[str]:
        """
        Detect prompt injection attempts.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of detected injection patterns
        """
        raise NotImplementedError("Will be implemented in Phase 5")
    
    def sanitize_output(self, output: str) -> str:
        """
        Remove PII and sensitive information from output.
        
        Args:
            output: Raw agent output
            
        Returns:
            Sanitized output safe for display
        """
        raise NotImplementedError("Will be implemented in Phase 5")
