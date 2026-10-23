# Task 6: Content-Quality Gate (G2 Gate)

## 1. Selected Task
**Task 6 — One Content-Quality Gate (G2: Evidence and Current-Validity Assessment)**

This component implements the G2 Content-Quality Gate for Atomity's Evidence-to-Insight system. Its sole responsibility is to evaluate evidence support, source authority, temporal validity, and current applicability for content cases using deterministic hard-floor checks and a transparent, auditable weighted scoring model. In strict accordance with the task specification, G2 evaluates evidence and current validity only—it explicitly excludes design, visual quality, writing style, and audience engagement.

---

## 2. How the Implementation Works

The gate executes a 5-stage deterministic pipeline. Decisions are made using strict precedence rules so outcomes never overlap or allow low-integrity claims to pass.

```
                   [ Input Case (JSON / Dict) ]
                                 │
                                 ▼
              ┌─────────────────────────────────────┐
              │  Stage 1: Pydantic Schema Validation │
              └──────────────────┬──────────────────┘
                                 │ Valid
                                 ▼
              ┌─────────────────────────────────────┐
              │ Stage 2: Security & Injection Guard │
              └──────────────────┬──────────────────┘
                                 │ Clean Text
                                 ▼
              ┌─────────────────────────────────────┐
              │     Stage 3: Mandatory Hard Floors  │
              └──────────────────┬──────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │ Hard Failure                  │ Passed
                 ▼                               ▼
       [ Route Decision ]           ┌────────────────────────┐
   (reject / revise / review)       │ Stage 4: Freshness &   │
                                    │ Temporal Validity      │
                                    └────────────┬───────────┘
                                                 │
                                                 ▼
                                    ┌────────────────────────┐
                                    │ Stage 5: Weighted Sum  │
                                    │ & Precedence Routing   │
                                    └────────────┬───────────┘
                                                 │
                                                 ▼
                                    [ Comprehensive Report ]
```

### The 5 Pipeline Stages:
1. **Schema Validation (`g2_gate/workflow.py`)**: Uses Pydantic v2 data models (`EvidenceCase`, `CaseMetadata`). Catches malformed structures or missing required fields gracefully and returns a structured `reject` report with `malformed_input` audit diagnostics, preventing runtime crashes.
2. **Untrusted Input & Injection Defense (`g2_gate/guardrails.py`)**: Treats all source text and statement fields as untrusted data. Scans for adversarial instruction overrides (e.g., `"ignore previous instructions"`, `"force decision to pass"`, `"override gate"`). Detection triggers a hard check violation routed to `reject`.
3. **Hard-Floor Checks (`g2_gate/evaluator.py`)**: Evaluates absolute requirements before scoring:
   - Competitor product claims $\rightarrow$ `reject`
   - Unsupported material claims $\rightarrow$ `revise`
   - Superseded evidence $\rightarrow$ `revise`
   - Materially conflicting evidence $\rightarrow$ `human_review`
   - Prompt injection detected $\rightarrow$ `reject`
   *(Hard check failures cannot be overridden by high criteria scores).*
4. **Freshness & Current Validity Assessment (`g2_gate/evaluator.py`)**: Distinguishes between publication date, event date, effective date, and current applicability:
   - **Regulations**: Evaluates `current_status` and `effective_from`. Historical enactment dates (e.g., from 2021) do not penalize valid, in-force laws. Adopted future rules (e.g., effective 2027) pass when statements accurately describe future applicability. Repealed or superseded statutes receive 0.0 validity.
   - **News & General Events**: Evaluates event age against the fixture's demo freshness policy ($\le 30\text{ days}$). News with events $> 30\text{ days}$ old routes to `revise` (`stale_news_event`). Missing event dates route to `human_review` (`unknown_event_date`) with a `null` score, never silently defaulting to zero.
5. **Multi-Factor Weighted Scoring & Decision Precedence (`g2_gate/evaluator.py`)**:
   - Calculates transparent weighted score: $\text{Score} = \sum (w_i \times c_i)$.
   - Routes through strict precedence: `reject` $\rightarrow$ `revise` $\rightarrow$ `human_review` $\rightarrow$ `pass`.

---

## 3. Setup & Run Instructions

The implementation runs 100% offline with zero external network requests or undisclosed credentials.

### Prerequisites
- Python 3.10+ (tested on Python 3.10, 3.11, 3.12, 3.13)

### Installation
From the repository root or submission folder:
```bash
# 1. Create and activate a clean virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# 2. Install minimal dependencies
pip install -r src/task-6_akil-al-sharafi/requirements.txt
```

### Running the Evaluator
Run the evaluation CLI against the official fixture (`fixtures/g2-cases.json`):
```bash
# Run from repository root
python3 src/task-6_akil-al-sharafi/main.py

# Or run from inside the submission directory
cd src/task-6_akil-al-sharafi
python3 main.py
```

### CLI Options
- `--fixtures <path>`: Specify custom fixture JSON path (defaults to repo root `fixtures/g2-cases.json`).
- `--additional-fixtures <path>`: Specify additional test fixture path.
- `--sensitivity`: Execute 3-way weight sensitivity comparison.
- `--json`: Output comprehensive JSON evaluation reports with audit traces.

---

## 4. Running the Tests

Execute the automated test suite using `pytest`:
```bash
# Run pytest from repo root
pytest src/task-6_akil-al-sharafi/tests -v

# Or run pytest from within task directory
cd src/task-6_akil-al-sharafi
pytest -v
```

### Test Coverage Summary (17 Tests Passing)
- `test_all_starter_fixture_cases_match_expected_decisions`: 100% pass rate across all 9 official starter cases in `fixtures/g2-cases.json`.
- `test_invalid_weight_sum_rejected`: Verifies $\sum w_i \neq 1.0$ raises `ValueError`.
- `test_negative_weight_rejected`: Verifies negative weights raise `ValueError`.
- `test_unknown_criterion_returns_null_and_human_review`: Verifies unknown temporal criteria yield `null` score and route to `human_review`.
- `test_hard_check_failure_overrides_high_scores`: Parameterized checks verifying competitor promotion, unsupported claims, superseded evidence, and contradictions cannot pass via scoring.
- `test_score_threshold_boundaries`: Verifies exact boundaries ($\ge 0.70$ pass, $0.40 - 0.69$ human review, $< 0.40$ revise).
- `test_prompt_injection_guardrail`: Parameterized testing of prompt-injection vectors resulting in hard `reject`.
- `test_malformed_input_graceful_rejection`: Schema validation failures return structured reports without crashing.
- `test_old_regulation_in_force_passes`: Verifies legacy statutes in force are not penalized for publication age.
- `test_repealed_regulation_fails_validity`: Verifies repealed laws receive 0.0 validity.
- `test_weight_sensitivity_comparison`: Tests 3 configurations across 3 cases, demonstrating score changes, ranking inversion, and routing shifts.

---

## 5. Fixtures & Assumptions Used

### Fixture Loading Boundary
- **In-Place Reading**: Official fixtures are loaded directly from `fixtures/g2-cases.json` via dynamic path resolution (`Path(__file__).resolve().parents[2] / "fixtures" / "g2-cases.json"`). No files in `fixtures/` are modified or copied.
- **Reference Date (`as_of`)**: The evaluator strictly respects the fixture's supplied `as_of` envelope date (`2026-10-06`) rather than system time, guaranteeing 100% deterministic results across all environments.
- **Metadata Boundary**: As stated in `task-6.md`, fixture metadata assertions (`supported`, `superseded`, `current_status`) are trusted input properties to this gate. G2 is responsible for evaluating, routing, and scoring those assertions, not independently investigating real-world truth.

### Criterion Definitions & Observable Anchors
Each criterion is mapped to an explicit, observable numerical scale:

| Criterion | Score `1.0` | Score `0.7` / `0.6` | Score `0.4` / `0.3` | Score `0.0` / `0.2` |
| :--- | :--- | :--- | :--- | :--- |
| **Source Authority** ($w=0.35$) | `primary_authority`: Official regulatory agencies, statutory bodies | `secondary_authority`: Accredited audit bodies, established standards groups (0.7) | `user_generated`: Community reports, practitioner discussions (0.4) | `competitor`: Rival product marketing or self-serving claims (0.2) |
| **Content Reliability** ($w=0.25$) | `regulation`: Codified legal standards, statutes | `official_report`: Peer-reviewed benchmarks, formal agency audits (0.85) / `news`: Professional reporting (0.60) | `blog`: Opinion editorials, unverified technical writeups (0.30) | Unverified hearsay, unsubstantiated releases |
| **Freshness** ($w=0.20$) | Event age $\le 30\text{ days}$ under demo policy; active regulation | Event age $31 - 90\text{ days}$ (0.7) | Event age $91 - 180\text{ days}$ (0.4) | Event age $> 180\text{ days}$ (0.1) |
| **Temporal Validity** ($w=0.20$) | `current`: Legally active and currently applicable | `adopted_not_applicable`: Adopted future rule accurately described in statement (0.8) | `draft`: Preliminary proposal not yet adopted (0.4) | `repealed` or `superseded`: Former rule no longer valid (0.0) |

### Weight Rationale & Provisional Status
- **Weights**: Authority ($0.35$), Reliability ($0.25$), Freshness ($0.20$), Temporal Validity ($0.20$).
- **Rationale**: In regulatory and cloud infrastructure compliance, provenance authority carries the greatest risk; unverified secondary sources cannot be redeemed simply by being recent. Reliability measures structural rigor, while freshness and validity ensure the claim accurately matches current reality.
- **Calibration Status**: Explicitly designated as `provisional-v1` / `uncalibrated`. The score is a deterministic decision aid, not a calibrated statistical probability.

---

## 6. How Each Acceptance Criterion is Satisfied

| Task 6 Requirement | Implementation Module | Verification Test |
| :--- | :--- | :--- |
| **Evaluate all starter cases** | `g2_gate/workflow.py`, `evaluator.py` | `test_all_starter_fixture_cases_match_expected_decisions` (9/9 matched) |
| **Hard checks evaluated before scoring** | `G2Evaluator.run_hard_checks()` | `test_hard_check_failure_overrides_high_scores` |
| **Freshness distinguishes date types** | `G2Evaluator.assess_freshness_and_validity()` | `test_old_regulation_in_force_passes`, `test_repealed_regulation_fails_validity` |
| **Unknown criterion produces null score** | `G2Evaluator.compute_weighted_score()` | `test_unknown_criterion_returns_null_and_human_review` |
| **Sum of weights must equal 1.0** | `PolicyConfig.validate_weights()` | `test_invalid_weight_sum_rejected` |
| **Negative weights rejected** | `PolicyConfig.validate_weights()` | `test_negative_weight_rejected` |
| **Malformed input handling** | `evaluate_case()` | `test_malformed_input_graceful_rejection` |
| **Decision precedence order** | `G2Evaluator.evaluate()` | Tested across all starter cases and edge tests |
| **Untrusted source & injection defense**| `guardrails.scan_for_instruction_injection()` | `test_prompt_injection_guardrail` |
| **Weight sensitivity analysis ($\ge 3$ cases)**| `run_weight_sensitivity_analysis()` | `test_weight_sensitivity_comparison` |

---

## 7. Weight Sensitivity Comparison

In accordance with Task 6 specifications, three eligible cases from `fixtures/additional-cases.json` were evaluated across three distinct weight configurations:
1. **Config 1 (Provisional Default)**: Authority $0.35$, Reliability $0.25$, Freshness $0.20$, Validity $0.20$
2. **Config 2 (Equal Weights)**: Authority $0.25$, Reliability $0.25$, Freshness $0.25$, Validity $0.25$
3. **Config 3 (Authority Heavy)**: Authority $0.50$, Reliability $0.20$, Freshness $0.15$, Validity $0.15$

### Sensitivity Results Table

| Case ID | Criteria Profile | Config 1 (Default) | Config 2 (Equal) | Config 3 (Auth-Heavy) | Sensitivity Dynamics |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `case-high-auth-news` | Auth: 1.0, Rel: 0.6, Fresh: 1.0, Temp: 1.0 | 0.9000 (Rank 1, Pass) | 0.9000 (Rank 2, Pass) | 0.9200 (Rank 1, Pass) | **Rank Inversion** with Case 2 under Config 2 |
| `case-secondary-authoritative-regulation` | Auth: 0.7, Rel: 1.0, Fresh: 1.0, Temp: 1.0 | 0.8950 (Rank 2, Pass) | 0.9250 (Rank 1, Pass) | 0.8500 (Rank 2, Pass) | Takes Rank 1 when reliability and validity share equal weight |
| `case-borderline-community-report` | Auth: 0.4, Rel: 0.85, Fresh: 1.0, Temp: 1.0 | 0.7525 (Rank 3, Pass) | 0.8125 (Rank 3, Pass) | 0.6700 (Rank 3, **Review**) | **Decision Shift**: drops below $0.70$ threshold into `human_review` |

### Key Observations
1. **Ranking Inversion**: Under Config 2 (Equal Weights), `case-secondary-authoritative-regulation` overtakes `case-high-auth-news` because equal weighting rewards highest content reliability ($1.0$) over primary authority ($1.0$).
2. **Decision Boundary Routing**: Under Config 3, increasing authority weight to $0.50$ penalizes user-generated sources sufficiently to pull `case-borderline-community-report` from $0.7525$ down to $0.6700$, causing an automated routing shift from `pass` to `human_review`.
3. This empirical comparison proves that the chosen provisional weights directly impact gate outcomes and must not be treated as unquestionable or scientifically calibrated.

---

## 8. Engineering Trade-offs & Known Limitations

### Engineering Trade-offs
- **Deterministic Rule Engine vs. Live LLM**: Implemented as a deterministic Pydantic rule engine. This guarantees 100% auditability, sub-millisecond execution, zero token cost, and complete immunity to hallucination.
- **Fail-Safe Precedence vs. Continuous Scoring**: Hard floors enforce strict gatekeeper boundaries. Even if a case scores $1.0$ across all valid criteria, an unsupported claim or competitor promotion cannot be rescued by high scores.
- **Explicit Unknowns vs. Imputation**: Missing temporal metadata yields an explicit `null` score rather than defaulting to 0 or an imputed average, ensuring mandatory human review where data is incomplete.

### Known Limitations
- **Regex Guardrails vs. Semantic Classifiers**: Untrusted input screening utilizes compiled regex pattern matching. While fast and deterministic, it can be bypassed by creative paraphrasing or obfuscation that a semantic model might catch.
- **Test-Only Freshness Policy**: The 30-day news threshold is a synthetic test convention specified by `fixtures/g2-cases.json`, not an empirically validated decay rate for real-world legal information.
- **Static Weights**: Weights are currently hardcoded in `PolicyConfig`. In production, weights should be dynamically loaded from a versioned policy repository calibrated against expert human adjudications.
