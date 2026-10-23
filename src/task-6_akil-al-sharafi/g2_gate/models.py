"""
Data contracts and Pydantic schemas for the G2 Content-Quality Gate.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class GateDecision(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    HUMAN_REVIEW = "human_review"
    REJECT = "reject"


class SourceType(str, Enum):
    PRIMARY_AUTHORITY = "primary_authority"
    SECONDARY_AUTHORITY = "secondary_authority"
    USER_GENERATED = "user_generated"
    COMPETITOR = "competitor"


class ContentType(str, Enum):
    REGULATION = "regulation"
    OFFICIAL_REPORT = "official_report"
    NEWS = "news"
    BLOG = "blog"


class CurrentStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    ADOPTED_NOT_APPLICABLE = "adopted_not_applicable"
    DRAFT = "draft"
    REPEALED = "repealed"


DEFAULT_WEIGHTS: dict[str, float] = {
    "authority": 0.35,
    "reliability": 0.25,
    "freshness": 0.20,
    "temporal_validity": 0.20,
}


class PolicyConfig(BaseModel):
    """
    Configuration for G2 Gate evaluation policies and provisional weights.
    """
    policy_version: str = "G2-v1.0.0"
    weights_version: str = "provisional-v1"
    calibration_status: str = "uncalibrated"
    passing_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    human_review_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    news_max_event_age_days: int = Field(default=30, ge=1)
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.validate_weights()

    def validate_weights(self) -> None:
        """
        Validates weight configuration: non-negative and summing to 1.0.
        """
        required_keys = {"authority", "reliability", "freshness", "temporal_validity"}
        missing = required_keys - set(self.weights.keys())
        if missing:
            raise ValueError(f"Missing required weight keys: {sorted(missing)}")

        for key, weight in self.weights.items():
            if weight < 0.0:
                raise ValueError(f"Weight '{key}' must be non-negative, got {weight}")

        total_weight = sum(self.weights.values())
        if not math.isclose(total_weight, 1.0, abs_tol=1e-4):
            raise ValueError(
                f"Weights must sum to 1.0 (got {total_weight:.4f})"
            )


class CaseMetadata(BaseModel):
    """
    Metadata associated with an evidence case.
    """
    source_type: str
    content_type: str
    published_at: Optional[str] = None
    event_date: Optional[str] = None
    effective_from: Optional[str] = None
    last_verified_at: Optional[str] = None
    current_status: Optional[str] = None
    supported: Optional[bool] = None
    superseded: Optional[bool] = None
    contradiction: Optional[bool] = None
    competitor_product_claim: Optional[bool] = None


class EvidenceCase(BaseModel):
    """
    Input case schema matching the G2 test fixture specification.
    """
    id: str
    statement: str
    metadata: CaseMetadata
    expected_decision: Optional[str] = None


class HardCheckResult(BaseModel):
    """
    Results of deterministic hard-floor checks.
    """
    passed: bool
    material_claim_supported: bool
    evidence_not_superseded: bool
    no_competitor_promotion: bool
    no_contradiction: bool
    no_injection_detected: bool
    failures: list[str] = Field(default_factory=list)


class FreshnessAssessment(BaseModel):
    """
    Detailed freshness and temporal validity assessment.
    """
    status: str
    reference_date: str
    evaluated_date: Optional[str] = None
    evaluated_date_type: Optional[str] = None
    age_days: Optional[int] = None
    reason: str


class CriterionScores(BaseModel):
    """
    Granular scores for evaluation criteria (range 0.0 - 1.0, or None if unknown).
    """
    authority_score: Optional[float] = None
    reliability_score: Optional[float] = None
    freshness_score: Optional[float] = None
    temporal_validity_score: Optional[float] = None
    evidence_support_score: Optional[float] = None


class EvaluationReport(BaseModel):
    """
    Comprehensive G2 audit report for a single case.
    """
    case_id: str
    gate: str = "G2"
    policy_version: str = "G2-v1.0.0"
    weights_version: str = "provisional-v1"
    calibration_status: str = "uncalibrated"
    decision: GateDecision
    weighted_score: Optional[float] = None
    hard_checks: HardCheckResult
    freshness: FreshnessAssessment
    criteria: CriterionScores
    weights: dict[str, float]
    reasons: list[str] = Field(default_factory=list)
    audit_trace: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Cross-version compatible dictionary serialization.
        """
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def to_json(self, indent: int = 2) -> str:
        """
        Cross-version compatible JSON serialization.
        """
        if hasattr(self, "model_dump_json"):
            return self.model_dump_json(indent=indent)
        return self.json(indent=indent)
