"""
Centralized Application Configuration

Responsibility:
- Load environment variables from .env file
- Provide typed, validated configuration values
- Define all tunable parameters in one place
- Ensure consistent defaults across the application

Explicitly NOT responsible for:
- Business logic
- Runtime state management
- Secrets rotation (handled externally)

Usage:
    from config.settings import Settings
    settings = Settings()
    print(settings.LLM_MODEL)

All configuration should flow through this module.
Nothing else should read from os.environ directly.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes are grouped by concern:
    - LLM: Language model configuration
    - Data: Synthetic data generation parameters
    - Business: Domain-specific rules and thresholds
    - UI: User interface settings
    """
    
    # =========================================================================
    # LLM Configuration
    # =========================================================================
    OPENAI_API_KEY: str = Field(
        ...,  # Required
        description="OpenAI API key for LLM calls"
    )
    
    LLM_MODEL: str = Field(
        default="gpt-4-turbo",
        description="OpenAI model to use for all agents"
    )
    
    LLM_TEMPERATURE: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature (lower = more deterministic)"
    )
    
    LLM_MAX_TOKENS: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Maximum tokens in LLM response"
    )
    
    LLM_TIMEOUT: int = Field(
        default=30,
        description="Timeout for LLM API calls in seconds"
    )
    
    # =========================================================================
    # Data Generation Configuration
    # =========================================================================
    NUM_RETAILERS: int = Field(
        default=500,
        ge=50,
        le=5000,
        description="Number of retailers to generate"
    )
    
    NUM_PRODUCTS: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Number of products in catalog"
    )
    
    DAYS_OF_HISTORY: int = Field(
        default=90,
        ge=30,
        le=365,
        description="Days of transaction history to generate"
    )
    
    RANDOM_SEED: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducible data generation"
    )
    
    NUM_BEATS: int = Field(
        default=10,
        ge=2,
        le=50,
        description="Number of geographic beats/routes"
    )
    
    # Anomaly injection rates
    CHURN_PERCENTAGE: float = Field(
        default=0.12,
        ge=0.0,
        le=0.5,
        description="Percentage of retailers with churn pattern"
    )
    
    CROSSSELL_GAP_PERCENTAGE: float = Field(
        default=0.15,
        ge=0.0,
        le=0.5,
        description="Percentage of retailers with cross-sell gaps"
    )
    
    # Tier distribution (must sum to 1.0)
    GOLD_TIER_PERCENTAGE: float = Field(
        default=0.10,
        description="Percentage of Gold tier retailers"
    )
    
    SILVER_TIER_PERCENTAGE: float = Field(
        default=0.30,
        description="Percentage of Silver tier retailers"
    )
    
    BRONZE_TIER_PERCENTAGE: float = Field(
        default=0.60,
        description="Percentage of Bronze tier retailers"
    )
    
    @property
    def TIER_DISTRIBUTION(self) -> dict:
        """Computed property for tier distribution."""
        return {
            "Gold": self.GOLD_TIER_PERCENTAGE,
            "Silver": self.SILVER_TIER_PERCENTAGE,
            "Bronze": self.BRONZE_TIER_PERCENTAGE,
        }
    
    # =========================================================================
    # Business Rules Configuration
    # =========================================================================
    MAX_DISCOUNT_PERCENT: int = Field(
        default=15,
        ge=0,
        le=50,
        description="Maximum discount AI can recommend"
    )
    
    CHURN_THRESHOLD_DAYS: int = Field(
        default=14,
        ge=7,
        le=60,
        description="Days without order to consider potential churn"
    )
    
    FREQUENCY_DECLINE_HIGH: float = Field(
        default=0.30,
        ge=0.1,
        le=0.9,
        description="Frequency decline threshold for HIGH risk (30%)"
    )
    
    FREQUENCY_DECLINE_MEDIUM: float = Field(
        default=0.15,
        ge=0.05,
        le=0.5,
        description="Frequency decline threshold for MEDIUM risk (15%)"
    )
    
    CROSS_SELL_AFFINITY_THRESHOLD: float = Field(
        default=0.5,
        ge=0.1,
        le=0.9,
        description="Minimum category affinity to flag cross-sell opportunity"
    )
    
    MIN_PURCHASES_FOR_CROSSSELL: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Minimum purchases in category A to flag category B gap"
    )
    
    # =========================================================================
    # UI Configuration
    # =========================================================================
    MAX_ACTION_CARDS: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum action cards to display"
    )
    
    PROCESSING_TIMEOUT: int = Field(
        default=60,
        description="Maximum seconds for full pipeline execution"
    )
    
    # =========================================================================
    # Database Configuration
    # =========================================================================
    DATABASE_PATH: Optional[str] = Field(
        default=None,
        description="Path to DuckDB file (None = in-memory)"
    )
    
    # =========================================================================
    # Pydantic Settings Configuration
    # =========================================================================
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars


# =============================================================================
# Convenience Functions
# =============================================================================

def get_settings() -> Settings:
    """
    Factory function to get settings instance.
    Useful for dependency injection in tests.
    """
    return Settings()


def validate_settings(settings: Settings) -> bool:
    """
    Validate that settings are internally consistent.
    
    Returns True if valid, raises ValueError otherwise.
    """
    # Tier percentages must sum to 1.0
    tier_sum = (
        settings.GOLD_TIER_PERCENTAGE + 
        settings.SILVER_TIER_PERCENTAGE + 
        settings.BRONZE_TIER_PERCENTAGE
    )
    if abs(tier_sum - 1.0) > 0.01:
        raise ValueError(
            f"Tier percentages must sum to 1.0, got {tier_sum}"
        )
    
    # High threshold must be greater than medium
    if settings.FREQUENCY_DECLINE_HIGH <= settings.FREQUENCY_DECLINE_MEDIUM:
        raise ValueError(
            "FREQUENCY_DECLINE_HIGH must be greater than FREQUENCY_DECLINE_MEDIUM"
        )
    
    return True


# =============================================================================
# Singleton Instance
# =============================================================================
# Use this for importing: from config.settings import settings
settings = Settings()
