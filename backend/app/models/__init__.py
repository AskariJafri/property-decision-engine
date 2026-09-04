"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.analysis import (
    AiJudgement,
    AiReport,
    AnalysisFactor,
    AnalysisJudgement,
    AnalysisScore,
    CalculationTrace,
    ComparableScore,
    FinancialScenario,
    PropertyAnalysis,
    PropertyComparison,
    RiskFlag,
)
from app.models.base import Base
from app.models.property import (
    Comparable,
    Location,
    LocationMetric,
    Property,
    PropertyAttribute,
    PropertyPriceHistory,
    PropertySource,
    SavedProperty,
)
from app.models.provenance import (
    DataProvenance,
    DataSource,
    MarketSnapshot,
    Rule,
    RuleSet,
)
from app.models.user import AuditLog, BuyerPreferences, FinancialProfile, User, UserProfile

__all__ = [
    "AiJudgement",
    "AiReport",
    "AnalysisFactor",
    "AnalysisJudgement",
    "AnalysisScore",
    "AuditLog",
    "Base",
    "BuyerPreferences",
    "CalculationTrace",
    "Comparable",
    "ComparableScore",
    "DataProvenance",
    "DataSource",
    "FinancialProfile",
    "FinancialScenario",
    "Location",
    "LocationMetric",
    "MarketSnapshot",
    "Property",
    "PropertyAnalysis",
    "PropertyAttribute",
    "PropertyComparison",
    "PropertyPriceHistory",
    "PropertySource",
    "RiskFlag",
    "Rule",
    "RuleSet",
    "SavedProperty",
    "User",
    "UserProfile",
]
