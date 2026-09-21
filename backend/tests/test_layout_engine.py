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
    assert len(paginated) == 3
    assert len(paginated[0]["rows"]) == 4
    assert len(paginated[1]["rows"]) == 4
    assert len(paginated[2]["rows"]) == 1


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
