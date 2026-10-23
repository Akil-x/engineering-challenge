"""
Core G2 Gate Evaluator: Hard checks, freshness assessment, criterion scoring, and decision routing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .models import (
    CaseMetadata,
    CriterionScores,
    EvaluationReport,
    EvidenceCase,
    FreshnessAssessment,
    GateDecision,
    HardCheckResult,
    PolicyConfig,
)
from .guardrails import scan_for_instruction_injection

AUTHORITY_ANCHORS: dict[str, float] = {
    "primary_authority": 1.0,
    "secondary_authority": 0.7,
    "user_generated": 0.4,
    "competitor": 0.2,
}

RELIABILITY_ANCHORS: dict[str, float] = {
    "regulation": 1.0,
    "official_report": 0.85,
    "news": 0.60,
    "blog": 0.30,
}


class G2Evaluator:
    """
    Deterministic evaluation engine for the G2 Content-Quality Gate.
    """

    def __init__(self, config: Optional[PolicyConfig] = None):
        self.config = config or PolicyConfig()

    def parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """
        Safely parses ISO date string (YYYY-MM-DD).
        """
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def run_hard_checks(
        self, case: EvidenceCase, injection_tags: list[str]
    ) -> HardCheckResult:
        """
        Evaluates mandatory hard floors before scoring.
        """
        failures: list[str] = []

        no_injection = len(injection_tags) == 0
        if not no_injection:
            failures.append("instruction_injection_detected")

        no_competitor = not bool(case.metadata.competitor_product_claim)
        if not no_competitor:
            failures.append("competitor_product_promotion")

        supported = case.metadata.supported is not False
        if not supported:
            failures.append("unsupported_claim")

        not_superseded = not bool(
            case.metadata.superseded or case.metadata.current_status == "superseded"
        )
        if not_superseded is False:
            failures.append("superseded_evidence")

        no_contradiction = not bool(case.metadata.contradiction)
        if not no_contradiction:
            failures.append("conflicting_evidence")

        passed = len(failures) == 0

        return HardCheckResult(
            passed=passed,
            material_claim_supported=supported,
            evidence_not_superseded=not_superseded,
            no_competitor_promotion=no_competitor,
            no_contradiction=no_contradiction,
            no_injection_detected=no_injection,
            failures=failures,
        )

    def assess_freshness_and_validity(
        self, case: EvidenceCase, reference_date: date
    ) -> tuple[FreshnessAssessment, Optional[float], Optional[float]]:
        """
        Evaluates temporal freshness and current applicability without conflating publication date.
        """
        metadata = case.metadata
        content_type = (metadata.content_type or "").lower()
        ref_str = reference_date.isoformat()

        # Rule 1: Regulation handling
        if content_type == "regulation":
            status = (metadata.current_status or "").lower()
            effective_date = self.parse_date(metadata.effective_from)

            if status == "adopted_not_applicable":
                # Adopted future rule
                statement = (case.statement or "").lower()
                is_future = effective_date and effective_date > reference_date
                statement_clarifies_future = any(
                    kw in statement for kw in ["will apply", "not today", "from", "future", "adopted"]
                )
                if is_future and statement_clarifies_future:
                    return (
                        FreshnessAssessment(
                            status="future_rule_valid",
                            reference_date=ref_str,
                            evaluated_date=metadata.effective_from,
                            evaluated_date_type="effective_from",
                            age_days=(effective_date - reference_date).days if effective_date else None,
                            reason=f"Regulation adopted with future effective date ({metadata.effective_from}); statement accurately indicates future applicability.",
                        ),
                        1.0,
                        0.8,
                    )

            if status == "current":
                return (
                    FreshnessAssessment(
                        status="current",
                        reference_date=ref_str,
                        evaluated_date=metadata.effective_from or metadata.published_at,
                        evaluated_date_type="effective_from" if metadata.effective_from else "published_at",
                        age_days=0,
                        reason="Regulation is currently in force; not penalized for historical enactment date.",
                    ),
                    1.0,
                    1.0,
                )

            if status == "superseded":
                return (
                    FreshnessAssessment(
                        status="superseded",
                        reference_date=ref_str,
                        evaluated_date=metadata.effective_from or metadata.published_at,
                        evaluated_date_type="effective_from",
                        age_days=None,
                        reason="Regulation is superseded by newer legislation.",
                    ),
                    0.0,
                    0.0,
                )

            if status == "repealed":
                return (
                    FreshnessAssessment(
                        status="repealed",
                        reference_date=ref_str,
                        evaluated_date=metadata.published_at,
                        evaluated_date_type="published_at",
                        age_days=None,
                        reason="Regulation has been repealed and is no longer applicable.",
                    ),
                    0.0,
                    0.0,
                )

            if status == "draft":
                return (
                    FreshnessAssessment(
                        status="draft",
                        reference_date=ref_str,
                        evaluated_date=metadata.published_at,
                        evaluated_date_type="published_at",
                        age_days=None,
                        reason="Regulation is in draft state and not yet legally binding.",
                    ),
                    0.7,
                    0.4,
                )

            return (
                FreshnessAssessment(
                    status="unknown_status",
                    reference_date=ref_str,
                    evaluated_date=None,
                    evaluated_date_type=None,
                    age_days=None,
                    reason=f"Unrecognized regulation status: '{metadata.current_status}'.",
                ),
                None,
                None,
            )

        # Rule 2: News and general content (demo freshness policy)
        event_date = self.parse_date(metadata.event_date)
        if event_date is None:
            return (
                FreshnessAssessment(
                    status="unknown",
                    reference_date=ref_str,
                    evaluated_date=None,
                    evaluated_date_type=None,
                    age_days=None,
                    reason="Event date unavailable for temporal verification under demo policy.",
                ),
                None,
                None,
            )

        age_days = (reference_date - event_date).days
        if age_days < 0:
            return (
                FreshnessAssessment(
                    status="future_event",
                    reference_date=ref_str,
                    evaluated_date=metadata.event_date,
                    evaluated_date_type="event_date",
                    age_days=age_days,
                    reason=f"Event date is in the future ({abs(age_days)} days ahead).",
                ),
                0.8,
                0.8,
            )

        if age_days <= self.config.news_max_event_age_days:
            return (
                FreshnessAssessment(
                    status="current",
                    reference_date=ref_str,
                    evaluated_date=metadata.event_date,
                    evaluated_date_type="event_date",
                    age_days=age_days,
                    reason=f"Event falls within the configured demonstration freshness policy ({age_days} days <= {self.config.news_max_event_age_days} days).",
                ),
                1.0,
                1.0,
            )

        # Stale event
        if age_days <= 90:
            freshness_score = 0.7
        elif age_days <= 180:
            freshness_score = 0.4
        else:
            freshness_score = 0.1

        return (
            FreshnessAssessment(
                status="stale",
                reference_date=ref_str,
                evaluated_date=metadata.event_date,
                evaluated_date_type="event_date",
                age_days=age_days,
                reason=f"News event is {age_days} days old, exceeding maximum freshness threshold ({self.config.news_max_event_age_days} days).",
            ),
            freshness_score,
            0.3,
        )

    def compute_criterion_scores(
        self,
        case: EvidenceCase,
        freshness_score: Optional[float],
        temporal_validity_score: Optional[float],
    ) -> CriterionScores:
        """
        Maps case attributes to normalized 0.0 - 1.0 criteria scores.
        """
        source_key = (case.metadata.source_type or "").lower()
        authority_score = AUTHORITY_ANCHORS.get(source_key, 0.4)

        content_key = (case.metadata.content_type or "").lower()
        reliability_score = RELIABILITY_ANCHORS.get(content_key, 0.4)

        evidence_support_score = (
            1.0 if case.metadata.supported is True
            else 0.0 if case.metadata.supported is False
            else None
        )

        return CriterionScores(
            authority_score=authority_score,
            reliability_score=reliability_score,
            freshness_score=freshness_score,
            temporal_validity_score=temporal_validity_score,
            evidence_support_score=evidence_support_score,
        )

    def compute_weighted_score(
        self, criteria: CriterionScores, weights: Optional[dict[str, float]] = None
    ) -> Optional[float]:
        """
        Computes the transparent weighted sum. Returns None if any required criterion is unknown.
        """
        active_weights = weights or self.config.weights
        req_scores = [
            criteria.authority_score,
            criteria.reliability_score,
            criteria.freshness_score,
            criteria.temporal_validity_score,
        ]

        # Do not silently convert unknown to 0.0
        if any(s is None for s in req_scores):
            return None

        score = (
            active_weights["authority"] * criteria.authority_score
            + active_weights["reliability"] * criteria.reliability_score
            + active_weights["freshness"] * criteria.freshness_score
            + active_weights["temporal_validity"] * criteria.temporal_validity_score
        )
        return round(score, 4)

    def evaluate(
        self, case: EvidenceCase, reference_date: date
    ) -> EvaluationReport:
        """
        Executes full G2 evaluation for a validated evidence case.
        """
        audit_trace: list[str] = []
        reasons: list[str] = []

        # 1. Injection scan
        scan_text = f"{case.statement} {case.metadata.source_type} {case.metadata.content_type}"
        injection_tags = scan_for_instruction_injection(scan_text)
        if injection_tags:
            audit_trace.append(f"Security: instruction injection detected: {injection_tags}")
        else:
            audit_trace.append("Security: clean input scan, no instruction injection detected")

        # 2. Hard checks
        hard_checks = self.run_hard_checks(case, injection_tags)
        audit_trace.append(f"Hard checks passed: {hard_checks.passed}")

        # 3. Freshness and validity
        freshness, fresh_score, temp_score = self.assess_freshness_and_validity(
            case, reference_date
        )
        audit_trace.append(f"Freshness evaluated: status={freshness.status}, reason={freshness.reason}")

        # 4. Criterion scores & weighted score
        criteria = self.compute_criterion_scores(case, fresh_score, temp_score)
        weighted_score = self.compute_weighted_score(criteria)
        audit_trace.append(f"Criterion scoring: {criteria}, weighted_score={weighted_score}")

        # 5. Decision routing according to strict precedence:
        # Precedence 1: Reject
        if "instruction_injection_detected" in hard_checks.failures:
            decision = GateDecision.REJECT
            reasons.append("instruction_injection_detected")
        elif "competitor_product_promotion" in hard_checks.failures:
            decision = GateDecision.REJECT
            reasons.append("competitor_product_promotion")
        # Precedence 2: Revise
        elif "unsupported_claim" in hard_checks.failures:
            decision = GateDecision.REVISE
            reasons.append("unsupported_claim")
        elif "superseded_evidence" in hard_checks.failures:
            decision = GateDecision.REVISE
            reasons.append("superseded_evidence")
        elif freshness.status == "stale":
            decision = GateDecision.REVISE
            reasons.append("stale_news_event")
        # Precedence 3: Human Review
        elif "conflicting_evidence" in hard_checks.failures:
            decision = GateDecision.HUMAN_REVIEW
            reasons.append("conflicting_evidence")
        elif weighted_score is None:
            decision = GateDecision.HUMAN_REVIEW
            reasons.append("unknown_required_criterion")
            if freshness.status == "unknown":
                reasons.append("unknown_event_date")
        # Threshold-based routing when hard checks pass and criteria are known
        elif weighted_score >= self.config.passing_threshold:
            decision = GateDecision.PASS
            reasons.append("all_mandatory_checks_passed")
            reasons.append("prototype_threshold_met")
        elif weighted_score >= self.config.human_review_threshold:
            decision = GateDecision.HUMAN_REVIEW
            reasons.append("score_in_human_review_range")
        else:
            decision = GateDecision.REVISE
            reasons.append("score_below_revision_threshold")

        audit_trace.append(f"Decision resolved: {decision.value} (reasons={reasons})")

        return EvaluationReport(
            case_id=case.id,
            gate="G2",
            policy_version=self.config.policy_version,
            weights_version=self.config.weights_version,
            calibration_status=self.config.calibration_status,
            decision=decision,
            weighted_score=weighted_score,
            hard_checks=hard_checks,
            freshness=freshness,
            criteria=criteria,
            weights=self.config.weights,
            reasons=reasons,
            audit_trace=audit_trace,
        )
