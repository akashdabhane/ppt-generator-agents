import pdfplumber
from typing import List, Dict, Any


class PDFProcessor:
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        blocks = []
        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                # 1. Extract tables if any
                tables = page.extract_tables()
                if tables:
                    for tbl in tables:
                        if not tbl or len(tbl) == 0:
                            continue
                        headers = [str(cell or "").strip() for cell in tbl[0]]
                        rows = [[str(cell or "").strip() for cell in row] for row in tbl[1:]]
                        
                        # Build formatted table string representation
                        table_str = f"Table on Page {page_idx}:\n"
                        table_str += " | ".join(headers) + "\n"
                        table_str += "-" * 40 + "\n"
                        for row in rows:
                            table_str += " | ".join(row) + "\n"
                            
                        blocks.append({
                            "content": table_str.strip(),
                            "page": page_idx,
                            "section": "Detected Table",
                            "is_table": True,
                            "table_data": {
                                "headers": headers,
                                "rows": rows
                            }
                        })
                
                # 2. Extract regular text
                text = page.extract_text()
                if text and text.strip():
                    blocks.append({
                        "content": text.strip(),
                        "page": page_idx,
                        "section": f"Page {page_idx}",
                        "is_table": False,
                        "table_data": None
                    })
        return blocks
