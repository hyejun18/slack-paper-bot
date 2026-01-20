"""PDF parsing module for extracting text from scientific papers."""

import hashlib
import logging
import tempfile
from pathlib import Path

import fitz  # PyMuPDF - much faster than pdfplumber
import requests

logger = logging.getLogger(__name__)


class PDFParseError(Exception):
    """Exception raised when PDF parsing fails."""

    pass


class PDFParser:
    """Extract text content from PDF files."""

    def __init__(self, max_pages: int = 50, timeout: int = 60):
        """
        Initialize PDF parser.

        Args:
            max_pages: Maximum number of pages to process (0 = no limit)
            timeout: Download timeout in seconds
        """
        self.max_pages = max_pages
        self.timeout = timeout

    def download_pdf(self, url: str, headers: dict | None = None) -> bytes:
        """
        Download PDF from URL.

        Args:
            url: URL to download from
            headers: Optional HTTP headers (e.g., for Slack authorization)

        Returns:
            PDF content as bytes

        Raises:
            PDFParseError: If download fails
        """
        try:
            logger.info(f"Downloading PDF from: {url[:50]}...")
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "application/pdf" not in content_type and not url.endswith(".pdf"):
                logger.warning(f"Unexpected content type: {content_type}")

            return response.content

        except requests.exceptions.Timeout:
            raise PDFParseError(f"Download timed out after {self.timeout}s")
        except requests.exceptions.RequestException as e:
            raise PDFParseError(f"Failed to download PDF: {e}")

    def extract_text(self, pdf_content: bytes) -> str:
        """
        Extract text from PDF content using PyMuPDF (fast).

        Args:
            pdf_content: PDF file content as bytes

        Returns:
            Extracted text from all pages

        Raises:
            PDFParseError: If parsing fails
        """
        try:
            return self._extract_from_bytes(pdf_content)
        except PDFParseError:
            raise
        except Exception as e:
            raise PDFParseError(f"Failed to extract text from PDF: {e}")

    def _extract_from_bytes(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes using PyMuPDF."""
        texts = []

        # Open PDF from bytes
        doc = fitz.open(stream=pdf_content, filetype="pdf")

        try:
            total_pages = len(doc)
            pages_to_process = total_pages

            if self.max_pages > 0:
                pages_to_process = min(total_pages, self.max_pages)

            logger.info(f"Processing {pages_to_process}/{total_pages} pages")

            for i in range(pages_to_process):
                try:
                    page = doc[i]
                    # Extract text only (no images/graphics processing)
                    text = page.get_text("text")
                    if text and text.strip():
                        texts.append(text.strip())
                except Exception as e:
                    logger.warning(f"Failed to extract page {i + 1}: {e}")
                    continue

        finally:
            doc.close()

        if not texts:
            raise PDFParseError("No text could be extracted from PDF")

        full_text = "\n\n".join(texts)
        logger.info(f"Extracted {len(full_text)} characters from PDF")

        return full_text

    def extract_from_url(self, url: str, headers: dict | None = None) -> str:
        """
        Download and extract text from a PDF URL.

        Args:
            url: URL of the PDF file
            headers: Optional HTTP headers

        Returns:
            Extracted text

        Raises:
            PDFParseError: If download or parsing fails
        """
        pdf_content = self.download_pdf(url, headers)
        return self.extract_text(pdf_content)

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of PDF content for caching."""
        return hashlib.sha256(content).hexdigest()

    def get_pdf_info(self, pdf_content: bytes) -> dict:
        """
        Get basic information about a PDF.

        Args:
            pdf_content: PDF file content

        Returns:
            Dictionary with page count and metadata
        """
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        try:
            return {
                "page_count": len(doc),
                "metadata": doc.metadata or {},
            }
        finally:
            doc.close()
