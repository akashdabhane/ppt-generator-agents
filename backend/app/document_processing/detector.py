import os


class DocumentTypeDetector:
    SUPPORTED_EXTENSIONS = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
        ".txt": "txt",
        ".csv": "csv",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".md": "markdown",
        ".markdown": "markdown",
    }

    @classmethod
    def detect_type(cls, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        if ext in cls.SUPPORTED_EXTENSIONS:
            return cls.SUPPORTED_EXTENSIONS[ext]
        raise ValueError(f"Unsupported document file extension: {ext}")
