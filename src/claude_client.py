"""Anthropic SDK wrapper for structured data extraction and analysis."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import anthropic
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
    """Wrapper around the Anthropic SDK for fund prospectus analysis."""

    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.api_key)
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _call_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_model: type[T],
        max_tokens: int | None = None,
        use_thinking: bool = False,
    ) -> T:
        """Make a Claude API call and parse the response into a Pydantic model."""
        max_tokens = max_tokens or self.config.max_tokens_extraction

        messages = [{"role": "user", "content": user_message}]

        # Build kwargs
        kwargs: dict = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
        }

        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": max_tokens // 2}
            kwargs["temperature"] = 1  # required when thinking is enabled

        # Make the API call
        response = self.client.messages.create(**kwargs)

        # Track token usage
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens

        # Extract text content from response
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content = block.text
                break

        # Parse JSON from the response
        # Try to find JSON in the response (Claude may wrap it in markdown code blocks)
        json_str = _extract_json(text_content)

        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.warning("Failed to parse structured output: %s", e)
            # Retry with explicit correction
            return self._retry_parse(system_prompt, user_message, text_content, response_model, max_tokens)

    def _retry_parse(
        self,
        system_prompt: str,
        user_message: str,
        previous_response: str,
        response_model: type[T],
        max_tokens: int,
    ) -> T:
        """Retry with an explicit correction prompt when parsing fails."""
        schema = json.dumps(response_model.model_json_schema(), indent=2)
        correction_message = (
            f"Your previous response could not be parsed. Please respond with ONLY valid JSON "
            f"matching this exact schema:\n\n{schema}\n\n"
            f"Previous response for context:\n{previous_response[:2000]}"
        )

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system_prompt}],
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": previous_response[:2000]},
                {"role": "user", "content": correction_message},
            ],
        )

        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens

        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content = block.text
                break

        json_str = _extract_json(text_content)
        return response_model.model_validate_json(json_str)

    # --- Public extraction methods ---

    def identify_funds(self, filename: str, text: str) -> FundIdentificationResult:
        """Call 1: Identify funds from cover pages / table of contents."""
        user_msg = FUND_IDENTIFICATION_USER.format(filename=filename, text=text[:15000])

        # Add JSON instruction to system prompt
        schema = json.dumps(FundIdentificationResult.model_json_schema(), indent=2)
        system = (
            FUND_IDENTIFICATION_SYSTEM
            + f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema}"
        )

        return self._call_structured(system, user_msg, FundIdentificationResult)

    def extract_risks(self, fund_name: str, text: str) -> FundRisks:
        """Call 2: Extract risk information for a fund."""
        user_msg = RISK_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])

        schema = json.dumps(FundRisks.model_json_schema(), indent=2)
        system = (
            RISK_EXTRACTION_SYSTEM
            + f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema}"
        )

        return self._call_structured(system, user_msg, FundRisks)

    def extract_returns(self, fund_name: str, text: str) -> FundReturns:
        """Call 3: Extract financial returns for a fund."""
        user_msg = RETURNS_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])

        schema = json.dumps(FundReturns.model_json_schema(), indent=2)
        system = (
            RETURNS_EXTRACTION_SYSTEM
            + f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema}"
        )

        return self._call_structured(system, user_msg, FundReturns)

    def extract_portfolio(self, fund_name: str, text: str) -> FundPortfolio:
        """Call 4: Extract investment portfolio for a fund."""
        user_msg = PORTFOLIO_EXTRACTION_USER.format(fund_name=fund_name, text=text[:30000])

        schema = json.dumps(FundPortfolio.model_json_schema(), indent=2)
        system = (
            PORTFOLIO_EXTRACTION_SYSTEM
            + f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema}"
        )

        return self._call_structured(system, user_msg, FundPortfolio)

    def generate_analysis(self, funds: list[FundData]) -> AnalyticalReport:
        """Call 5: Generate cross-fund analytical report."""
        # Serialize fund data to JSON for the prompt
        funds_json = json.dumps(
            [f.model_dump(exclude_none=True) for f in funds],
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        user_msg = ANALYSIS_USER.format(funds_json=funds_json[:60000])

        schema = json.dumps(AnalyticalReport.model_json_schema(), indent=2)
        system = (
            ANALYSIS_SYSTEM
            + f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema}"
        )

        return self._call_structured(
            system,
            user_msg,
            AnalyticalReport,
            max_tokens=self.config.max_tokens_analysis,
            use_thinking=True,
        )

    def estimate_cost(self) -> float:
        """Estimate API cost based on token usage (Sonnet pricing)."""
        # Sonnet 4: $3/M input, $15/M output
        input_cost = (self.total_input_tokens / 1_000_000) * 3.0
        output_cost = (self.total_output_tokens / 1_000_000) * 15.0
        return input_cost + output_cost


def _extract_json(text: str) -> str:
    """Extract JSON from text that may be wrapped in markdown code blocks."""
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
