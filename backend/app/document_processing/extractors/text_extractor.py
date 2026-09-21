import re
from typing import List, Dict, Any


class TextProcessor:
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        blocks = []
        # Split markdown or text by headers (# Heading)
        sections = re.split(r'\n(?=#+ )', content)
        
        for idx, sec in enumerate(sections, start=1):
            sec_str = sec.strip()
            if not sec_str:
                continue
            
            lines = sec_str.split("\n")
            section_title = lines[0].lstrip("#").strip() if lines[0].startswith("#") else f"Section {idx}"
            
            blocks.append({
                "content": sec_str,
                "page": None,
                "section": section_title,
                "is_table": False,
                "table_data": None
            })

        return blocks
