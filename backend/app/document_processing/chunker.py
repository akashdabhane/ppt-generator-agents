import re
from typing import List, Dict, Any
from app.document_processing.detector import DocumentTypeDetector
from app.document_processing.extractors.pdf_extractor import PDFProcessor
from app.document_processing.extractors.docx_extractor import DOCXProcessor
from app.document_processing.extractors.excel_extractor import XLSXProcessor
from app.document_processing.extractors.text_extractor import TextProcessor
from app.document_processing.extractors.pptx_extractor import PPTXProcessor


class DocumentChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.pdf_proc = PDFProcessor()
        self.docx_proc = DOCXProcessor()
        self.xlsx_proc = XLSXProcessor()
        self.text_proc = TextProcessor()
        self.pptx_proc = PPTXProcessor()

    def process_and_chunk(self, document_id: str, filename: str, file_path: str) -> List[Dict[str, Any]]:
        doc_type = DocumentTypeDetector.detect_type(filename)
        
        # 1. Extract raw blocks
        if doc_type == "pdf":
            raw_blocks = self.pdf_proc.process(file_path)
        elif doc_type == "docx":
            raw_blocks = self.docx_proc.process(file_path)
        elif doc_type == "pptx":
            raw_blocks = self.pptx_proc.process(file_path)
        elif doc_type in ["xlsx", "csv"]:
            raw_blocks = self.xlsx_proc.process(file_path, is_csv=(doc_type == "csv"))
        else:
            raw_blocks = self.text_proc.process(file_path)

        chunks = []
        chunk_index = 0

        # 2. Chunk content into RAG chunks while preserving rich metadata
        for block in raw_blocks:
            content = block["content"]
            page = block.get("page")
            section = block.get("section", "General")
            is_table = block.get("is_table", False)
            table_data = block.get("table_data")

            # Structured tables remain intact without fragmenting mid-row
            if is_table:
                metadata = {
                    "document_id": document_id,
                    "filename": filename,
                    "page": page,
                    "section": section,
                    "chunk_index": chunk_index,
                    "document_type": doc_type,
                    "is_table": True,
                    "table_data": table_data
                }
                chunks.append({
                    "content": content,
                    "chunk_index": chunk_index,
                    "page": page,
                    "section": section,
                    "metadata": metadata
                })
                chunk_index += 1
            else:
                # Text chunking algorithm
                text_splits = self._split_text(content, self.chunk_size, self.chunk_overlap)
                for split_text in text_splits:
                    metadata = {
                        "document_id": document_id,
                        "filename": filename,
                        "page": page,
                        "section": section,
                        "chunk_index": chunk_index,
                        "document_type": doc_type,
                        "is_table": False
                    }
                    chunks.append({
                        "content": split_text,
                        "chunk_index": chunk_index,
                        "page": page,
                        "section": section,
                        "metadata": metadata
                    })
                    chunk_index += 1

        return chunks

    # Sentence ends (., !, ? followed by whitespace) and line breaks
    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")

    def _split_text(self, text: str, size: int, overlap: int) -> List[str]:
        """
        Packs whole sentences into chunks of at most `size` chars, repeating trailing sentences (up to `overlap`
        chars) at the start of the next chunk. Never cuts a sentence, word or number in half unless a single
        sentence is longer than `size`, in which case it is split at word boundaries.
        """
        text = text.strip()
        if len(text) <= size:
            return [text] if text else []

        units: List[str] = []
        for sentence in (s.strip() for s in self._SENTENCE_BOUNDARY.split(text)):
            if not sentence:
                continue
            if len(sentence) <= size:
                units.append(sentence)
                continue
            piece = ""
            for word in sentence.split():
                if piece and len(piece) + 1 + len(word) > size:
                    units.append(piece)
                    piece = word
                else:
                    piece = f"{piece} {word}" if piece else word
            if piece:
                units.append(piece)

        chunks: List[str] = []
        current: List[str] = []
        for unit in units:
            if current and len(" ".join(current + [unit])) > size:
                chunks.append(" ".join(current))
                # Carry trailing sentences into the next chunk as overlap
                carry: List[str] = []
                for prev in reversed(current):
                    if len(" ".join([prev] + carry)) > overlap:
                        break
                    carry.insert(0, prev)
                current = carry if len(" ".join(carry + [unit])) <= size else []
            current.append(unit)
        if current:
            chunks.append(" ".join(current))
        return chunks
