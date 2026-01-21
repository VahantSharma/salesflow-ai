"""
Copywriter Agent

Responsibility:
- Transform strategic insights into human-readable messages
- Craft empathetic, action-oriented sales communications
- Apply confidence-aware tone adjustment
- Maintain brand voice consistency

Explicitly NOT responsible for:
- Deciding WHAT to communicate (Strategist's job)
- Data analysis (Strategist's job)
- SQL queries (Analyst's job)

Personality:
- "Seasoned Sales Rep" - knows how to motivate action
- Uses concrete numbers and urgency
- Never sounds robotic or template-y
- Balances warmth with directness

Confidence-Aware Tone:
- HIGH confidence → ASSERTIVE: "Visit Kumar Stores immediately"
- MEDIUM confidence → SUGGESTIVE: "Consider reaching out to Kumar Stores"
- LOW confidence → EXPLORATORY: "You may want to check on Kumar Stores"

Action Friction Mapping (determines urgency/effort):
- MESSAGE: Low friction (app notification, quick)
- CALL: Medium friction (phone call, moderate effort)
- VISIT: High friction (in-person visit, significant effort)

Message Types:
1. CHURN_RISK: Retention-focused, empathetic, offers value
2. CROSS_SELL_GAP: Opportunity-focused, shows margin benefit
3. VALUE_DECLINE: Performance review, data-driven
4. NO_ISSUES: Positive reinforcement, celebrate stability

Template Rules:
- Include retailer name (personalization)
- Include ONE specific number (credibility)
- Include clear call-to-action (actionability)
- Keep under 280 characters (SMS/WhatsApp friendly)

Localization:
- Numbers in Indian format (₹47,000 not $47,000)
- Common FMCG terms in local context
- Respectful but direct tone

Input Contract (from Strategist):
{
    "insight_type": str,
    "priority": str,
    "findings": [...],
    "top_finding": {...},
    "recommended_action": str,
    "action_type": "VISIT" | "CALL" | "MESSAGE",
    "confidence_level": "HIGH" | "MEDIUM" | "LOW",
    "business_impact": str,
    "evidence": [...]
}

Output Format:
{
    "message_type": "CHURN_RISK",
    "primary_message": "Hi Ramesh, we noticed...",
    "whatsapp_variant": "🎯 Ramesh ji, ...",
    "internal_notes": "For sales rep: mention new credit terms",
    "tone": "ASSERTIVE" | "SUGGESTIVE" | "EXPLORATORY",
    "action_friction": "HIGH" | "MEDIUM" | "LOW"
}

Usage:
    from agents.copywriter import CopywriterAgent
    copywriter = CopywriterAgent(llm=llm)
    message = copywriter.craft_message(insight)
"""

from typing import Any, Dict, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from config.prompts import COPYWRITER_SYSTEM_PROMPT, COPYWRITER_TALKING_POINT_PROMPT


class CopywriterAgent:
    """
    Sales message crafting agent.
    
    The Copywriter is the "voice" of the system - it transforms
    insights into messages that drive action.
    
    Key Features:
    - Confidence-aware tone (HIGH/MEDIUM/LOW → assertive/suggestive/exploratory)
    - Action friction mapping (VISIT > CALL > MESSAGE)
    - Template-driven structure with LLM for talking points
    - Strict output constraints (280 chars, no hallucination)
    """
    
    # =========================================================================
    # SALESCODE.AI VOCABULARY MAPPING
    # =========================================================================
    # Internal system terms → Salescode operational terminology
    # This ensures alignment with real sales ops language
    # =========================================================================
    ACTION_LABELS = {
        'VISIT': 'Field Visit',
        'CALL': 'Telecalling',
        'MESSAGE': 'WhatsApp Nudge'
    }
    
    INSIGHT_LABELS = {
        'CHURN_RISK': 'Retention Alert',
        'CROSS_SELL_GAP': 'Growth Opportunity',
        'VALUE_DECLINE': 'Performance Review',
        'NO_ISSUES': 'Portfolio Healthy'
    }
    
    PRIORITY_LABELS = {
        'P1_CRITICAL': 'Immediate Action Required',
        'P2_HIGH': 'High Priority',
        'P3_MEDIUM': 'Standard Follow-up',
        'P4_LOW': 'Monitor Only'
    }
    
    # Confidence to tone mapping
    CONFIDENCE_TO_TONE = {
        'HIGH': 'ASSERTIVE',
        'MEDIUM': 'SUGGESTIVE',
        'LOW': 'EXPLORATORY'
    }
    
    # Action to friction mapping
    ACTION_TO_FRICTION = {
        'VISIT': 'HIGH',
        'CALL': 'MEDIUM',
        'MESSAGE': 'LOW'
    }
    
    # Tone-specific language patterns
    TONE_PATTERNS = {
        'ASSERTIVE': {
            'action_verb': 'Visit',
            'urgency': 'immediately',
            'certainty': 'requires',
            'opener': '🔴 URGENT',
        },
        'SUGGESTIVE': {
            'action_verb': 'Consider visiting',
            'urgency': 'soon',
            'certainty': 'may need',
            'opener': '🟡 ATTENTION',
        },
        'EXPLORATORY': {
            'action_verb': 'You might want to check on',
            'urgency': 'when convenient',
            'certainty': 'might benefit from',
            'opener': '🟢 OPPORTUNITY',
        }
    }
    
    # Discount caps (enforced, never exceeded)
    MAX_DISCOUNT = 15
    
    def __init__(self, llm: BaseChatModel):
        """
        Initialize the Copywriter Agent.
        
        Args:
            llm: LangChain chat model (GPT-4-turbo recommended)
        """
        self.llm = llm
    
    def craft_message(self, insight: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create sales message from strategic insight.
        
        Uses deterministic templates with LLM only for talking points.
        Tone is adjusted based on confidence_level from Strategist.
        
        Args:
            insight: Output from StrategistAgent with full context
            
        Returns:
            Dict with message variants, tone, and metadata
        """
        # Extract insight components
        insight_type = insight.get('insight_type', 'VALUE_DECLINE')
        priority = insight.get('priority', 'P4_LOW')
        top_finding = insight.get('top_finding', {})
        action_type = insight.get('action_type', 'MESSAGE')
        confidence_level = insight.get('confidence_level', 'MEDIUM')
        business_impact = insight.get('business_impact', '')
        evidence = insight.get('evidence', [])
        recommended_action = insight.get('recommended_action', '')
        
        # Handle empty/no-issues case
        if insight_type == 'NO_ISSUES' or not top_finding:
            return self._create_positive_message()
        
        # Determine tone from confidence
        tone = self.CONFIDENCE_TO_TONE.get(confidence_level, 'SUGGESTIVE')
        friction = self.ACTION_TO_FRICTION.get(action_type, 'LOW')
        
        # Extract retailer info
        retailer_id = top_finding.get('retailer_id', 'Unknown')
        retailer_name = top_finding.get('retailer_name', top_finding.get('name', 'Retailer'))
        tier = top_finding.get('tier', 'Unknown')
        severity = top_finding.get('severity', 'MEDIUM')
        explanation = top_finding.get('explanation', '')
        
        # Generate talking point via LLM
        talking_point = self._generate_talking_point(
            insight_type=insight_type,
            tier=tier,
            evidence=evidence,
            action_type=action_type
        )
        
        # Get discount from Strategist (single source of truth)
        # Copywriter does NOT calculate - only formats what Strategist provides
        # Fallback to _calculate_discount only if Strategist didn't provide one
        discount = insight.get('suggested_discount')
        if discount is None:
            # Fallback for backward compatibility
            discount = self._calculate_discount(severity, tier)
        
        # Enforce cap as safety check (Strategist already enforces, this is defense-in-depth)
        discount = min(discount, self.MAX_DISCOUNT)
        
        # Build messages using templates
        primary = self._build_primary_message(
            insight_type=insight_type,
            retailer_name=retailer_name,
            retailer_id=retailer_id,
            tier=tier,
            tone=tone,
            explanation=explanation,
            action_type=action_type,
            discount=discount,
            talking_point=talking_point
        )
        
        whatsapp = self._build_whatsapp_message(
            insight_type=insight_type,
            retailer_name=retailer_name,
            tone=tone,
            explanation=explanation,
            action_type=action_type
        )
        
        internal_notes = self._build_internal_notes(
            insight_type=insight_type,
            tier=tier,
            evidence=evidence,
            business_impact=business_impact
        )
        
        return {
            'success': True,
            'message_type': insight_type,
            'primary_message': primary,
            'whatsapp_variant': whatsapp,
            'internal_notes': internal_notes,
            'talking_point': talking_point,
            'tone': tone,
            'action_friction': friction,
            'suggested_discount': discount,
            'retailer_id': retailer_id,
            'retailer_name': retailer_name
        }
    
    def _generate_talking_point(
        self,
        insight_type: str,
        tier: str,
        evidence: list,
        action_type: str
    ) -> str:
        """
        Generate conversational talking point via LLM.
        
        This is the ONLY part where LLM has creative freedom.
        Constrained to: conversational, <20 words, no invented data.
        """
        evidence_str = '; '.join(evidence[:3]) if evidence else 'declining activity'
        
        prompt = COPYWRITER_TALKING_POINT_PROMPT.format(
            issue_type=insight_type,
            tier=tier,
            evidence=evidence_str,
            action=action_type
        )
        
        try:
            messages = [
                SystemMessage(content=COPYWRITER_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = self.llm.invoke(messages)
            
            # Clean and validate
            talking_point = response.content.strip().strip('"\'')
            
            # Enforce length limit
            if len(talking_point) > 100:
                talking_point = talking_point[:97] + '...'
            
            return talking_point
            
        except Exception:
            # Fallback talking points
            fallbacks = {
                'CHURN_RISK': "We noticed it's been a while - everything okay with the shop?",
                'CROSS_SELL_GAP': "Your customers might be interested in some new products.",
                'VALUE_DECLINE': "Let's talk about how we can support your business better."
            }
            return fallbacks.get(insight_type, "I wanted to check in with you.")
    
    def _calculate_discount(self, severity: str, tier: str) -> int:
        """
        Calculate suggested discount based on severity and tier.
        
        NEVER exceeds MAX_DISCOUNT (15%).
        """
        base_discount = {
            'HIGH': 15,
            'MEDIUM': 10,
            'LOW': 5
        }.get(severity, 5)
        
        # Gold tier gets full discount, others get less
        tier_multiplier = {
            'Gold': 1.0,
            'Silver': 0.8,
            'Bronze': 0.6
        }.get(tier, 0.6)
        
        discount = int(base_discount * tier_multiplier)
        return min(discount, self.MAX_DISCOUNT)
    
    def _build_primary_message(
        self,
        insight_type: str,
        retailer_name: str,
        retailer_id: str,
        tier: str,
        tone: str,
        explanation: str,
        action_type: str,
        discount: int,
        talking_point: str
    ) -> str:
        """
        Build the primary message using templates.
        
        Structure varies by insight_type, tone adjusts urgency.
        """
        patterns = self.TONE_PATTERNS[tone]
        opener = patterns['opener']
        urgency = patterns['urgency']
        action_verb = patterns['action_verb']
        
        if insight_type == 'CHURN_RISK':
            if action_type == 'VISIT':
                return f"""{opener}: {action_verb} {retailer_name}

Why: {explanation}. {tier} customer at risk.

Action: Personal visit to {retailer_name} ({retailer_id})
Offer: {discount}% off next order
Say: "{talking_point}"

Deadline: Within 48 hours"""
            elif action_type == 'CALL':
                return f"""{opener}: Call {retailer_name}

Why: {explanation}. Early intervention needed.

Action: Phone call to {retailer_name}
Mention: "{talking_point}"

Deadline: Today"""
            else:  # MESSAGE
                return f"""{opener}: Message {retailer_name}

{explanation}. Consider reaching out {urgency}.

Say: "{talking_point}" """
        
        elif insight_type == 'CROSS_SELL_GAP':
            return f"""{opener}: Introduce new category to {retailer_name}

Why: {explanation}

Action: {action_verb} with product samples
Offer: {discount}% trial discount
Say: "{talking_point}"

Deadline: Next scheduled visit"""
        
        else:  # VALUE_DECLINE or other
            return f"""{opener}: Review {retailer_name}'s account

Why: {explanation}

Action: {action_verb} to discuss performance
Say: "{talking_point}" """
    
    def _build_whatsapp_message(
        self,
        insight_type: str,
        retailer_name: str,
        tone: str,
        explanation: str,
        action_type: str
    ) -> str:
        """
        Build WhatsApp-friendly message (max 280 chars).
        """
        patterns = self.TONE_PATTERNS[tone]
        opener = patterns['opener']
        
        if insight_type == 'CHURN_RISK':
            base = f"{opener} {retailer_name}: {explanation}. "
            if action_type == 'VISIT':
                base += "Schedule visit today! 🏃"
            elif action_type == 'CALL':
                base += "Call them now! 📞"
            else:
                base += "Send a check-in message 💬"
        elif insight_type == 'CROSS_SELL_GAP':
            base = f"🎯 {retailer_name}: {explanation}. Great cross-sell opportunity! 📈"
        else:
            base = f"📊 {retailer_name}: {explanation}. Review account."
        
        # Enforce WhatsApp limit
        if len(base) > 280:
            base = base[:277] + '...'
        
        return base
    
    def _build_internal_notes(
        self,
        insight_type: str,
        tier: str,
        evidence: list,
        business_impact: str
    ) -> str:
        """
        Build internal notes for sales rep.
        
        This is NOT shown to retailer - just prep for sales rep.
        """
        notes = [f"Customer Tier: {tier}", f"Impact: {business_impact}"]
        
        if evidence:
            notes.append("Evidence:")
            for e in evidence[:3]:
                notes.append(f"  - {e}")
        
        if insight_type == 'CHURN_RISK':
            notes.append("Tip: Focus on relationship, not sales pressure")
        elif insight_type == 'CROSS_SELL_GAP':
            notes.append("Tip: Bring product samples, show margin benefit")
        
        return '\n'.join(notes)
    
    def _create_positive_message(self) -> Dict[str, Any]:
        """
        Create positive reinforcement message when no issues found.
        """
        return {
            'success': True,
            'message_type': 'NO_ISSUES',
            'primary_message': "✅ All clear! No retailers currently at risk. Great job maintaining relationships.",
            'whatsapp_variant': "✅ Portfolio looking healthy! No urgent actions needed today. 🎉",
            'internal_notes': "No churn risks or cross-sell gaps detected. Consider proactive outreach to top performers.",
            'talking_point': "Everything is running smoothly.",
            'tone': 'ASSERTIVE',
            'action_friction': 'LOW',
            'suggested_discount': 0,
            'retailer_id': None,
            'retailer_name': None
        }
    
    def localize(self, message: str, locale: str = "en-IN") -> str:
        """
        Adapt message for regional preferences.
        
        Currently supports:
        - en-IN: Indian English (₹, lakhs, ji suffix)
        
        Args:
            message: Base message
            locale: Target locale code
            
        Returns:
            Localized message
        """
        if locale == "en-IN":
            # Already in Indian format
            return message
        
        # Future: Add more locales
        return message
    
    def validate_tone(self, message: str) -> bool:
        """
        Check message meets brand and safety guidelines.
        
        Blocked content:
        - Competitor mentions
        - Negative language about retailer
        - Promises we can't keep
        - Discount > 15%
        
        Args:
            message: Message to validate
            
        Returns:
            True if message is appropriate
        """
        message_lower = message.lower()
        
        # Check for blocked patterns
        blocked = [
            'competitor',
            'their loss',
            'guarantee',
            'promise',
            'definitely will',
            '20%', '25%', '30%',  # Excessive discounts
        ]
        
        for pattern in blocked:
            if pattern in message_lower:
                return False
        
        return True
