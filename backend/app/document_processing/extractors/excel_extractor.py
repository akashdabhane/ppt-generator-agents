import pandas as pd
from typing import List, Dict, Any


class XLSXProcessor:
    def process(self, file_path: str, is_csv: bool = False) -> List[Dict[str, Any]]:
        blocks = []
        
        if is_csv:
            excel_file = {"Sheet1": pd.read_csv(file_path)}
        else:
            excel_file = pd.read_excel(file_path, sheet_name=None)

        for sheet_name, df in excel_file.items():
            if df.empty:
                continue
            
            # Clean dataframe text values
            df = df.fillna("")
            headers = [str(col).strip() for col in df.columns]
            rows = [[str(val).strip() for val in row] for row in df.values]

            # Construct structured text snippet for RAG retrieval
            table_str = f"Spreadsheet Sheet: {sheet_name}\n"
            table_str += " | ".join(headers) + "\n"
            table_str += "-" * 40 + "\n"
            for row in rows[:50]:  # Up to 50 rows per textual block snippet
                table_str += " | ".join(row) + "\n"

            blocks.append({
                "content": table_str.strip(),
                "page": None,
                "section": f"Sheet: {sheet_name}",
                "is_table": True,
                "table_data": {
                    "sheet": sheet_name,
                    "headers": headers,
                    "rows": rows
                }
            })

        return blocks
