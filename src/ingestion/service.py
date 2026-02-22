import io
import base64
import hashlib
from typing import List
from langchain_community.document_loaders.parsers.pdf import PyPDFParser
from langchain_core.document_loaders import Blob
from docx import Document as DocxDocument
import fitz  # pymupdf


class IngestionService:
    def __init__(self):
        self.pdf_parser = PyPDFParser()

    def calculate_hash(self, file_content: bytes) -> str:
        """Calculates SHA-256 hash of the file content."""
        return hashlib.sha256(file_content).hexdigest()

    def extract_text(self, file_content: bytes, filename: str) -> str:
        """
        Extracts full text from the uploaded file.
        Supports PDF, DOCX, and plain text.
        """
        lower = filename.lower()
        if lower.endswith('.pdf'):
            pages = self.extract_pages(file_content, filename)
            return "\n".join(p["content"] for p in pages)
        elif lower.endswith('.docx'):
            return self._extract_docx_text(file_content)
        else:
            try:
                return file_content.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("Unsupported file format or encoding")

    def extract_pages(self, file_content: bytes, filename: str) -> List[dict]:
        """
        Extract text per page. Returns list of {page_number, content}.
        Uses LangChain PyPDFParser for PDFs, DOCX extraction, or plain text fallback.
        """
        lower = filename.lower()
        if lower.endswith('.pdf'):
            return self._extract_pdf_pages(file_content)
        elif lower.endswith('.docx'):
            text = self._extract_docx_text(file_content)
            return [{"page_number": 1, "content": text}]
        else:
            try:
                text = file_content.decode('utf-8')
                return [{"page_number": 1, "content": text}]
            except UnicodeDecodeError:
                raise ValueError("Unsupported file format or encoding")

    def _extract_docx_text(self, file_content: bytes) -> str:
        """Extract text from a DOCX file using python-docx."""
        doc = DocxDocument(io.BytesIO(file_content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    def _extract_pdf_pages(self, file_content: bytes) -> List[dict]:
        """Extract text page-by-page from a PDF using LangChain's PyPDFParser."""
        blob = Blob.from_data(file_content, mime_type="application/pdf")
        documents = list(self.pdf_parser.lazy_parse(blob))
        pages = []
        for doc in documents:
            text = doc.page_content or ""
            if text.strip():
                page_num = doc.metadata.get("page", 0) + 1  # PyPDFParser is 0-indexed
                pages.append({"page_number": page_num, "content": text})
        return pages

    def extract_images(self, file_content: bytes, filename: str) -> List[dict]:
        """
        Extract page images from PDF pages that contain embedded images/diagrams.
        Returns list of {"page_number": int, "image_bytes": bytes, "image_base64": str}.
        Non-PDF files return an empty list.
        """
        if not filename.lower().endswith('.pdf'):
            return []

        images = []
        doc = fitz.open(stream=file_content, filetype="pdf")
        try:
            for page_num, page in enumerate(doc, start=1):
                if not page.get_images():
                    continue
                # Render the page to a PNG pixmap
                pixmap = page.get_pixmap(dpi=150)
                image_bytes = pixmap.tobytes("png")
                images.append({
                    "page_number": page_num,
                    "image_bytes": image_bytes,
                    "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
                })
        finally:
            doc.close()

        return images
