from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


class LayoutEngine:
    # 16:9 Widescreen standard dimensions in Inches
    SLIDE_WIDTH: float = 10.0
    SLIDE_HEIGHT: float = 5.625
    
    MARGIN_LEFT: float = 0.8
    MARGIN_RIGHT: float = 0.8
    MARGIN_TOP: float = 0.6
    MARGIN_BOTTOM: float = 0.5

    TITLE_HEIGHT: float = 0.9
    FOOTER_HEIGHT: float = 0.4

    @classmethod
    def get_title_rect(cls) -> Rect:
        return Rect(
            x=cls.MARGIN_LEFT,
            y=cls.MARGIN_TOP,
            width=cls.SLIDE_WIDTH - cls.MARGIN_LEFT - cls.MARGIN_RIGHT,
            height=cls.TITLE_HEIGHT
        )

    @classmethod
    def get_content_rect(cls) -> Rect:
        content_y = cls.MARGIN_TOP + cls.TITLE_HEIGHT + 0.1
        content_height = cls.SLIDE_HEIGHT - content_y - cls.FOOTER_HEIGHT
        return Rect(
            x=cls.MARGIN_LEFT,
            y=content_y,
            width=cls.SLIDE_WIDTH - cls.MARGIN_LEFT - cls.MARGIN_RIGHT,
            height=content_height
        )

    @classmethod
    def get_two_column_rects(cls) -> Tuple[Rect, Rect]:
        content = cls.get_content_rect()
        gap = 0.4
        col_width = (content.width - gap) / 2.0
        
        left_col = Rect(x=content.x, y=content.y, width=col_width, height=content.height)
        right_col = Rect(x=content.x + col_width + gap, y=content.y, width=col_width, height=content.height)
        return left_col, right_col

    @classmethod
    def calculate_max_rows_per_slide(cls, rows: List[List[str]]) -> int:
        if not rows:
            return 10
        
        # Calculate max text character count across cells
        max_char_len = 0
        for row in rows:
            for cell in row:
                max_char_len = max(max_char_len, len(str(cell)))

        # Dynamic row pagination bounds based on content density
        if max_char_len > 120:
            return 4  # Long text cell density
        elif max_char_len > 60:
            return 7  # Medium text cell density
        else:
            return 10 # Short text standard cell density (Max 10 rows)

    @classmethod
    def split_table_rows(cls, columns: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
        """
        Deterministic Table Pagination Algorithm:
        Splits table rows into multiple paginated table slide specs to guarantee ZERO visual overflow.
        e.g., 25 rows -> 10 + 10 + 5 rows across 3 slides.
        """
        if not rows:
            return [{"columns": columns, "rows": []}]

        max_rows = cls.calculate_max_rows_per_slide(rows)
        
        if len(rows) <= max_rows:
            return [{"columns": columns, "rows": rows, "part": 1, "total_parts": 1}]

        paginated_tables = []
        total_parts = (len(rows) + max_rows - 1) // max_rows

        for i in range(0, len(rows), max_rows):
            chunk_rows = rows[i:i + max_rows]
            part_num = (i // max_rows) + 1
            paginated_tables.append({
                "columns": columns,
                "rows": chunk_rows,
                "part": part_num,
                "total_parts": total_parts
            })

        return paginated_tables

    @classmethod
    def validate_bounds(cls, rect: Rect) -> bool:
        """
        Validates that the rendered element is strictly inside the 16:9 slide boundaries.
        """
        epsilon = 1e-4
        if rect.x < 0 or rect.y < 0:
            return False
        if rect.right > cls.SLIDE_WIDTH + epsilon:
            return False
        if rect.bottom > cls.SLIDE_HEIGHT + epsilon:
            return False
        return True
