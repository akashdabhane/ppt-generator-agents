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

    # Title / section slide card
    TITLE_CARD_X: float = 1.0
    TITLE_CARD_Y: float = 1.2
    TITLE_CARD_WIDTH: float = 8.0
    TITLE_CARD_HEIGHT: float = 3.2

    # Text measurement. python-pptx has no text metrics, so estimate conservatively:
    # average glyph width as a fraction of the font size (the theme fonts average ~0.45–0.55 em),
    # line height as a multiple of the font size, and the default text-frame insets in inches.
    AVG_CHAR_WIDTH_EM: float = 0.55
    BOLD_CHAR_WIDTH_EM: float = 0.6
    LINE_SPACING: float = 1.2
    TEXT_INSET_X: float = 0.1
    TEXT_INSET_Y: float = 0.05
    TABLE_CELL_PADDING_Y: float = 0.1
    MIN_FONT_PT: int = 12
    TABLE_HEADER_FONT_PT: int = 12
    TABLE_BODY_FONT_PT: int = 11

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
    def get_title_card_rect(cls) -> Rect:
        return Rect(x=cls.TITLE_CARD_X, y=cls.TITLE_CARD_Y, width=cls.TITLE_CARD_WIDTH, height=cls.TITLE_CARD_HEIGHT)

    @classmethod
    def get_footer_rect(cls) -> Rect:
        return Rect(
            x=cls.MARGIN_LEFT,
            y=cls.SLIDE_HEIGHT - cls.FOOTER_HEIGHT,
            width=cls.SLIDE_WIDTH - cls.MARGIN_LEFT - cls.MARGIN_RIGHT,
            height=cls.FOOTER_HEIGHT
        )

    # ------------------------------------------------------------------
    # Text measurement & fitting
    # ------------------------------------------------------------------

    @classmethod
    def chars_per_line(cls, width_in: float, font_pt: float, bold: bool = False) -> int:
        em = cls.BOLD_CHAR_WIDTH_EM if bold else cls.AVG_CHAR_WIDTH_EM
        return max(1, int(width_in / (em * font_pt / 72.0)))

    @classmethod
    def estimate_lines(cls, text: str, width_in: float, font_pt: float, bold: bool = False) -> int:
        """Simulates word wrapping; words longer than a line are hard-broken."""
        cpl = cls.chars_per_line(width_in, font_pt, bold)
        total = 0
        for para in str(text).split("\n"):
            lines, cur = 1, 0
            for word in para.split():
                w = len(word)
                if cur == 0:
                    cur = w
                elif cur + 1 + w <= cpl:
                    cur += 1 + w
                else:
                    lines += 1
                    cur = w
                while cur > cpl:
                    lines += 1
                    cur -= cpl
            total += lines
        return max(total, 1)

    @classmethod
    def line_height(cls, font_pt: float) -> float:
        return font_pt * cls.LINE_SPACING / 72.0

    @classmethod
    def text_height(cls, text: str, width_in: float, font_pt: float, space_after_pt: float = 0, bold: bool = False) -> float:
        return cls.estimate_lines(text, width_in, font_pt, bold) * cls.line_height(font_pt) + space_after_pt / 72.0

    @classmethod
    def usable_size(cls, rect: Rect) -> Tuple[float, float]:
        """Width and height inside a text box's default insets."""
        return rect.width - 2 * cls.TEXT_INSET_X, rect.height - 2 * cls.TEXT_INSET_Y

    @classmethod
    def truncate_to_fit(cls, text: str, width_in: float, height_in: float, font_pt: float, bold: bool = False) -> str:
        """Cuts text at a word boundary (adding an ellipsis) so it fits the box. Last resort only."""
        text = str(text)
        if cls.estimate_lines(text, width_in, font_pt, bold) * cls.line_height(font_pt) <= height_in:
            return text
        words = text.split()
        lo, hi = 0, len(words)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = " ".join(words[:mid]) + "…"
            if cls.estimate_lines(candidate, width_in, font_pt, bold) * cls.line_height(font_pt) <= height_in:
                lo = mid
            else:
                hi = mid - 1
        if lo == 0:
            # Even one word is too long: hard-cut by characters
            max_chars = max(1, cls.chars_per_line(width_in, font_pt, bold) * max(1, int(height_in / cls.line_height(font_pt))) - 1)
            return text[:max_chars] + "…"
        return " ".join(words[:lo]) + "…"

    @classmethod
    def fit_font_size(cls, text: str, width_in: float, height_in: float, max_pt: int, min_pt: int = MIN_FONT_PT,
                      bold: bool = False) -> Tuple[int, str]:
        """Largest font size (stepping down by 2 pt) at which text fits; truncates at min_pt if it still doesn't."""
        size = max_pt
        while size > min_pt and cls.estimate_lines(text, width_in, size, bold) * cls.line_height(size) > height_in:
            size -= 2
        size = max(size, min_pt)
        return size, cls.truncate_to_fit(text, width_in, height_in, size, bold)

    @classmethod
    def paginate_text_items(cls, items: List[str], width_in: float, height_in: float, font_pt: float,
                            space_after_pt: float = 0, prefix: str = "", bold: bool = False) -> List[List[str]]:
        """
        Deterministic list pagination (the text equivalent of split_table_rows):
        greedily fills each page with whole items; an item taller than a full page is truncated.
        Always returns at least one (possibly empty) page.
        """
        pages: List[List[str]] = [[]]
        used = 0.0
        for item in items:
            text = str(item)
            h = cls.text_height(prefix + text, width_in, font_pt, space_after_pt, bold)
            if h > height_in:
                text = cls.truncate_to_fit(prefix + text, width_in, height_in - space_after_pt / 72.0, font_pt, bold)[len(prefix):]
                h = cls.text_height(prefix + text, width_in, font_pt, space_after_pt, bold)
            if pages[-1] and used + h > height_in:
                pages.append([])
                used = 0.0
            pages[-1].append(text)
            used += h
        return pages

    @classmethod
    def estimate_table_row_height(cls, row: List[str], num_cols: int, font_pt: float, bold: bool = False) -> float:
        content = cls.get_content_rect()
        col_width = content.width / max(num_cols, 1) - 2 * cls.TEXT_INSET_X
        lines = max((cls.estimate_lines(str(cell), col_width, font_pt, bold) for cell in row), default=1)
        return lines * cls.line_height(font_pt) + cls.TABLE_CELL_PADDING_Y

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

        # Row cap by density, plus a height budget so wide tables (narrow columns → more wrapping) also fit
        num_cols = max(len(columns), 1)
        budget = cls.get_content_rect().height - cls.estimate_table_row_height(
            columns, num_cols, cls.TABLE_HEADER_FONT_PT, bold=True)
        pages: List[List[List[str]]] = [[]]
        used = 0.0
        col_width = cls.get_content_rect().width / num_cols - 2 * cls.TEXT_INSET_X
        for row in rows:
            h = cls.estimate_table_row_height(row, num_cols, cls.TABLE_BODY_FONT_PT)
            if h > budget:
                # A single row taller than the slide: cut its cells down to what one slide can hold
                row = [cls.truncate_to_fit(str(cell), col_width, budget - cls.TABLE_CELL_PADDING_Y, cls.TABLE_BODY_FONT_PT)
                       for cell in row]
                h = cls.estimate_table_row_height(row, num_cols, cls.TABLE_BODY_FONT_PT)
            if pages[-1] and (len(pages[-1]) >= max_rows or used + h > budget):
                pages.append([])
                used = 0.0
            pages[-1].append(row)
            used += h

        total_parts = len(pages)
        return [
            {"columns": columns, "rows": page_rows, "part": idx, "total_parts": total_parts}
            for idx, page_rows in enumerate(pages, start=1)
        ]

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
