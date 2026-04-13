"""Configuration loading from config.yaml, .env, and CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    input_dir: Path = Path("./input")
    output_dir: Path = Path("./output")
    model: str = "claude-sonnet-4-6"
    max_tokens_extraction: int = 16000
    max_tokens_analysis: int = 32000
    language: str = "es"
    output_language: str = "en"
    cost_warning_threshold: float = 5.00
    api_key: str = ""
    verbose: bool = False
    dry_run: bool = False


def load_config(
    config_path: str = "config.yaml",
    cli_overrides: dict | None = None,
) -> Config:
    """Load configuration from YAML file, .env, and optional CLI overrides."""
    # Load .env for API key
    load_dotenv()

    config = Config()

    # Load YAML config if it exists
    yaml_path = Path(config_path)
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

        if "input_dir" in yaml_data:
            config.input_dir = Path(yaml_data["input_dir"])
        if "output_dir" in yaml_data:
            config.output_dir = Path(yaml_data["output_dir"])
        if "model" in yaml_data:
            config.model = yaml_data["model"]
        if "max_tokens_extraction" in yaml_data:
            config.max_tokens_extraction = int(yaml_data["max_tokens_extraction"])
        if "max_tokens_analysis" in yaml_data:
            config.max_tokens_analysis = int(yaml_data["max_tokens_analysis"])
        if "language" in yaml_data:
            config.language = yaml_data["language"]
        if "output_language" in yaml_data:
            config.output_language = yaml_data["output_language"]
        if "cost_warning_threshold" in yaml_data:
            config.cost_warning_threshold = float(yaml_data["cost_warning_threshold"])

    # Load API key from environment
    config.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Apply CLI overrides
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None and hasattr(config, key):
                if key in ("input_dir", "output_dir"):
                    setattr(config, key, Path(value))
                else:
                    setattr(config, key, value)

    return config


def validate_config(config: Config) -> list[str]:
    """Validate configuration and return list of errors (empty if valid)."""
    errors = []

    if not config.api_key or config.api_key == "your-api-key-here":
        errors.append("ANTHROPIC_API_KEY not set. Add it to .env file.")

    if not config.input_dir.exists():
        errors.append(f"Input directory does not exist: {config.input_dir}")

    if not config.output_dir.exists():
        try:
            config.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create output directory: {e}")

    return errors
