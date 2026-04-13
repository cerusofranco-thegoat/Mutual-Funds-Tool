"""Mutual Funds Analyzing Tool - CLI entry point.

Reads BlackRock Mexico mutual fund prospectus PDFs/Excel files,
extracts structured data via Claude Code CLI, and generates
a comprehensive Excel report with per-fund details and cross-fund analysis.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from src.config import load_config, validate_config
from src.pipeline import run as run_pipeline, PipelineResult
from src.utils import setup_logging

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze BlackRock Mexico mutual fund prospectuses and generate Excel reports.",
    )
    parser.add_argument(
        "--input-dir",
        help="Directory containing PDF/Excel prospectus files (default: ./input)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for generated reports (default: ./output)",
    )
    parser.add_argument(
        "--model",
        help="Claude model to use (default: sonnet). Accepts aliases like 'sonnet', 'opus', 'haiku'.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and extract files without making API calls (for cost estimation)",
    )
    return parser.parse_args()


def print_summary(result: PipelineResult) -> None:
    """Print end-of-run summary."""
    console.print("\n" + "=" * 60)
    console.print("[bold]Run Summary[/bold]")
    console.print("=" * 60)

    console.print(f"  Files processed: [bold]{result.files_processed}[/bold]")
    console.print(f"  Funds extracted:  [bold]{len(result.funds)}[/bold]")

    if result.files_skipped:
        console.print(f"  Files skipped:   [yellow]{len(result.files_skipped)}[/yellow]")
        for name, reason in result.files_skipped:
            console.print(f"    - {name}: {reason}")

    if result.fund_errors:
        console.print(f"  Fund errors:     [red]{len(result.fund_errors)}[/red]")
        for name, error in result.fund_errors:
            console.print(f"    - {name}: {error}")

    if result.output_path:
        console.print(f"\n  Output: [bold green]{result.output_path}[/bold green]")

    console.print(f"  Claude CLI calls:  [bold]{result.cli_calls}[/bold]")
    console.print("  Cost: [bold green]$0.00 (uses Claude Code subscription)[/bold green]")
    console.print("=" * 60)


def main() -> int:
    args = parse_args()

    setup_logging(verbose=args.verbose)

    # Build CLI overrides dict
    overrides = {}
    if args.input_dir:
        overrides["input_dir"] = args.input_dir
    if args.output_dir:
        overrides["output_dir"] = args.output_dir
    if args.model:
        overrides["model"] = args.model
    if args.verbose:
        overrides["verbose"] = True
    if args.dry_run:
        overrides["dry_run"] = True

    config = load_config(config_path=args.config, cli_overrides=overrides)

    # Validate
    errors = validate_config(config)
    if errors:
        for err in errors:
            console.print(f"[red]Config error: {err}[/red]")
        return 1

    console.print("[bold]Mutual Funds Analyzing Tool[/bold]")
    console.print(f"  Model: {config.model}")
    console.print(f"  Input: {config.input_dir.resolve()}")
    console.print(f"  Output: {config.output_dir.resolve()}")
    console.print()

    result = run_pipeline(config)
    print_summary(result)

    return 0 if not result.fund_errors and result.funds else 1


if __name__ == "__main__":
    sys.exit(main())
