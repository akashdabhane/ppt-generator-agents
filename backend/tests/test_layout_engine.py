import pytest
from app.presentation.layout_engine import LayoutEngine, Rect


def test_table_pagination_single_row():
    columns = ["ID", "Name", "Revenue"]
    rows = [["1", "Alpha Inc", "$100,000"]]
    
    paginated = LayoutEngine.split_table_rows(columns, rows)
    assert len(paginated) == 1
    assert len(paginated[0]["rows"]) == 1


def test_table_pagination_ten_rows():
    columns = ["Metric", "Value"]
    rows = [[f"Metric {i}", f"{i * 10}"] for i in range(1, 11)]
    
    paginated = LayoutEngine.split_table_rows(columns, rows)
    assert len(paginated) == 1
    assert len(paginated[0]["rows"]) == 10


def test_table_pagination_eleven_rows():
    columns = ["Metric", "Value"]
    rows = [[f"Metric {i}", f"{i * 10}"] for i in range(1, 12)]
    
    paginated = LayoutEngine.split_table_rows(columns, rows)
    assert len(paginated) == 2
    assert len(paginated[0]["rows"]) == 10
    assert len(paginated[1]["rows"]) == 1


def test_table_pagination_twenty_five_rows():
    columns = ["Department", "Q1", "Q2", "Q3", "Q4"]
    rows = [[f"Dept {i}", "10", "20", "30", "40"] for i in range(1, 26)]
    
    paginated = LayoutEngine.split_table_rows(columns, rows)
    assert len(paginated) == 3
    assert len(paginated[0]["rows"]) == 10
    assert len(paginated[1]["rows"]) == 10
    assert len(paginated[2]["rows"]) == 5


def test_table_pagination_long_text():
    columns = ["Requirement", "Description"]
    # Cells with long text (> 120 chars) should trigger max 4 rows per slide limit
    rows = [[f"Req {i}", "X" * 150] for i in range(1, 10)]
    
    paginated = LayoutEngine.split_table_rows(columns, rows)
    # The density cap (max 4) applies; the height budget may pack fewer rows per slide
    assert all(1 <= len(p["rows"]) <= 4 for p in paginated)
    assert sum(len(p["rows"]) for p in paginated) == 9
    assert [p["part"] for p in paginated] == list(range(1, len(paginated) + 1))


def test_slide_bounds_validation():
    # Valid title rect inside 10.0 x 5.625 slide
    valid_rect = Rect(x=0.8, y=0.6, width=8.4, height=0.9)
    assert LayoutEngine.validate_bounds(valid_rect) is True

    # Invalid rect overflowing right boundary
    overflow_right = Rect(x=5.0, y=1.0, width=6.0, height=2.0)
    assert LayoutEngine.validate_bounds(overflow_right) is False

    # Invalid rect overflowing bottom boundary
    overflow_bottom = Rect(x=0.8, y=4.5, width=8.4, height=2.0)
    assert LayoutEngine.validate_bounds(overflow_bottom) is False


# ---------------------------------------------------------------------------
# Zero-overflow: text measurement, fitting and pagination
# ---------------------------------------------------------------------------

def _pages_fit(pages, width, height, font_pt, space_after_pt, prefix=""):
    for page in pages:
        used = sum(LayoutEngine.text_height(prefix + t, width, font_pt, space_after_pt) for t in page)
        assert used <= height + 1e-6


def test_estimate_lines_wraps_words():
    # 10 in at 12 pt → ~109 chars per line
    assert LayoutEngine.estimate_lines("short", 10.0, 12) == 1
    assert LayoutEngine.estimate_lines("word " * 60, 10.0, 12) == 3
    assert LayoutEngine.estimate_lines("line one\nline two", 10.0, 12) == 2


def test_short_bullets_stay_on_one_slide():
    w, h = LayoutEngine.usable_size(LayoutEngine.get_content_rect())
    pages = LayoutEngine.paginate_text_items(["Revenue up 12%", "Costs down 3%", "Churn flat"], w, h, 14, 12, "• ")
    assert pages == [["Revenue up 12%", "Costs down 3%", "Churn flat"]]


def test_long_bullet_list_is_split_without_losing_items():
    w, h = LayoutEngine.usable_size(LayoutEngine.get_content_rect())
    bullets = [f"Finding {i}: " + "detailed supporting evidence from the quarterly filing " * 2 for i in range(15)]
    pages = LayoutEngine.paginate_text_items(bullets, w, h, 14, 12, "• ")
    assert len(pages) > 1
    assert [b for p in pages for b in p] == bullets
    _pages_fit(pages, w, h, 14, 12, "• ")


def test_single_huge_bullet_is_truncated_to_fit():
    w, h = LayoutEngine.usable_size(LayoutEngine.get_content_rect())
    pages = LayoutEngine.paginate_text_items(["word " * 2000], w, h, 14, 12, "• ")
    assert len(pages) == 1
    assert pages[0][0].endswith("…")
    _pages_fit(pages, w, h, 14, 12, "• ")


def test_empty_list_gives_one_empty_page():
    assert LayoutEngine.paginate_text_items([], 8.0, 3.0, 14) == [[]]


def test_fit_font_size_shrinks_long_titles_then_truncates():
    w, h = LayoutEngine.usable_size(LayoutEngine.get_title_rect())
    size, text = LayoutEngine.fit_font_size("Q3 Results", w, h, 24)
    assert (size, text) == (24, "Q3 Results")

    long_title = "Quarterly revenue performance across all regional business units and product lines"
    size, text = LayoutEngine.fit_font_size(long_title, w, h, 24)
    assert 12 <= size <= 24
    assert LayoutEngine.estimate_lines(text, w, size) * LayoutEngine.line_height(size) <= h

    size, text = LayoutEngine.fit_font_size("word " * 500, w, h, 24)
    assert size == LayoutEngine.MIN_FONT_PT
    assert text.endswith("…")


def test_wide_table_paginates_by_height():
    columns = [f"Col {i}" for i in range(8)]
    rows = [["a fairly long cell value that wraps in a narrow column"] * 8 for _ in range(10)]
    pages = LayoutEngine.split_table_rows(columns, rows)
    assert len(pages) > 1
    budget = LayoutEngine.get_content_rect().height
    for p in pages:
        used = LayoutEngine.estimate_table_row_height(columns, 8, 12, bold=True) + sum(
            LayoutEngine.estimate_table_row_height(r, 8, 11) for r in p["rows"])
        assert used <= budget + 1e-6


def test_fixed_rects_are_inside_the_slide():
    for rect in [LayoutEngine.get_title_rect(), LayoutEngine.get_content_rect(), LayoutEngine.get_footer_rect(),
                 LayoutEngine.get_title_card_rect(), *LayoutEngine.get_two_column_rects()]:
        assert LayoutEngine.validate_bounds(rect)
