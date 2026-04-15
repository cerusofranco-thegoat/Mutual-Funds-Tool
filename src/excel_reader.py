"""Read supplementary Excel input files into normalized DocumentContent."""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl import load_workbook

from .models import DocumentContent, PageContent

logger = logging.getLogger(__name__)


def _page_from_rows(index: int, sheet_name: str, rows: list[list[str]]) -> PageContent:
    text_lines = ["\t".join(c for c in r if c) for r in rows if any(r)]
    text = f"[Sheet: {sheet_name}]\n" + "\n".join(text_lines)
    return PageContent(
        page_number=index + 1,
        text=text,
        tables=[rows] if rows else [],
    )


def _extract_xls_legacy(file_path: Path) -> list[PageContent]:
    import xlrd  # type: ignore

    pages: list[PageContent] = []
    book = xlrd.open_workbook(str(file_path))
    for i, sheet in enumerate(book.sheets()):
        rows: list[list[str]] = []
        for r in range(sheet.nrows):
            row = sheet.row_values(r)
            rows.append([str(c) if c != "" else "" for c in row])
        pages.append(_page_from_rows(i, sheet.name, rows))
    return pages


def _extract_xlsx(file_path: Path) -> list[PageContent]:
    pages: list[PageContent] = []
    wb = load_workbook(file_path, read_only=True, data_only=True)
    for i, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        rows = [
            [str(cell) if cell is not None else "" for cell in row]
            for row in ws.iter_rows(values_only=True)
        ]
        pages.append(_page_from_rows(i, sheet_name, rows))
    wb.close()
    return pages


def extract_excel(file_path: Path) -> DocumentContent:
    """Read an Excel file and convert each sheet into a PageContent."""
    pages: list[PageContent] = []
    try:
        if file_path.suffix.lower() == ".xls":
            pages = _extract_xls_legacy(file_path)
        else:
            pages = _extract_xlsx(file_path)
    except Exception as e:
        logger.error("Failed to read Excel file %s: %s", file_path.name, e)

    return DocumentContent(filename=file_path.name, pages=pages)
