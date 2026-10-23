"""
Workflow orchestrator, Human-in-the-Loop routing, and sensitivity analysis pipeline.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from .evaluator import G2Evaluator
from .models import (
    CriterionScores,
    EvaluationReport,
    EvidenceCase,
    FreshnessAssessment,
    GateDecision,
    HardCheckResult,
    PolicyConfig,
)

DEFAULT_AS_OF_DATE = date(2026, 10, 6)


def parse_reference_date(val: Any) -> date:
    """
    Parses a reference date from string or date object, defaulting to 2026-10-06.
    """
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass
    return DEFAULT_AS_OF_DATE


def evaluate_case(
    raw_case: dict[str, Any] | EvidenceCase,
    reference_date: Optional[date | str] = None,
    config: Optional[PolicyConfig] = None,
) -> EvaluationReport:
    """
    Evaluates a single evidence case through the full G2 gate pipeline.
    Catches validation errors gracefully and converts them to structured reject reports.
    """
    active_config = config or PolicyConfig()
    ref_date = parse_reference_date(reference_date)

    # Stage 1: Pydantic Schema Validation
    if isinstance(raw_case, EvidenceCase):
        case = raw_case
    else:
        try:
            if hasattr(EvidenceCase, "model_validate"):
                case = EvidenceCase.model_validate(raw_case)
            else:
                case = EvidenceCase.parse_obj(raw_case)
        except (ValidationError, Exception) as exc:
            case_id = raw_case.get("id", "unknown_case") if isinstance(raw_case, dict) else "unknown_case"
            return EvaluationReport(
                case_id=case_id,
                gate="G2",
                policy_version=active_config.policy_version,
                weights_version=active_config.weights_version,
                calibration_status=active_config.calibration_status,
                decision=GateDecision.REJECT,
                weighted_score=None,
                hard_checks=HardCheckResult(
                    passed=False,
                    material_claim_supported=False,
                    evidence_not_superseded=False,
                    no_competitor_promotion=False,
                    no_contradiction=False,
                    no_injection_detected=False,
                    failures=["malformed_input_schema"],
                ),
                freshness=FreshnessAssessment(
                    status="invalid",
                    reference_date=ref_date.isoformat(),
                    reason="Input failed schema validation.",
                ),
                criteria=CriterionScores(),
                weights=active_config.weights,
                reasons=["malformed_input", f"schema_validation_error: {str(exc)}"],
                audit_trace=[f"Validation Error: {str(exc)}"],
            )

    # Stage 2-5: Evaluator Pipeline
    evaluator = G2Evaluator(config=active_config)
    return evaluator.evaluate(case, reference_date=ref_date)


def load_and_evaluate_fixtures(
    fixture_path: str | Path,
    config: Optional[PolicyConfig] = None,
) -> tuple[dict[str, Any], list[EvaluationReport]]:
    """
    Loads official or custom fixtures in-place and evaluates all cases.
    """
    path = Path(fixture_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Fixture file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    as_of = parse_reference_date(data.get("as_of"))
    cases_raw = data.get("cases", [])

    reports: list[EvaluationReport] = []
    for raw in cases_raw:
        report = evaluate_case(raw, reference_date=as_of, config=config)
        reports.append(report)

    metadata = {
        "schema_version": data.get("schema_version"),
        "as_of": as_of.isoformat(),
        "total_cases": len(cases_raw),
    }

    return metadata, reports


def run_weight_sensitivity_analysis(
    cases: list[dict[str, Any] | EvidenceCase],
    reference_date: Optional[date | str] = None,
    configs: Optional[dict[str, PolicyConfig]] = None,
) -> dict[str, Any]:
    """
    Evaluates eligible test cases under 3 distinct weight configurations
    to demonstrate weight sensitivity, ranking dynamics, and routing stability.
    """
    ref_date = parse_reference_date(reference_date)

    if configs is None:
        configs = {
            "Config 1 (Provisional Default)": PolicyConfig(
                weights={
                    "authority": 0.35,
                    "reliability": 0.25,
                    "freshness": 0.20,
                    "temporal_validity": 0.20,
                }
            ),
            "Config 2 (Equal Weights)": PolicyConfig(
                weights={
                    "authority": 0.25,
                    "reliability": 0.25,
                    "freshness": 0.25,
                    "temporal_validity": 0.25,
                }
            ),
            "Config 3 (Authority Heavy)": PolicyConfig(
                weights={
                    "authority": 0.50,
                    "reliability": 0.20,
                    "freshness": 0.15,
                    "temporal_validity": 0.15,
                }
            ),
        }

    results_by_config: dict[str, list[dict[str, Any]]] = {}

    for cfg_name, cfg in configs.items():
        config_reports: list[dict[str, Any]] = []
        for c in cases:
            report = evaluate_case(c, reference_date=ref_date, config=cfg)
            config_reports.append(
                {
                    "case_id": report.case_id,
                    "score": report.weighted_score,
                    "decision": report.decision.value,
                    "criteria": report.criteria.model_dump()
                    if hasattr(report.criteria, "model_dump")
                    else report.criteria.dict(),
                }
            )

        # Sort descending by score to determine rank
        sorted_reports = sorted(
            config_reports,
            key=lambda x: (x["score"] is not None, x["score"] or -1.0),
            reverse=True,
        )
        for rank, item in enumerate(sorted_reports, start=1):
            item["rank"] = rank

        results_by_config[cfg_name] = sorted_reports

    return {
        "reference_date": ref_date.isoformat(),
        "configs": {k: v.weights for k, v in configs.items()},
        "results_by_config": results_by_config,
    }
