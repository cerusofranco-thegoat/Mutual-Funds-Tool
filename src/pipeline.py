"""Main pipeline orchestrating the full data flow from input files to Excel output."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .claude_client import ClaudeClient
from .config import Config
from .excel_reader import extract_excel
from .models import AnalyticalReport, DocumentContent, FundData
from .pdf_reader import extract_pdf

logger = logging.getLogger(__name__)
console = Console()


class PipelineResult:
    """Result of running the full pipeline."""

    def __init__(self):
        self.funds: list[FundData] = []
        self.report: AnalyticalReport | None = None
        self.files_processed: int = 0
        self.files_skipped: list[tuple[str, str]] = []  # (filename, reason)
        self.fund_errors: list[tuple[str, str]] = []  # (fund_name, error)
        self.output_path: Path | None = None
        self.estimated_cost: float = 0.0


def discover_files(input_dir: Path) -> list[Path]:
    """Find all PDF and Excel files in the input directory."""
    files = []
    for pattern in ("*.pdf", "*.PDF", "*.xlsx", "*.XLSX", "*.xls"):
        files.extend(input_dir.glob(pattern))
    files.sort(key=lambda p: p.name)
    return files


def extract_document(file_path: Path) -> DocumentContent | None:
    """Extract content from a single file based on its extension."""
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_pdf(file_path)
        elif suffix in (".xlsx", ".xls"):
            return extract_excel(file_path)
        else:
            logger.warning("Unsupported file type: %s", file_path.name)
            return None
    except Exception as e:
        logger.error("Failed to extract %s: %s", file_path.name, e)
        return None


def get_pages_text(doc: DocumentContent, start: int | None = None, end: int | None = None) -> str:
    """Get concatenated text from a range of pages."""
    pages = doc.pages
    if start is not None:
        pages = [p for p in pages if p.page_number >= start]
    if end is not None:
        pages = [p for p in pages if p.page_number <= end]
    return "\n\n".join(p.text for p in pages if p.text.strip())


def run(config: Config) -> PipelineResult:
    """Execute the full analysis pipeline."""
    result = PipelineResult()

    # Phase 1: Discover files
    files = discover_files(config.input_dir)
    if not files:
        console.print("[yellow]No PDF or Excel files found in input directory.[/yellow]")
        return result

    console.print(f"Found [bold]{len(files)}[/bold] file(s) to process.\n")

    claude = ClaudeClient(config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        main_task = progress.add_task("Processing files", total=len(files))

        for file_path in files:
            progress.update(main_task, description=f"Processing {file_path.name}")

            # Extract document content
            doc = extract_document(file_path)
            if doc is None or not doc.pages:
                result.files_skipped.append((file_path.name, "Extraction failed"))
                progress.advance(main_task)
                continue

            result.files_processed += 1

            # Phase 2: Identify funds
            cover_text = get_pages_text(doc, start=1, end=5)
            if not cover_text.strip():
                result.files_skipped.append((file_path.name, "No text content"))
                progress.advance(main_task)
                continue

            try:
                id_result = claude.identify_funds(doc.filename, cover_text)
            except Exception as e:
                logger.error("Fund identification failed for %s: %s", file_path.name, e)
                result.files_skipped.append((file_path.name, f"Identification failed: {e}"))
                progress.advance(main_task)
                continue

            if not id_result.funds:
                result.files_skipped.append((file_path.name, "No funds identified"))
                progress.advance(main_task)
                continue

            # Phase 3: Per-fund extraction
            for fund_id in id_result.funds:
                fund_name = fund_id.fund_name
                progress.update(main_task, description=f"Extracting: {fund_name[:40]}")

                fund_text = get_pages_text(doc, start=fund_id.page_start, end=fund_id.page_end)
                if not fund_text.strip():
                    fund_text = get_pages_text(doc)  # Use full document as fallback

                fund_data = FundData(
                    identification=fund_id,
                    source_file=file_path.name,
                )

                # Extract risks
                try:
                    fund_data.risks = claude.extract_risks(fund_name, fund_text)
                except Exception as e:
                    logger.error("Risk extraction failed for %s: %s", fund_name, e)
                    result.fund_errors.append((fund_name, f"Risk extraction: {e}"))

                # Extract returns
                try:
                    fund_data.returns = claude.extract_returns(fund_name, fund_text)
                except Exception as e:
                    logger.error("Returns extraction failed for %s: %s", fund_name, e)
                    result.fund_errors.append((fund_name, f"Returns extraction: {e}"))

                # Extract portfolio
                try:
                    fund_data.portfolio = claude.extract_portfolio(fund_name, fund_text)
                except Exception as e:
                    logger.error("Portfolio extraction failed for %s: %s", fund_name, e)
                    result.fund_errors.append((fund_name, f"Portfolio extraction: {e}"))

                result.funds.append(fund_data)

            progress.advance(main_task)

    # Phase 4: Analytical assessment
    if result.funds:
        console.print("\n[bold]Generating analytical report...[/bold]")
        try:
            result.report = claude.generate_analysis(result.funds)
        except Exception as e:
            logger.error("Analysis generation failed: %s", e)
            console.print(f"[red]Analysis generation failed: {e}[/red]")

    # Phase 5: Excel generation
    if result.funds:
        from .excel_writer import generate_workbook

        try:
            output_path = generate_workbook(config, result.funds, result.report)
            result.output_path = output_path
        except Exception as e:
            logger.error("Excel generation failed: %s", e)
            console.print(f"[red]Excel generation failed: {e}[/red]")

            # Save JSON backup
            _save_json_backup(config, result)

    result.estimated_cost = claude.estimate_cost()
    return result


def _save_json_backup(config: Config, result: PipelineResult) -> None:
    """Save extracted data as JSON when Excel generation fails."""
    import json
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config.output_dir / f"backup_{timestamp}.json"

    data = {
        "funds": [f.model_dump(exclude_none=True) for f in result.funds],
        "report": result.report.model_dump(exclude_none=True) if result.report else None,
    }

    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"[yellow]JSON backup saved to: {backup_path}[/yellow]")
    except Exception as e:
        logger.error("JSON backup also failed: %s", e)
