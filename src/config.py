"""Configuration loading from config.yaml and CLI overrides."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    input_dir: Path = Path("./input")
    output_dir: Path = Path("./output")
    model: str = "sonnet"
    language: str = "es"
    output_language: str = "en"
    verbose: bool = False
    dry_run: bool = False


def load_config(
    config_path: str = "config.yaml",
    cli_overrides: dict | None = None,
) -> Config:
    """Load configuration from YAML file and optional CLI overrides."""
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
        if "language" in yaml_data:
            config.language = yaml_data["language"]
        if "output_language" in yaml_data:
            config.output_language = yaml_data["output_language"]

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

    # Check that claude CLI is available
    if not shutil.which("claude"):
        errors.append("Claude Code CLI ('claude') not found in PATH. Install it first.")

    if not config.input_dir.exists():
        errors.append(f"Input directory does not exist: {config.input_dir}")

    if not config.output_dir.exists():
        try:
            config.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create output directory: {e}")

    return errors
