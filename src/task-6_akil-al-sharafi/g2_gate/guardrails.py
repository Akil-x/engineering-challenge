"""
Security and input sanitization layer for untrusted content and prompt-injection defense.
"""

from __future__ import annotations

import re

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(r"ignore\s+(?:all\s+|any\s+|previous\s+|prior\s+|above\s+)?instructions", re.IGNORECASE),
    ),
    (
        "disregard_rules",
        re.compile(r"disregard\s+(?:all\s+|any\s+|previous\s+|prior\s+)?(?:rules|instructions|prompts)", re.IGNORECASE),
    ),
    (
        "system_prompt",
        re.compile(r"(?:system\s+prompt|system\s*:\s*you\s+are)", re.IGNORECASE),
    ),
    (
        "force_pass",
        re.compile(r"force\s+(?:decision\s+to\s+)?(?:pass|approve)", re.IGNORECASE),
    ),
    (
        "override_gate",
        re.compile(r"override\s+(?:gate|decision|policy|checks|evaluation)", re.IGNORECASE),
    ),
    (
        "bypass_verification",
        re.compile(r"bypass\s+(?:verification|checks|policy|guardrails|filters)", re.IGNORECASE),
    ),
    (
        "developer_mode",
        re.compile(r"(?:developer\s+mode|jailbreak|unrestricted\s+mode)", re.IGNORECASE),
    ),
    (
        "roleplay_instructions",
        re.compile(r"you\s+are\s+now\s+(?:an?|in)\b", re.IGNORECASE),
    ),
    (
        "suppress_rules",
        re.compile(r"do\s+not\s+apply\s+(?:rules|checks|filters)", re.IGNORECASE),
    ),
]


def scan_for_instruction_injection(text: str) -> list[str]:
    """
    Scans untrusted input text for prompt-injection and instruction-override patterns.

    Returns:
        A list of identified violation tags (empty if text is clean).
    """
    if not text or not isinstance(text, str):
        return []

    detected: list[str] = []
    for tag, pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            detected.append(tag)

    return detected
