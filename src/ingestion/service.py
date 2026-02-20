import hashlib
from typing import List
from langchain_community.document_loaders.parsers.pdf import PyPDFParser
from langchain_core.document_loaders import Blob


class IngestionService:
    def __init__(self):
        self.pdf_parser = PyPDFParser()

    def calculate_hash(self, file_content: bytes) -> str:
        """Calculates SHA-256 hash of the file content."""
        return hashlib.sha256(file_content).hexdigest()

    def extract_text(self, file_content: bytes, filename: str) -> str:
        """
        Extracts full text from the uploaded file.
        Supports PDF via PyPDFParser; falls back to UTF-8 text.
        """
        if filename.lower().endswith('.pdf'):
            pages = self.extract_pages(file_content, filename)
            return "\n".join(p["content"] for p in pages)
        else:
            try:
                return file_content.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("Unsupported file format or encoding")

    def extract_pages(self, file_content: bytes, filename: str) -> List[dict]:
        """
        Extract text per page. Returns list of {page_number, content}.
        Uses LangChain PyPDFParser for PDFs, plain text fallback otherwise.
        """
        if filename.lower().endswith('.pdf'):
            return self._extract_pdf_pages(file_content)
        else:
            try:
                text = file_content.decode('utf-8')
                return [{"page_number": 1, "content": text}]
            except UnicodeDecodeError:
                raise ValueError("Unsupported file format or encoding")

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
