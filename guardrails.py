from __future__ import annotations

import re
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


def _load_regex_patterns() -> tuple[list[str], list[str]]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return [], []

    if not isinstance(config, dict):
        return [], []

    rails = config.get("rails", {})
    if not isinstance(rails, dict):
        return [], []

    guardrail_config = rails.get("config", {})
    if not isinstance(guardrail_config, dict):
        return [], []

    regex_detection = guardrail_config.get("regex_detection", {})
    if not isinstance(regex_detection, dict):
        return [], []

    input_cfg = regex_detection.get("input", {})
    output_cfg = regex_detection.get("output", {})

    if not isinstance(input_cfg, dict):
        input_cfg = {}
    if not isinstance(output_cfg, dict):
        output_cfg = {}

    input_patterns = input_cfg.get("patterns", [])
    output_patterns = output_cfg.get("patterns", [])

    if not isinstance(input_patterns, list):
        input_patterns = []
    if not isinstance(output_patterns, list):
        output_patterns = []

    return input_patterns, output_patterns


def _matches_any(text: str, patterns: list[str], case_insensitive: bool = True) -> bool:
    if not text or not patterns:
        return False

    flags = re.IGNORECASE if case_insensitive else 0
    for pattern in patterns:
        if re.search(str(pattern), str(text), flags):
            return True
    return False


def check_input(message: str):
    patterns, _ = _load_regex_patterns()
    if _matches_any(message, patterns, case_insensitive=True):
        return False, "I can't process that request. Please provide a normal customer-service request."
    return True, message


def check_output(response: str):
    _, patterns = _load_regex_patterns()
    if _matches_any(response, patterns, case_insensitive=True):
        return False, "I can't provide that response."
    return True, response
