"""PDF text and table extraction using pdfplumber with PyMuPDF fallback."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import DocumentContent, PageContent

logger = logging.getLogger(__name__)


def extract_pdf(file_path: Path) -> DocumentContent:
    """Extract text and tables from a PDF file.

    Uses pdfplumber as the primary extractor. Falls back to PyMuPDF
    if pdfplumber fails or returns empty text.
    """
    pages = _extract_with_pdfplumber(file_path)

    # Fallback to PyMuPDF if pdfplumber yielded no text
    if not pages or all(not p.text.strip() for p in pages):
        logger.info("pdfplumber returned no text for %s, trying PyMuPDF", file_path.name)
        pages = _extract_with_pymupdf(file_path)

    if not pages:
        logger.warning("No content extracted from %s", file_path.name)

    return DocumentContent(filename=file_path.name, pages=pages)


def _extract_with_pdfplumber(file_path: Path) -> list[PageContent]:
    """Extract using pdfplumber (better for tables and structured text)."""
    import pdfplumber

    pages: list[PageContent] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                raw_tables = page.extract_tables() or []
                # Convert tables: each table is list of rows, each row is list of cells
                tables = [
                    [[cell or "" for cell in row] for row in table]
                    for table in raw_tables
                ]
                pages.append(PageContent(
                    page_number=i + 1,
                    text=text,
                    tables=tables,
                ))
    except Exception as e:
        logger.error("pdfplumber failed on %s: %s", file_path.name, e)

    return pages


def _extract_with_pymupdf(file_path: Path) -> list[PageContent]:
    """Extract using PyMuPDF (better for scanned or complex PDFs)."""
    import fitz  # PyMuPDF

    pages: list[PageContent] = []
    try:
        doc = fitz.open(file_path)
        for i, page in enumerate(doc):
            text = page.get_text()
            pages.append(PageContent(
                page_number=i + 1,
                text=text,
                tables=[],  # PyMuPDF doesn't extract tables natively
            ))
        doc.close()
    except Exception as e:
        logger.error("PyMuPDF failed on %s: %s", file_path.name, e)

    return pages
