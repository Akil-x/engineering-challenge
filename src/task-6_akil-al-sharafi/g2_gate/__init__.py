"""
G2 Content-Quality Gate package for evidence and current-validity assessment.
"""

from .models import (
    PolicyConfig,
    CaseMetadata,
    EvidenceCase,
    HardCheckResult,
    FreshnessAssessment,
    CriterionScores,
    EvaluationReport,
    GateDecision,
)
from .guardrails import scan_for_instruction_injection
from .evaluator import G2Evaluator

__all__ = [
    "PolicyConfig",
    "CaseMetadata",
    "EvidenceCase",
    "HardCheckResult",
    "FreshnessAssessment",
    "CriterionScores",
    "EvaluationReport",
    "GateDecision",
    "scan_for_instruction_injection",
    "G2Evaluator",
]
