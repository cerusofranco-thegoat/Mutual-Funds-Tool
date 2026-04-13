"""Claude Code CLI wrapper for structured data extraction and analysis.

Uses 'claude -p' (print mode) as a subprocess instead of the Anthropic API directly,
so the tool runs on your existing Claude Code subscription with no API key needed.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .config import Config
from .models import (
    AnalyticalReport,
    FundData,
    FundIdentificationResult,
    FundPortfolio,
    FundReturns,
    FundRisks,
)
from .prompts import (
    ANALYSIS_SYSTEM,
    ANALYSIS_USER,
    FUND_IDENTIFICATION_SYSTEM,
    FUND_IDENTIFICATION_USER,
    PORTFOLIO_EXTRACTION_SYSTEM,
    PORTFOLIO_EXTRACTION_USER,
    RETURNS_EXTRACTION_SYSTEM,
    RETURNS_EXTRACTION_USER,
    RISK_EXTRACTION_SYSTEM,
    RISK_EXTRACTION_USER,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ClaudeClient:
    """Wrapper that calls Claude Code CLI for fund prospectus analysis."""

    def __init__(self, config: Config):
        self.config = config
        self.call_count = 0

    def _call_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_model: type[T],
    ) -> T:
        """Call Claude Code CLI and parse the response into a Pydantic model.

        Uses 'claude -p' with --json-schema for structured output and
        --system-prompt for the system instructions.
        """
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema)

        # Write the user message to a temp file to avoid command-line length limits
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(user_message)
            tmp_path = tmp.name

        try:
            cmd = [
                "claude",
                "-p",
                "--output-format", "json",
                "--json-schema", schema_str,
                "--system-prompt", system_prompt,
                "--model", self.config.model,
                "--no-session-persistence",
                "--bare",
            ]

            # Pipe the user message via stdin from the temp file
            with open(tmp_path, "r", encoding="utf-8") as f:
                proc = subprocess.run(
                    cmd,
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout per call
                )

            self.call_count += 1

            if proc.returncode != 0:
                stderr = proc.stderr.strip()
                logger.error("Claude CLI failed (exit %d): %s", proc.returncode, stderr)
                raise RuntimeError(f"Claude CLI error: {stderr}")

            raw_output = proc.stdout.strip()
            if not raw_output:
                raise RuntimeError("Claude CLI returned empty output")

            # --output-format json returns a JSON envelope with the result
            try:
                envelope = json.loads(raw_output)
            except json.JSONDecodeError:
                # If it's not valid JSON envelope, treat as raw text
                json_str = _extract_json(raw_output)
                return response_model.model_validate_json(json_str)

            # The envelope from claude --output-format json has a "result" field
            # containing the actual text response
            if isinstance(envelope, dict) and "result" in envelope:
                result_text = envelope["result"]
            elif isinstance(envelope, dict) and "content" in envelope:
                # Alternative envelope format
                result_text = envelope["content"]
            else:
                # Might be the direct JSON output thanks to --json-schema
                result_text = raw_output

            json_str = _extract_json(result_text)

            try:
                return response_model.model_validate_json(json_str)
            except Exception as e:
                logger.warning("First parse attempt failed: %s", e)
                # Try parsing the entire result_text as-is
                return response_model.model_validate_json(
                    result_text if isinstance(result_text, str) else json.dumps(result_text)
                )

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # --- Public extraction methods ---

    def identify_funds(self, filename: str, text: str) -> FundIdentificationResult:
        """Call 1: Identify funds from cover pages / table of contents."""
        user_msg = FUND_IDENTIFICATION_USER.format(filename=filename, text=text[:15000])
        return self._call_structured(
            FUND_IDENTIFICATION_SYSTEM, user_msg, FundIdentificationResult
        )

    def extract_risks(self, fund_name: str, text: str) -> FundRisks:
        """Call 2: Extract risk information for a fund."""
        user_msg = RISK_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])
        return self._call_structured(RISK_EXTRACTION_SYSTEM, user_msg, FundRisks)

    def extract_returns(self, fund_name: str, text: str) -> FundReturns:
        """Call 3: Extract financial returns for a fund."""
        user_msg = RETURNS_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])
        return self._call_structured(RETURNS_EXTRACTION_SYSTEM, user_msg, FundReturns)

    def extract_portfolio(self, fund_name: str, text: str) -> FundPortfolio:
        """Call 4: Extract investment portfolio for a fund."""
        user_msg = PORTFOLIO_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])
        return self._call_structured(PORTFOLIO_EXTRACTION_SYSTEM, user_msg, FundPortfolio)

    def generate_analysis(self, funds: list[FundData]) -> AnalyticalReport:
        """Call 5: Generate cross-fund analytical report."""
        funds_json = json.dumps(
            [f.model_dump(exclude_none=True) for f in funds],
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        user_msg = ANALYSIS_USER.format(funds_json=funds_json[:60000])
        return self._call_structured(ANALYSIS_SYSTEM, user_msg, AnalyticalReport)

    def estimate_cost(self) -> float:
        """No API cost — runs on Claude Code subscription."""
        return 0.0


def _extract_json(text: str) -> str:
    """Extract JSON from text that may be wrapped in markdown code blocks."""
    if not isinstance(text, str):
        return json.dumps(text)

    text = text.strip()

    # Remove markdown code block wrappers
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    # Try to find JSON object or array boundaries
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

    return text
