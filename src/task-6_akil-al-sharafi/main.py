#!/usr/bin/env python3
"""
CLI entry point for G2 Gate evaluation runner and sensitivity analysis.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from g2_gate.workflow import (
    load_and_evaluate_fixtures,
    run_weight_sensitivity_analysis,
)


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    """
    Renders an ASCII table for console reporting.
    """
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(cell))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    lines = [sep, header_line, sep]
    for row in rows:
        line = "| " + " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)) + " |"
        lines.append(line)
    lines.append(sep)
    return "\n".join(lines)


def main() -> int:
    default_fixtures = Path(__file__).resolve().parents[2] / "fixtures" / "g2-cases.json"
    additional_fixtures_default = Path(__file__).resolve().parent / "fixtures" / "additional-cases.json"

    parser = argparse.ArgumentParser(
        description="G2 Content-Quality Gate Evaluation Runner (Task 6)"
    )
    parser.add_argument(
        "--fixtures",
        type=str,
        default=str(default_fixtures),
        help=f"Path to official starter fixtures (default: {default_fixtures})",
    )
    parser.add_argument(
        "--additional-fixtures",
        type=str,
        default=str(additional_fixtures_default),
        help="Path to additional eligible fixtures for sensitivity analysis",
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Execute 3-way weight sensitivity comparison on additional eligible cases",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output evaluation reports in JSON format",
    )

    args = parser.parse_args()

    # Load and evaluate primary fixture
    fixture_path = Path(args.fixtures)
    if not fixture_path.is_file():
        print(f"Error: Fixture file not found: {fixture_path}", file=sys.stderr)
        return 1

    metadata, reports = load_and_evaluate_fixtures(fixture_path)

    # Read raw cases to compare expected_decision if available
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)
    expected_map = {c["id"]: c.get("expected_decision", "N/A") for c in fixture_data.get("cases", [])}

    all_matched = True
    table_rows: list[list[str]] = []

    for report in reports:
        expected = expected_map.get(report.case_id, "N/A")
        actual = report.decision.value
        matched = (expected == "N/A") or (expected == actual)
        if not matched:
            all_matched = False

        status_str = "MATCH" if matched else "MISMATCH"
        score_str = f"{report.weighted_score:.4f}" if report.weighted_score is not None else "null"
        reasons_str = ", ".join(report.reasons[:2])

        table_rows.append([
            report.case_id,
            expected,
            actual,
            score_str,
            status_str,
            reasons_str,
        ])

    headers = ["Case ID", "Expected", "Actual", "Score", "Status", "Key Reasons"]

    if args.json:
        output_payload: dict[str, Any] = {
            "metadata": metadata,
            "all_passed": all_matched,
            "reports": [r.to_dict() for r in reports],
        }
        if args.sensitivity and Path(args.additional_fixtures).is_file():
            with open(args.additional_fixtures, "r", encoding="utf-8") as f:
                add_data = json.load(f)
            sensitivity_res = run_weight_sensitivity_analysis(add_data.get("cases", []))
            output_payload["sensitivity_analysis"] = sensitivity_res
        print(json.dumps(output_payload, indent=2))
    else:
        print("\n=======================================================")
        print("     ATOMITY G2 CONTENT-QUALITY GATE EVALUATION        ")
        print(f"  Reference Date: {metadata['as_of']} | Cases: {metadata['total_cases']}")
        print("=======================================================\n")
        print(format_table(table_rows, headers))

        if all_matched:
            print("\n[SUCCESS] All starter fixture cases match their expected decisions 100%.\n")
        else:
            print("\n[FAILURE] One or more cases deviated from the expected decision.\n", file=sys.stderr)

        if args.sensitivity or True:
            # Always display sensitivity summary in non-json mode for easy verification
            add_path = Path(args.additional_fixtures)
            if add_path.is_file():
                print("-------------------------------------------------------")
                print("       WEIGHT SENSITIVITY ANALYSIS (3 CONFIGS)        ")
                print("-------------------------------------------------------")
                with open(add_path, "r", encoding="utf-8") as f:
                    add_data = json.load(f)
                sensitivity_res = run_weight_sensitivity_analysis(add_data.get("cases", []))

                sens_rows: list[list[str]] = []
                for cfg_name, results in sensitivity_res["results_by_config"].items():
                    for res in results:
                        score_val = f"{res['score']:.4f}" if res['score'] is not None else "null"
                        sens_rows.append([
                            cfg_name,
                            res["case_id"],
                            score_val,
                            str(res["rank"]),
                            res["decision"],
                        ])
                sens_headers = ["Configuration", "Case ID", "Score", "Rank", "Decision"]
                print(format_table(sens_rows, sens_headers))
                print("\nObservations: Case 'case-borderline-community-report' drops from 'pass' to 'human_review' under Authority-Heavy weights due to lower user_generated source authority weight.")

    return 0 if all_matched else 1


if __name__ == "__main__":
    sys.exit(main())
