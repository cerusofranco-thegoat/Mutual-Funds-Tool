"""Read supplementary Excel input files into normalized DocumentContent."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl import load_workbook

from .models import DocumentContent, PageContent

logger = logging.getLogger(__name__)


def extract_excel(file_path: Path) -> DocumentContent:
    """Read an Excel file and convert each sheet into a PageContent.

    Each sheet becomes a 'page' with its text content being all cell values
    concatenated row-by-row, and tables extracted from the raw data.
    """
    pages: list[PageContent] = []

    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        for i, sheet_name in enumerate(wb.sheetnames):
            ws = wb[sheet_name]
            rows: list[list[str]] = []
            text_lines: list[str] = []

            for row in ws.iter_rows(values_only=True):
                cells = [str(cell) if cell is not None else "" for cell in row]
                rows.append(cells)
                # Build text representation: non-empty cells joined by tab
                non_empty = [c for c in cells if c]
                if non_empty:
                    text_lines.append("\t".join(non_empty))

            text = f"[Sheet: {sheet_name}]\n" + "\n".join(text_lines)
            tables = [rows] if rows else []

            pages.append(PageContent(
                page_number=i + 1,
                text=text,
                tables=tables,
            ))

        wb.close()
    except Exception as e:
        logger.error("Failed to read Excel file %s: %s", file_path.name, e)

    return DocumentContent(filename=file_path.name, pages=pages)
